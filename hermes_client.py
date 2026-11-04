"""
Hermes Agent Client for Project Phoenix.
Connects Phoenix Voice & HUD to Nous Research's autonomous Hermes Agent engine.
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger("paaro.hermes")


def get_hermes_executable() -> str:
    """Resolve the absolute path to the hermes executable."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    default_path = os.path.join(local_app_data, "hermes", "bin", "hermes.exe")
    if os.path.isfile(default_path):
        return default_path

    # Fallback to PATH lookup
    path_lookup = shutil.which("hermes")
    if path_lookup:
        return path_lookup

    return default_path


def execute_hermes(query: str, cwd: Optional[str] = None, timeout: int = 180) -> Dict[str, Any]:
    """
    Execute an autonomous task with Hermes Agent CLI.
    Runs in quiet/yolo mode for headless, non-interactive execution.
    """
    if not query or not query.strip():
        return {
            "status": "error",
            "message": "Empty query provided for Hermes agent.",
            "output": "",
        }

    hermes_bin = get_hermes_executable()
    if not os.path.isfile(hermes_bin):
        err = f"Hermes executable not found at '{hermes_bin}'."
        logger.error(err)
        return {"status": "error", "message": err, "output": ""}

    work_dir = os.path.abspath(cwd) if cwd else os.getcwd()
    cmd = [
        hermes_bin,
        "chat",
        "-Q",
        "--yolo",
        "--in",
        work_dir,
        "-q",
        query.strip(),
    ]

    logger.info("Executing Hermes task in '%s': %s", work_dir, query[:100])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
            encoding="utf-8",
            errors="replace",
        )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        # Clean session metadata footer if present
        clean_output = re.sub(r"\n*session_id:\s*\S+", "", stdout).strip()
        if not clean_output and stderr:
            clean_output = stderr

        success = proc.returncode == 0
        logger.info(
            "Hermes task completed (code %d). Output length: %d chars",
            proc.returncode,
            len(clean_output),
        )
        return {
            "status": "success" if success else "error",
            "output": clean_output,
            "returncode": proc.returncode,
            "query": query,
            "cwd": work_dir,
        }

    except subprocess.TimeoutExpired:
        msg = f"Hermes task timed out after {timeout} seconds."
        logger.warning(msg)
        return {"status": "error", "message": msg, "output": ""}
    except Exception as e:
        logger.error("Hermes execution error: %s", e)
        return {"status": "error", "message": str(e), "output": ""}


async def execute_hermes_async(
    query: str, cwd: Optional[str] = None, timeout: int = 180
) -> Dict[str, Any]:
    """Asynchronously execute Hermes in a background thread to prevent blocking the event loop."""
    return await asyncio.to_thread(execute_hermes, query, cwd, timeout)
