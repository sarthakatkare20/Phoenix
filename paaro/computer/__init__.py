"""
Paaro Computer Control Subsystem (Step 9).
Provides safe, deterministic, policy-governed local computer control.
"""

from .models import (
    ComputerActionType,
    ComputerAction,
    ComputerActionResult,
    ComputerVerificationResult,
    AppInfo,
    ProcessInfo,
    SystemStateInfo,
)
from .apps import ApplicationRegistry
from .filesystem import SafePathResolver
from .urls import SafeUrlOpener
from .processes import ProcessController
from .controller import ComputerController

# Default shared controller instance
computer_controller = ComputerController()

__all__ = [
    "ComputerActionType",
    "ComputerAction",
    "ComputerActionResult",
    "ComputerVerificationResult",
    "AppInfo",
    "ProcessInfo",
    "SystemStateInfo",
    "ApplicationRegistry",
    "SafePathResolver",
    "SafeUrlOpener",
    "ProcessController",
    "ComputerController",
    "computer_controller",
]
