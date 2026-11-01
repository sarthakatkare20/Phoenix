"""
Proactive Engine for Paaro (Step 7).
Background event consumer, queue manager, and realtime pipeline bridge.
"""

import asyncio
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .events import (
    EventSeverity,
    ProactiveDecision,
    ProactiveDecisionType,
    ProactiveEvent,
    UserActivityState,
)
from .event_bus import EventBus
from .evaluator import EventEvaluator
from .queue import ProactiveEventQueue
from .brain import ProactiveBrain
from ..config import PaaroSettings, settings

logger = logging.getLogger("paaro.proactive.engine")


class ProactiveEngine:
    """
    Main proactive system engine.
    Orchestrates the Event Bus, Bounded Priority Queue, Evaluator, and Proactive Brain.
    """

    def __init__(
        self,
        config: Optional[PaaroSettings] = None,
        event_bus: Optional[EventBus] = None,
        evaluator: Optional[EventEvaluator] = None,
        brain: Optional[ProactiveBrain] = None,
        queue: Optional[ProactiveEventQueue] = None,
        user_state_provider: Optional[Callable[[], UserActivityState]] = None,
    ):
        self.config = config or settings
        self.event_bus = event_bus or EventBus()
        
        min_sev = EventSeverity.LOW
        try:
            min_sev = EventSeverity(self.config.PROACTIVE_MIN_SEVERITY.lower())
        except Exception:
            pass

        self.evaluator = evaluator or EventEvaluator(
            min_severity=min_sev,
            default_cooldown_sec=self.config.PROACTIVE_DEFAULT_COOLDOWN_SEC,
        )
        self.brain = brain or ProactiveBrain(
            evaluator=self.evaluator,
            auto_speech=self.config.PROACTIVE_AUTO_SPEECH,
        )
        self.queue = queue or ProactiveEventQueue(max_size=self.config.PROACTIVE_QUEUE_SIZE)
        self.user_state_provider = user_state_provider or (lambda: UserActivityState.IDLE)

        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Connect event bus to engine handler
        self.event_bus.subscribe(self._on_bus_event)

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop = loop
        self.event_bus.set_async_loop(loop)

    def get_current_user_state(self) -> UserActivityState:
        try:
            return self.user_state_provider()
        except Exception:
            return UserActivityState.IDLE

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start proactive engine background queue processing loop."""
        if self._is_running:
            return

        self._is_running = True
        self._stop_event.clear()
        if loop:
            self.set_async_loop(loop)

        if self._async_loop and self._async_loop.is_running():
            self._worker_task = self._async_loop.create_task(self._queue_worker_loop())
            logger.info("ProactiveEngine background queue worker started.")

    def stop(self) -> None:
        """Stop background worker loop."""
        self._is_running = False
        self._stop_event.set()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        self._worker_task = None
        logger.info("ProactiveEngine stopped.")

    async def _on_bus_event(self, event: ProactiveEvent) -> None:
        """Internal callback invoked when any event is published on EventBus."""
        if not self.config.PROACTIVE_ENABLED:
            return

        user_state = self.get_current_user_state()
        decision = await self.brain.process_event(event, user_state=user_state)

        # If decision is DEFER, push to queue
        if decision.decision == ProactiveDecisionType.DEFER:
            enqueued = self.queue.push(event)
            if enqueued:
                logger.info(
                    "[PROACTIVE] Enqueued deferred event '%s' (queue depth: %d)",
                    event.event_type,
                    len(self.queue),
                )

    async def _queue_worker_loop(self) -> None:
        """Periodic worker to drain queued events when user returns to IDLE."""
        while self._is_running and not self._stop_event.is_set():
            try:
                await asyncio.sleep(1.0)
                if not self.config.PROACTIVE_ENABLED or len(self.queue) == 0:
                    continue

                user_state = self.get_current_user_state()
                if user_state == UserActivityState.IDLE:
                    # Pop highest priority non-expired event
                    event = self.queue.pop()
                    if event:
                        logger.info(
                            "[PROACTIVE] User is IDLE. Draining queued event '%s' (%s)",
                            event.event_type,
                            event.severity.value,
                        )
                        await self.brain.process_event(event, user_state=UserActivityState.IDLE)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in proactive queue worker: %s", e)

    # -------------------------------------------------------------------------
    # Convenience Emitter API
    # -------------------------------------------------------------------------

    def emit_event(self, event: ProactiveEvent) -> None:
        self.event_bus.publish(event)

    def emit_cpu_high(self, cpu_percent: float, duration_seconds: float = 120.0) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="cpu_high",
                source="system_monitor",
                severity=EventSeverity.MEDIUM,
                data={"cpu_percent": float(cpu_percent), "duration_seconds": float(duration_seconds)},
            )
        )

    def emit_memory_high(self, memory_percent: float, duration_seconds: float = 120.0) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="memory_high",
                source="system_monitor",
                severity=EventSeverity.MEDIUM,
                data={"memory_percent": float(memory_percent), "duration_seconds": float(duration_seconds)},
            )
        )

    def emit_disk_low(self, free_gb: float, mount: str = "C:") -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="disk_space_low",
                source="disk_monitor",
                severity=EventSeverity.MEDIUM if free_gb > 2.0 else EventSeverity.HIGH,
                data={"free_gb": float(free_gb), "mount": mount},
            )
        )

    def emit_process_crashed(self, process_name: str, exit_code: int = 1) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="process_crashed",
                source="process_watcher",
                severity=EventSeverity.HIGH,
                data={"process_name": process_name, "exit_code": exit_code},
            )
        )

    def emit_server_stopped(self, server_name: str, port: int = 8000, reason: str = "crashed") -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="server_stopped",
                source="dev_server",
                severity=EventSeverity.HIGH,
                data={"server_name": server_name, "port": port, "reason": reason},
            )
        )

    def emit_test_suite_completed(
        self, suite_name: str, total_tests: int, passed: int, duration_sec: float = 0.0
    ) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="test_suite_completed",
                source="test_runner",
                severity=EventSeverity.LOW,
                data={"suite_name": suite_name, "total_tests": total_tests, "passed": passed, "duration_sec": duration_sec},
            )
        )

    def emit_test_suite_failed(
        self, suite_name: str, failed: int, errors: int = 0, failure_details: str = ""
    ) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="test_suite_failed",
                source="test_runner",
                severity=EventSeverity.MEDIUM,
                data={"suite_name": suite_name, "failed": failed, "errors": errors, "failure_details": failure_details},
            )
        )

    def emit_build_completed(self, target: str, duration_sec: float = 0.0) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="build_completed",
                source="build_system",
                severity=EventSeverity.LOW,
                data={"target": target, "duration_sec": duration_sec},
            )
        )

    def emit_build_failed(self, target: str, error_message: str) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="build_failed",
                source="build_system",
                severity=EventSeverity.HIGH,
                data={"target": target, "error_message": error_message},
            )
        )

    def emit_download_completed(self, filename: str, size_mb: float = 0.0) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="download_completed",
                source="browser_downloader",
                severity=EventSeverity.LOW,
                data={"filename": filename, "size_mb": size_mb},
            )
        )

    def emit_download_failed(self, filename: str, error: str) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="download_failed",
                source="browser_downloader",
                severity=EventSeverity.MEDIUM,
                data={"filename": filename, "error": error},
            )
        )

    def emit_reminder(self, title: str, minutes_remaining: int = 5) -> None:
        self.emit_event(
            ProactiveEvent(
                event_type="reminder_approaching",
                source="calendar",
                severity=EventSeverity.MEDIUM,
                data={"title": title, "minutes_remaining": minutes_remaining},
            )
        )
