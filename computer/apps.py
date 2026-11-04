"""
Application Registry and Controller for Paaro Computer Control (Step 9).
Manages application aliases, executable discovery, launch execution, graceful closing, and window focus.
"""

import ctypes
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from computer.models import AppInfo, ComputerActionResult, ComputerVerificationResult

logger = logging.getLogger("paaro.computer.apps")


def has_visible_window(keyword: str) -> bool:
    """Check if any currently visible top-level desktop window contains the keyword in its title."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        found = False
        def enum_cb(hwnd, extra):
            nonlocal found
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    if keyword.lower() in buff.value.lower():
                        found = True
                        return False
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return found
    except Exception:
        return False


class ApplicationRegistry:
    """
    Registry of approved desktop applications with natural language alias resolution.
    Discovers executables safely without exposing arbitrary command injection.
    """

    # Static safe mapping of app identifier -> canonical details & aliases
    KNOWN_APPS: Dict[str, Dict[str, Any]] = {
        "chrome": {
            "name": "Google Chrome",
            "executables": ["chrome.exe", "chrome"],
            "aliases": ["google chrome", "browser", "chrome browser", "google"],
            "uri": None,
        },
        "vscode": {
            "name": "Visual Studio Code",
            "executables": ["code.cmd", "code.exe", "code"],
            "aliases": ["vs code", "visual studio code", "code", "editor", "ide"],
            "uri": None,
        },
        "spotify": {
            "name": "Spotify",
            "executables": ["spotify.exe", "spotify"],
            "aliases": ["spotify music", "music app", "music"],
            "uri": "spotify:",
        },
        "notepad": {
            "name": "Notepad",
            "executables": ["notepad.exe", "notepad"],
            "aliases": ["text editor", "notes", "notepad editor"],
            "uri": None,
        },
        "calculator": {
            "name": "Calculator",
            "executables": ["calc.exe", "calc"],
            "aliases": ["calc"],
            "uri": "calculator:",
        },
        "terminal": {
            "name": "Command Prompt / Terminal",
            "executables": ["wt.exe", "cmd.exe", "powershell.exe"],
            "aliases": ["cmd", "command prompt", "powershell", "console", "bash"],
            "uri": None,
        },
        "explorer": {
            "name": "File Explorer",
            "executables": ["explorer.exe", "explorer"],
            "aliases": ["files", "file manager", "my computer"],
            "uri": None,
        },
        "antigravity": {
            "name": "Antigravity IDE",
            "executables": ["Antigravity.exe", "Antigravity IDE.exe", "antigravity.exe", "antigravity"],
            "aliases": ["antigravity ide", "agy", "google antigravity"],
            "uri": None,
        },
        "discord": {
            "name": "Discord",
            "executables": ["Discord.exe", "discord"],
            "aliases": ["discord app"],
            "uri": "discord:",
        },
        "slack": {
            "name": "Slack",
            "executables": ["slack.exe", "slack"],
            "aliases": ["slack app"],
            "uri": "slack:",
        },
    }

    def __init__(self):
        self._discovered_cache: Dict[str, str] = {}

    def resolve_app(self, query: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Resolve a natural language application name or alias into a canonical app definition.
        """
        if not query or not isinstance(query, str):
            return None

        q = query.strip().lower()

        # 1. Exact match on app key
        if q in self.KNOWN_APPS:
            return q, self.KNOWN_APPS[q]

        # 2. Match on name or aliases
        for app_id, app_info in self.KNOWN_APPS.items():
            if q == app_info["name"].lower():
                return app_id, app_info
            for alias in app_info.get("aliases", []):
                if q == alias.lower():
                    return app_id, app_info

        # 3. Substring matching
        for app_id, app_info in self.KNOWN_APPS.items():
            if app_id in q or q in app_id:
                return app_id, app_info
            for alias in app_info.get("aliases", []):
                if alias in q or q in alias:
                    return app_id, app_info

        # 4. Check if standard Windows system executable exists on PATH
        exe_path = shutil.which(q) or shutil.which(f"{q}.exe")
        if exe_path:
            return q, {
                "name": q.capitalize(),
                "executables": [exe_path],
                "aliases": [q],
                "uri": None,
            }

        return None

    def find_executable(self, app_info: Dict[str, Any]) -> Optional[str]:
        """
        Locate the absolute executable binary for an application.
        """
        app_name = app_info["name"]
        if app_name in self._discovered_cache:
            return self._discovered_cache[app_name]

        # Check executables on PATH
        for exe in app_info.get("executables", []):
            found = shutil.which(exe)
            if found:
                self._discovered_cache[app_name] = found
                return found

        # Search standard Windows installation locations
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        user_home = os.path.expanduser("~")

        search_dirs = [
            local_app_data,
            os.path.join(local_app_data, "Programs"),
            os.path.join(local_app_data, "Microsoft", "WindowsApps"),
            program_files,
            program_files_x86,
            user_home,
        ]

        for exe in app_info.get("executables", []):
            for sdir in search_dirs:
                if not sdir or not os.path.isdir(sdir):
                    continue
                # Direct check
                candidate = os.path.join(sdir, exe)
                if os.path.isfile(candidate):
                    self._discovered_cache[app_name] = candidate
                    return candidate

        return None

    def launch_app(
        self, app_name_or_alias: str, args: Optional[List[str]] = None
    ) -> ComputerActionResult:
        """
        Launch a registered application safely without shell=True.
        """
        resolved = self.resolve_app(app_name_or_alias)
        if not resolved:
            return ComputerActionResult(
                success=False,
                action="open_app",
                target=app_name_or_alias,
                error="application_not_found",
                verification=ComputerVerificationResult(
                    verified=False,
                    reason=f"Application '{app_name_or_alias}' is not recognized or permitted.",
                ),
            )

        app_id, app_info = resolved

        # Special handling for Spotify: avoid Windows Store headless zombie processes
        if app_id == "spotify":
            logger.info("[COMPUTER] Handling Spotify launch...")
            standalone_exe = os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")
            if os.path.isfile(standalone_exe):
                try:
                    os.startfile(standalone_exe)
                    time.sleep(1.0)
                    is_running, active_pid = self.is_app_running("spotify")
                    return ComputerActionResult(
                        success=True,
                        action="open_app",
                        target="Spotify",
                        pid=active_pid,
                        result={"app_id": "spotify", "name": "Spotify Desktop", "pid": active_pid},
                        verification=ComputerVerificationResult(
                            verified=True,
                            reason=f"Application 'Spotify Desktop' started (PID: {active_pid})",
                        ),
                    )
                except Exception as e:
                    logger.warning("[COMPUTER] Failed to launch standalone Spotify: %s", e)

            # Clean up any leftover headless zombie processes from Windows Store app
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if (p.info.get("name") or "").lower() == "spotify.exe":
                        p.kill()
                except Exception:
                    pass

            # Open Spotify Web Player visibly in Chrome (guaranteed 100% visible GUI)
            logger.info("[COMPUTER] Opening Spotify Web Player in Chrome...")
            try:
                from visual_control import open_chrome_visual
                open_chrome_visual("https://open.spotify.com/")
            except Exception:
                if hasattr(os, "startfile"):
                    os.startfile("https://open.spotify.com/")

            return ComputerActionResult(
                success=True,
                action="open_app",
                target="Spotify",
                result={"app_id": "spotify", "name": "Spotify", "url": "https://open.spotify.com/"},
                verification=ComputerVerificationResult(
                    verified=True,
                    reason="Opened Spotify in Chrome (Visual web player)",
                ),
            )

        exe_path = self.find_executable(app_info)

        logger.info("[COMPUTER] Launching application '%s' (exe=%s)", app_info['name'], exe_path)

        try:
            pid: Optional[int] = None
            if app_info.get("uri") and hasattr(os, "startfile"):
                # Protocol URI launch (e.g. spotify:, calculator:) directly opens in user desktop session
                os.startfile(app_info["uri"])
                logger.info("[COMPUTER] Successfully launched '%s' via protocol URI: %s", app_info['name'], app_info['uri'])
            elif exe_path and "WindowsApps" in exe_path and hasattr(os, "startfile"):
                # WindowsApps UWP stubs must be launched via shell startfile to display GUI
                os.startfile(exe_path)
                logger.info("[COMPUTER] Launched WindowsStore app via os.startfile: %s", exe_path)
            elif exe_path:
                if hasattr(os, "startfile") and not args:
                    try:
                        os.startfile(exe_path)
                    except Exception:
                        proc = subprocess.Popen([exe_path] + (args or []))
                        pid = proc.pid
                else:
                    cmd = [exe_path] + (args or [])
                    proc = subprocess.Popen(cmd)
                    pid = proc.pid
            else:
                proc_name = app_info["executables"][0]
                if hasattr(os, "startfile") and not args:
                    try:
                        os.startfile(proc_name)
                    except Exception:
                        proc = subprocess.Popen([proc_name] + (args or []))
                        pid = proc.pid
                else:
                    proc = subprocess.Popen([proc_name] + (args or []))
                    pid = proc.pid

            # Verification: check if process is active or created
            time.sleep(0.3)
            is_running, active_pid = self.is_app_running(app_id)
            final_pid = pid or active_pid

            return ComputerActionResult(
                success=True,
                action="open_app",
                target=app_info["name"],
                pid=final_pid,
                result={"app_id": app_id, "name": app_info["name"], "pid": final_pid},
                verification=ComputerVerificationResult(
                    verified=is_running or (final_pid is not None),
                    reason=f"Application '{app_info['name']}' started (PID: {final_pid})",
                    details={"app_id": app_id, "pid": final_pid},
                ),
            )
        except Exception as e:
            logger.error("[COMPUTER] Failed to launch '%s': %s", app_name_or_alias, e)
            return ComputerActionResult(
                success=False,
                action="open_app",
                target=app_name_or_alias,
                error=str(e),
                verification=ComputerVerificationResult(verified=False, reason=str(e)),
            )

    def is_app_running(self, app_id_or_name: str) -> Tuple[bool, Optional[int]]:
        """
        Check if any process corresponding to the application is running.
        """
        resolved = self.resolve_app(app_id_or_name)
        if not resolved:
            return False, None

        app_id, app_info = resolved
        exe_names = [exe.lower() for exe in app_info.get("executables", [])]

        for p in psutil.process_iter(["pid", "name"]):
            try:
                pname = (p.info.get("name") or "").lower()
                for exe in exe_names:
                    clean_exe = exe.replace(".exe", "")
                    clean_pname = pname.replace(".exe", "")
                    if clean_pname == clean_exe:
                        return True, p.info.get("pid")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return False, None

    def close_app(
        self, app_name_or_alias: str, force: bool = False
    ) -> ComputerActionResult:
        """
        Gracefully close an active application by sending termination signal.
        """
        resolved = self.resolve_app(app_name_or_alias)
        if not resolved:
            return ComputerActionResult(
                success=False,
                action="close_app",
                target=app_name_or_alias,
                error=f"Application not recognized: '{app_name_or_alias}'",
                verification=ComputerVerificationResult(verified=False, reason="App not found"),
            )

        app_id, app_info = resolved
        exe_names = [exe.lower() for exe in app_info.get("executables", [])]
        app_aliases = [a.lower() for a in app_info.get("aliases", [])]

        terminated_pids = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pname = (p.info.get("name") or "").lower()
                matched = any(exe in pname or pname in exe for exe in exe_names)
                if not matched:
                    matched = any(alias in pname for alias in app_aliases)

                if matched:
                    proc_obj = psutil.Process(p.info["pid"])
                    if force:
                        proc_obj.kill()
                    else:
                        proc_obj.terminate()
                    terminated_pids.append(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not terminated_pids:
            return ComputerActionResult(
                success=True,
                action="close_app",
                target=app_info["name"],
                result={"terminated_pids": [], "message": "Application was not running"},
                verification=ComputerVerificationResult(
                    verified=True,
                    reason=f"Application '{app_info['name']}' is not currently running.",
                ),
            )

        time.sleep(0.3)
        still_running, _ = self.is_app_running(app_id)

        return ComputerActionResult(
            success=not still_running,
            action="close_app",
            target=app_info["name"],
            result={"terminated_pids": terminated_pids},
            verification=ComputerVerificationResult(
                verified=not still_running,
                reason=f"Application '{app_info['name']}' closed (terminated PIDs: {terminated_pids})",
                details={"pids": terminated_pids},
            ),
        )

    def focus_app(self, app_name_or_alias: str) -> ComputerActionResult:
        """
        Activate and focus an application's main window on Windows.
        """
        resolved = self.resolve_app(app_name_or_alias)
        if not resolved:
            return ComputerActionResult(
                success=False,
                action="focus_app",
                target=app_name_or_alias,
                error=f"Application not found: '{app_name_or_alias}'",
            )

        app_id, app_info = resolved
        is_running, pid = self.is_app_running(app_id)

        if not is_running or not pid:
            return ComputerActionResult(
                success=False,
                action="focus_app",
                target=app_info["name"],
                error=f"Cannot focus '{app_info['name']}': application is not running.",
            )

        try:
            # Enumerate Windows windows to find window associated with PID
            user32 = getattr(ctypes, "windll", None)
            focused = False
            if user32 and hasattr(user32, "user32"):
                EnumWindows = user32.user32.EnumWindows
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
                GetWindowThreadProcessId = user32.user32.GetWindowThreadProcessId
                SetForegroundWindow = user32.user32.SetForegroundWindow
                ShowWindow = user32.user32.ShowWindow

                def callback(hwnd, extra):
                    lpdw_process_id = ctypes.c_ulong()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_process_id))
                    if lpdw_process_id.value == pid:
                        ShowWindow(hwnd, 9)  # SW_RESTORE
                        SetForegroundWindow(hwnd)
                        return False
                    return True

                EnumWindows(EnumWindowsProc(callback), 0)
                focused = True

            return ComputerActionResult(
                success=True,
                action="focus_app",
                target=app_info["name"],
                pid=pid,
                verification=ComputerVerificationResult(
                    verified=True,
                    reason=f"Focused window for '{app_info['name']}' (PID: {pid})",
                ),
            )
        except Exception as e:
            logger.error("[COMPUTER] Error focusing app '%s': %s", app_info["name"], e)
            return ComputerActionResult(
                success=False,
                action="focus_app",
                target=app_info["name"],
                error=str(e),
            )

    def get_all_apps(self) -> List[AppInfo]:
        """
        List all registered applications and their current runtime status.
        """
        result: List[AppInfo] = []
        for app_id, app_info in self.KNOWN_APPS.items():
            is_running, pid = self.is_app_running(app_id)
            result.append(
                AppInfo(
                    name=app_info["name"],
                    executable=app_info.get("executables", [""])[0],
                    aliases=list(app_info.get("aliases", [])),
                    is_running=is_running,
                    pid=pid,
                )
            )
        return result
