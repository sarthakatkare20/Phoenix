"""
Safe URL Opener for Paaro Computer Control (Step 9).
Validates URL schemes, blocks dangerous protocols (file://, javascript:, data:), and opens approved web URLs.
"""

import logging
import os
import re
from typing import Optional, Set, Tuple
from urllib.parse import urlparse
import webbrowser

from computer.models import ComputerActionResult, ComputerVerificationResult

logger = logging.getLogger("paaro.computer.urls")


class SafeUrlOpener:
    """
    Validates and securely launches web URLs in the user's default browser.
    Blocks protocol-based exploitation such as file://, javascript:, data:, and command injections.
    """

    ALLOWED_SCHEMES: Set[str] = {"http", "https"}
    FORBIDDEN_SCHEMES: Set[str] = {
        "file",
        "javascript",
        "data",
        "vbscript",
        "chrome",
        "about",
        "blob",
        "ws",
        "wss",
        "shell",
        "cmd",
        "powershell",
    }

    KNOWN_SHORTCUTS = {
        "google": "https://google.com",
        "github": "https://github.com",
        "youtube": "https://youtube.com",
        "reddit": "https://reddit.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "netflix": "https://netflix.com",
        "paaro docs": "https://github.com",
        "docs": "https://github.com",
        "paaro documentation": "https://github.com",
    }

    def validate_url(self, raw_url: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validate, normalize, and verify URL scheme safety.
        Returns: (is_valid, normalized_url, error_message)
        """
        if not raw_url or not isinstance(raw_url, str) or not raw_url.strip():
            return False, "", "URL cannot be empty"

        cleaned = raw_url.strip()

        # Check natural shortcuts
        cleaned_lower = cleaned.lower()
        if cleaned_lower in self.KNOWN_SHORTCUTS:
            cleaned = self.KNOWN_SHORTCUTS[cleaned_lower]

        # If has a scheme format (e.g. scheme:...)
        if re.match(r"^[a-zA-Z0-9+.-]+:", cleaned):
            pass
        elif cleaned.startswith("www.") or ("." in cleaned and " " not in cleaned):
            cleaned = f"https://{cleaned}"
        else:
            cleaned = f"https://www.google.com/search?q={cleaned}"

        # Parse URL
        try:
            parsed = urlparse(cleaned)
        except Exception as e:
            return False, cleaned, f"Malformed URL: {e}"

        scheme = (parsed.scheme or "").lower()

        # Check forbidden schemes
        if scheme in self.FORBIDDEN_SCHEMES:
            logger.warning("[COMPUTER] URL '%s' rejected: forbidden scheme '%s'", cleaned, scheme)
            return False, cleaned, f"Access denied: URL scheme '{scheme}:' is forbidden for security."

        # Check allowed schemes
        if scheme not in self.ALLOWED_SCHEMES:
            logger.warning("[COMPUTER] URL '%s' rejected: unsupported scheme '%s'", cleaned, scheme)
            return False, cleaned, f"Access denied: URL scheme '{scheme}:' is not supported (only http/https permitted)."

        if not parsed.netloc:
            return False, cleaned, f"Invalid URL: missing host domain in '{cleaned}'"

        return True, cleaned, None

    def open_url(self, url: str) -> ComputerActionResult:
        """
        Safely open an approved web URL in the system's default browser.
        """
        is_valid, normalized_url, err = self.validate_url(url)
        if not is_valid:
            return ComputerActionResult(
                success=False,
                action="open_url",
                target=url,
                error=err,
                verification=ComputerVerificationResult(verified=False, reason=err or "Invalid URL"),
            )

        logger.info("[COMPUTER] Opening URL in browser: '%s'", normalized_url)
        try:
            # Launch via standard webbrowser library or OS default
            opened = webbrowser.open(normalized_url, new=2)
            if not opened and hasattr(os, "startfile"):
                os.startfile(normalized_url)
                opened = True

            return ComputerActionResult(
                success=True,
                action="open_url",
                target=normalized_url,
                result={"url": normalized_url, "scheme": urlparse(normalized_url).scheme},
                verification=ComputerVerificationResult(
                    verified=True,
                    reason=f"URL dispatched to default browser: {normalized_url}",
                    details={"url": normalized_url},
                ),
            )
        except Exception as e:
            logger.error("[COMPUTER] Error launching browser for URL '%s': %s", normalized_url, e)
            return ComputerActionResult(
                success=False,
                action="open_url",
                target=normalized_url,
                error=str(e),
                verification=ComputerVerificationResult(verified=False, reason=str(e)),
            )
