"""
Safe Filesystem Controller for Paaro Computer Control (Step 9).
Provides safe path resolution, directory traversal prevention, root containment, and safe folder/file opening.
"""

import logging
import os
import subprocess
import time
from typing import List, Optional, Set, Tuple

from computer.models import ComputerActionResult, ComputerVerificationResult
from config import settings

logger = logging.getLogger("paaro.computer.filesystem")


class SafePathResolver:
    """
    Validates, normalizes, and contains filesystem access within approved directory roots.
    Prevents path traversal, access to restricted OS files, and credential leaks.
    """

    RESTRICTED_FILENAMES: Set[str] = {
        "sam",
        "system",
        "security",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
        "master.key",
        "passwords.txt",
        "credentials.json",
        "shadow",
        "sudoers",
    }

    RESTRICTED_EXTENSIONS: Set[str] = {
        ".key",
        ".pem",
        ".pfx",
        ".p12",
        ".kdbx",
    }

    def __init__(self, allowed_roots: Optional[List[str]] = None):
        self.allowed_roots: List[str] = []
        if allowed_roots is not None:
            for r in allowed_roots:
                if r:
                    real_r = os.path.realpath(os.path.abspath(os.path.expanduser(r)))
                    if real_r not in self.allowed_roots:
                        self.allowed_roots.append(real_r)
        else:
            # Built-in safe roots
            user_home = os.path.realpath(os.path.expanduser("~"))
            self.allowed_roots.append(user_home)

            # Common user subdirectories
            for sub in ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"]:
                p = os.path.join(user_home, sub)
                if os.path.isdir(p):
                    self.allowed_roots.append(os.path.realpath(p))

            # Project root
            cwd = os.path.realpath(os.getcwd())
            self.allowed_roots.append(cwd)

            # Configured roots
            configured = settings.COMPUTER_CONTROL_ALLOWED_ROOTS
            if configured:
                for r in configured:
                    if os.path.exists(r):
                        real_r = os.path.realpath(os.path.abspath(os.path.expanduser(r)))
                        if real_r not in self.allowed_roots:
                            self.allowed_roots.append(real_r)

    def resolve_safe_path(
        self,
        raw_path: str,
        must_exist: bool = True,
        is_directory: Optional[bool] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Validate and resolve a path string against allowed roots.
        Returns: (is_valid, resolved_path, error_message)
        """
        if not raw_path or not isinstance(raw_path, str) or not raw_path.strip():
            return False, "", "Path cannot be empty"

        cleaned = raw_path.strip()

        # Handle symbolic / natural root shortcuts
        home_path = os.path.realpath(os.path.expanduser("~"))
        shortcuts = {
            "home": home_path,
            "~": home_path,
            "downloads": os.path.join(home_path, "Downloads"),
            "documents": os.path.join(home_path, "Documents"),
            "desktop": os.path.join(home_path, "Desktop"),
            "project": os.path.realpath(os.getcwd()),
            "paaro": os.path.realpath(os.getcwd()),
            "paaro project": os.path.realpath(os.getcwd()),
            "current": os.path.realpath(os.getcwd()),
            "cwd": os.path.realpath(os.getcwd()),
        }

        cleaned_lower = cleaned.lower().strip()
        if cleaned_lower in shortcuts:
            cleaned = shortcuts[cleaned_lower]

        # Expand user and environment variables
        expanded = os.path.expandvars(os.path.expanduser(cleaned))
        if not os.path.isabs(expanded):
            # Resolve relative to current project directory
            expanded = os.path.join(os.getcwd(), expanded)

        # Resolve absolute canonical path
        try:
            resolved = os.path.realpath(os.path.abspath(expanded))
        except Exception as e:
            return False, "", f"Failed to normalize path '{cleaned}': {e}"

        # 1. Check path traversal and root containment
        is_contained = False
        for root in self.allowed_roots:
            try:
                # Check if resolved path starts with root
                common = os.path.commonpath([resolved, root])
                if common == root:
                    is_contained = True
                    break
            except ValueError:
                # Different drives (e.g. C: and F:)
                continue

        if not is_contained:
            logger.warning("[COMPUTER] Path '%s' rejected: outside allowed roots", resolved)
            return False, resolved, f"Access denied: path '{raw_path}' is outside approved directories."

        # 2. Check restricted sensitive files and extensions
        basename = os.path.basename(resolved).lower()
        _, ext = os.path.splitext(resolved)
        ext = ext.lower()

        if basename in self.RESTRICTED_FILENAMES:
            logger.warning("[COMPUTER] Path '%s' rejected: matches restricted filename '%s'", resolved, basename)
            return False, resolved, f"Access denied: restricted sensitive file '{basename}'."

        if ext in self.RESTRICTED_EXTENSIONS:
            logger.warning("[COMPUTER] Path '%s' rejected: matches restricted extension '%s'", resolved, ext)
            return False, resolved, f"Access denied: restricted sensitive file extension '{ext}'."

        # 3. Check existence if required
        if must_exist and not os.path.exists(resolved):
            return False, resolved, f"Path does not exist: '{resolved}'"

        if is_directory is True and os.path.exists(resolved) and not os.path.isdir(resolved):
            return False, resolved, f"Path is not a directory: '{resolved}'"

        if is_directory is False and os.path.exists(resolved) and not os.path.isfile(resolved):
            return False, resolved, f"Path is not a file: '{resolved}'"

        return True, resolved, None

    def open_folder(self, folder_path: str) -> ComputerActionResult:
        """
        Safely open a folder in Windows Explorer.
        """
        valid, resolved, err = self.resolve_safe_path(folder_path, must_exist=True, is_directory=True)
        if not valid:
            return ComputerActionResult(
                success=False,
                action="open_folder",
                target=folder_path,
                error=err,
                verification=ComputerVerificationResult(verified=False, reason=err or "Invalid path"),
            )

        logger.info("[COMPUTER] Opening folder in Explorer: '%s'", resolved)
        try:
            if hasattr(os, "startfile"):
                os.startfile(resolved)
            else:
                subprocess.Popen(["explorer", resolved])

            # Verification: directory exists and is accessible
            verified = os.path.isdir(resolved)
            return ComputerActionResult(
                success=True,
                action="open_folder",
                target=resolved,
                result={"path": resolved, "type": "directory"},
                verification=ComputerVerificationResult(
                    verified=verified,
                    reason=f"Folder opened in Explorer: {resolved}",
                    details={"path": resolved},
                ),
            )
        except Exception as e:
            logger.error("[COMPUTER] Error opening folder '%s': %s", resolved, e)
            return ComputerActionResult(
                success=False,
                action="open_folder",
                target=resolved,
                error=str(e),
                verification=ComputerVerificationResult(verified=False, reason=str(e)),
            )

    def open_file(self, file_path: str) -> ComputerActionResult:
        """
        Safely open a file in its default associated desktop application.
        """
        valid, resolved, err = self.resolve_safe_path(file_path, must_exist=True, is_directory=False)
        if not valid:
            return ComputerActionResult(
                success=False,
                action="open_file",
                target=file_path,
                error=err,
                verification=ComputerVerificationResult(verified=False, reason=err or "Invalid file path"),
            )

        logger.info("[COMPUTER] Opening file in default application: '%s'", resolved)
        try:
            if hasattr(os, "startfile"):
                os.startfile(resolved)
            else:
                subprocess.Popen(["cmd", "/c", "start", "", resolved])

            verified = os.path.isfile(resolved)
            return ComputerActionResult(
                success=True,
                action="open_file",
                target=resolved,
                result={"path": resolved, "size_bytes": os.path.getsize(resolved)},
                verification=ComputerVerificationResult(
                    verified=verified,
                    reason=f"File opened in default application: {resolved}",
                    details={"path": resolved, "size": os.path.getsize(resolved)},
                ),
            )
        except Exception as e:
            logger.error("[COMPUTER] Error opening file '%s': %s", resolved, e)
            return ComputerActionResult(
                success=False,
                action="open_file",
                target=resolved,
                error=str(e),
                verification=ComputerVerificationResult(verified=False, reason=str(e)),
            )
