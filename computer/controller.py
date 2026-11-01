"""
Central Computer Controller for Paaro Computer Control (Step 9).
Coordinates application lifecycle, safe filesystem containment, URL opening, process supervision, and event dispatch.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .models import (
    AppInfo,
    ComputerAction,
    ComputerActionResult,
    ComputerActionType,
    ComputerVerificationResult,
    ProcessInfo,
    SystemStateInfo,
)
from .apps import ApplicationRegistry
from .filesystem import SafePathResolver
from .urls import SafeUrlOpener
from .processes import ProcessController
from ..config import PaaroSettings, settings

logger = logging.getLogger("paaro.computer.controller")


class ComputerController:
    """
    Unified Computer Control subsystem interface for Paaro.
    Executes safe, verified OS-level actions strictly through Tool Gateway and Policy Engine boundaries.
    """

    def __init__(
        self,
        config: Optional[PaaroSettings] = None,
        apps: Optional[ApplicationRegistry] = None,
        filesystem: Optional[SafePathResolver] = None,
        urls: Optional[SafeUrlOpener] = None,
        processes: Optional[ProcessController] = None,
    ):
        self.config = config or settings
        self.apps = apps or ApplicationRegistry()
        self.filesystem = filesystem or SafePathResolver(
            allowed_roots=self.config.COMPUTER_CONTROL_ALLOWED_ROOTS
        )
        self.urls = urls or SafeUrlOpener()
        self.processes = processes or ProcessController()
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

    def add_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _broadcast(self, event: Dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception as e:
                logger.error("[COMPUTER] Error dispatching event: %s", e)

    def execute_action(self, action: ComputerAction) -> ComputerActionResult:
        """
        Execute a structured ComputerAction and verify result.
        """
        t0 = time.time()
        atype = action.action_type
        if isinstance(atype, str):
            try:
                atype = ComputerActionType(atype.lower().strip())
            except ValueError:
                pass

        logger.info("[COMPUTER] Executing action '%s' with target '%s'", atype, action.target)
        self._broadcast({
            "type": "computer_action_started",
            "action": str(atype),
            "target": action.target,
            "timestamp": int(time.time() * 1000),
        })

        res: ComputerActionResult
        if atype == ComputerActionType.OPEN_APP:
            res = self.open_app(action.target, args=action.args.get("args"))
        elif atype == ComputerActionType.CLOSE_APP:
            res = self.close_app(action.target, force=bool(action.args.get("force", False)))
        elif atype == ComputerActionType.OPEN_FOLDER:
            res = self.open_folder(action.target or action.args.get("path", "."))
        elif atype == ComputerActionType.OPEN_FILE:
            res = self.open_file(action.target or action.args.get("path", ""))
        elif atype == ComputerActionType.OPEN_URL:
            res = self.open_url(action.target or action.args.get("url", ""))
        elif atype == ComputerActionType.START_PROCESS:
            res = self.start_process(action.target, args=action.args.get("args"), cwd=action.args.get("cwd"))
        elif atype == ComputerActionType.STOP_PROCESS:
            res = self.stop_process(action.target, pid=action.args.get("pid"), force=bool(action.args.get("force", False)))
        elif atype == ComputerActionType.CHECK_PROCESS:
            chk = self.check_process(action.target)
            res = ComputerActionResult(
                success=True,
                action="check_process",
                target=action.target,
                result=chk,
                verification=ComputerVerificationResult(
                    verified=True,
                    reason=f"Process check completed: running={chk['running']} (count={chk['count']})",
                    details=chk,
                ),
            )
        elif atype == ComputerActionType.GET_PROCESS_LIST:
            procs = self.get_process_list(
                max_count=int(action.args.get("max_count", self.config.COMPUTER_CONTROL_MAX_PROCESS_LIST)),
                filter_name=action.args.get("filter"),
            )
            res = ComputerActionResult(
                success=True,
                action="get_process_list",
                target=action.target,
                result={"processes": [p.to_dict() for p in procs], "count": len(procs)},
                verification=ComputerVerificationResult(
                    verified=True,
                    reason=f"Listed {len(procs)} active processes",
                ),
            )
        elif atype == ComputerActionType.FOCUS_APP:
            res = self.focus_app(action.target)
        elif atype == ComputerActionType.GET_SYSTEM_STATE:
            state = self.get_system_state()
            res = ComputerActionResult(
                success=True,
                action="get_system_state",
                target="system",
                result=state,
                verification=ComputerVerificationResult(
                    verified=True,
                    reason=f"System metrics captured (CPU: {state['cpu_percent']}%, Memory: {state['memory_percent']}%)",
                ),
            )
        else:
            res = ComputerActionResult(
                success=False,
                action=str(atype),
                target=action.target,
                error=f"Unsupported computer action: '{atype}'",
                verification=ComputerVerificationResult(verified=False, reason="Unsupported action"),
            )

        dur_ms = (time.time() - t0) * 1000.0
        ev_name = "computer_action_completed" if res.success else "computer_action_failed"
        self._broadcast({
            "type": ev_name,
            "action": res.action,
            "target": res.target,
            "success": res.success,
            "result": res.result,
            "error": res.error,
            "duration_ms": round(dur_ms, 2),
            "verification": res.verification.to_dict() if res.verification else None,
            "timestamp": int(time.time() * 1000),
        })

        return res

    # -----------------------------------------------------------------------
    # Direct Specific Action Handlers
    # -----------------------------------------------------------------------

    def open_app(self, app_name: str, args: Optional[List[str]] = None) -> ComputerActionResult:
        return self.apps.launch_app(app_name, args=args)

    def close_app(self, app_name: str, force: bool = False) -> ComputerActionResult:
        return self.apps.close_app(app_name, force=force)

    def focus_app(self, app_name: str) -> ComputerActionResult:
        return self.apps.focus_app(app_name)

    def open_folder(self, folder_path: str) -> ComputerActionResult:
        return self.filesystem.open_folder(folder_path)

    def open_file(self, file_path: str) -> ComputerActionResult:
        return self.filesystem.open_file(file_path)

    def open_url(self, url: str) -> ComputerActionResult:
        return self.urls.open_url(url)

    def start_process(
        self, service_name: str, args: Optional[List[str]] = None, cwd: Optional[str] = None
    ) -> ComputerActionResult:
        return self.processes.start_process(service_name, args=args, cwd=cwd)

    def stop_process(
        self, target_name_or_pid: str, pid: Optional[int] = None, force: bool = False
    ) -> ComputerActionResult:
        return self.processes.stop_process(target_name_or_pid, pid=pid, force=force)

    def check_process(self, target: str) -> Dict[str, Any]:
        return self.processes.check_process(target)

    def get_process_list(
        self, max_count: int = 50, filter_name: Optional[str] = None
    ) -> List[ProcessInfo]:
        return self.processes.get_process_list(max_count=max_count, filter_name=filter_name)

    def get_system_state(self) -> Dict[str, Any]:
        return self.processes.get_system_state().to_dict()
