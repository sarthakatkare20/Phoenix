"""
Paaro Computer Control Subsystem (Step 9).
Provides safe, deterministic, policy-governed local computer control.
"""

from computer.models import (
    ComputerActionType,
    ComputerAction,
    ComputerActionResult,
    ComputerVerificationResult,
    AppInfo,
    ProcessInfo,
    SystemStateInfo,
)
from computer.apps import ApplicationRegistry
from computer.filesystem import SafePathResolver
from computer.urls import SafeUrlOpener
from computer.processes import ProcessController
from computer.controller import ComputerController

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
