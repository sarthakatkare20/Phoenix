"""
Data models and Enums for Paaro Computer Control Subsystem (Step 9).
Defines structured actions, execution results, application registry data, and system state info.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class ComputerActionType(str, Enum):
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    OPEN_FOLDER = "open_folder"
    OPEN_FILE = "open_file"
    OPEN_URL = "open_url"
    START_PROCESS = "start_process"
    STOP_PROCESS = "stop_process"
    GET_PROCESS_LIST = "get_process_list"
    CHECK_PROCESS = "check_process"
    FOCUS_APP = "focus_app"
    GET_SYSTEM_STATE = "get_system_state"


@dataclass
class ComputerAction:
    action_type: ComputerActionType
    target: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    verify: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value if isinstance(self.action_type, ComputerActionType) else self.action_type,
            "target": self.target,
            "args": self.args,
            "verify": self.verify,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ComputerAction":
        atype_val = d.get("action_type") or d.get("action", "")
        try:
            atype = ComputerActionType(atype_val.lower().strip())
        except ValueError:
            atype = ComputerActionType.OPEN_APP

        return cls(
            action_type=atype,
            target=str(d.get("target", "")),
            args=dict(d.get("args", {})),
            verify=bool(d.get("verify", True)),
        )


@dataclass
class ComputerVerificationResult:
    verified: bool
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "reason": self.reason,
            "details": self.details,
        }


@dataclass
class ComputerActionResult:
    success: bool
    action: str
    target: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
    pid: Optional[int] = None
    verification: Optional[ComputerVerificationResult] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "target": self.target,
            "result": self.result,
            "error": self.error,
            "pid": self.pid,
            "verification": self.verification.to_dict() if self.verification else None,
            "timestamp": int(self.timestamp * 1000),
        }


@dataclass
class AppInfo:
    name: str
    executable: str
    aliases: List[str] = field(default_factory=list)
    is_running: bool = False
    pid: Optional[int] = None
    window_title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "executable": self.executable,
            "aliases": list(self.aliases),
            "is_running": self.is_running,
            "pid": self.pid,
            "window_title": self.window_title,
        }


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    status: str = "running"
    cmdline: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_mb": round(self.memory_mb, 2),
            "status": self.status,
            "cmdline": self.cmdline,
        }


@dataclass
class SystemStateInfo:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    battery_percent: Optional[float] = None
    battery_plugged: Optional[bool] = None
    active_window: Optional[str] = None
    running_app_count: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_percent": round(self.memory_percent, 2),
            "memory_used_gb": round(self.memory_used_gb, 2),
            "memory_total_gb": round(self.memory_total_gb, 2),
            "battery_percent": self.battery_percent,
            "battery_plugged": self.battery_plugged,
            "active_window": self.active_window,
            "running_app_count": self.running_app_count,
            "timestamp": int(self.timestamp * 1000),
        }
