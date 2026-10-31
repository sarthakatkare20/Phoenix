"""
Security and Emergency Stop subsystem for Paaro.
Ensures permission boundaries, session safety, and emergency halt capabilities.
"""

import threading
import time
from typing import Callable, List, Optional


class SecurityContext:
    """
    Thread-safe security monitor and emergency stop controller.
    """

    def __init__(self, initial_emergency_stop: bool = False):
        self._lock = threading.Lock()
        self._emergency_stop: bool = initial_emergency_stop
        self._listeners: List[Callable[[bool], None]] = []
        self._last_state_change: float = time.time()
        self._reason: Optional[str] = None

    @property
    def is_emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency_stop

    @property
    def halt_reason(self) -> Optional[str]:
        with self._lock:
            return self._reason

    def trigger_emergency_stop(self, reason: str = "Emergency stop triggered by operator") -> None:
        """
        Immediately trigger an emergency halt across all subsystems.
        """
        callbacks = []
        with self._lock:
            if not self._emergency_stop:
                self._emergency_stop = True
                self._reason = reason
                self._last_state_change = time.time()
                callbacks = list(self._listeners)

        # Notify callbacks outside lock to prevent deadlocks
        for cb in callbacks:
            try:
                cb(True)
            except Exception as e:
                # Log error or keep going; emergency stop must never fail
                pass

    def clear_emergency_stop(self, reason: str = "Emergency stop cleared") -> None:
        """
        Clear emergency stop and allow normal operations to resume.
        """
        callbacks = []
        with self._lock:
            if self._emergency_stop:
                self._emergency_stop = False
                self._reason = reason
                self._last_state_change = time.time()
                callbacks = list(self._listeners)

        for cb in callbacks:
            try:
                cb(False)
            except Exception:
                pass

    def add_emergency_listener(self, callback: Callable[[bool], None]) -> None:
        """
        Register a listener that is invoked whenever emergency stop state changes.
        """
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_emergency_listener(self, callback: Callable[[bool], None]) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)


# Global security context singleton
security_context = SecurityContext()
