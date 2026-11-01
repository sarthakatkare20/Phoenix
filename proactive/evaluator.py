"""
Deterministic Event Evaluator for Paaro Proactive Intelligence (Step 7).
Enforces deduplication, cooldowns, severity boundaries, user activity awareness,
and deterministic response templates without invoking LLM for standard events.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

from proactive.events import (
    EventSeverity,
    ProactiveDecision,
    ProactiveDecisionType,
    ProactiveEvent,
    UserActivityState,
)

logger = logging.getLogger("paaro.proactive.evaluator")

DEFAULT_COOLDOWNS: Dict[str, float] = {
    "cpu_high": 120.0,
    "memory_high": 120.0,
    "disk_space_low": 300.0,
    "process_crashed": 60.0,
    "server_stopped": 60.0,
    "test_suite_completed": 30.0,
    "test_suite_failed": 30.0,
    "build_completed": 30.0,
    "build_failed": 30.0,
    "file_created": 30.0,
    "file_changed": 30.0,
    "download_completed": 30.0,
    "download_failed": 30.0,
    "reminder_approaching": 60.0,
}


class EventEvaluator:
    """
    Deterministic evaluation engine filtering raw background events.
    Applies deduplication, cooldown checks, severity gating, and interaction state deferral.
    """

    def __init__(
        self,
        min_severity: EventSeverity = EventSeverity.LOW,
        cooldowns: Optional[Dict[str, float]] = None,
        default_cooldown_sec: float = 60.0,
        duplicate_window_sec: float = 15.0,
    ):
        self.min_severity = min_severity
        self.cooldowns: Dict[str, float] = dict(DEFAULT_COOLDOWNS)
        if cooldowns:
            self.cooldowns.update(cooldowns)
        self.default_cooldown_sec = default_cooldown_sec
        self.duplicate_window_sec = duplicate_window_sec

        self._lock = threading.Lock()
        self._last_triggered_by_type: Dict[str, float] = {}
        self._recent_fingerprints: Dict[str, float] = {}

    def set_cooldown(self, event_type: str, cooldown_sec: float) -> None:
        with self._lock:
            self.cooldowns[event_type] = max(0.0, cooldown_sec)

    def get_cooldown(self, event_type: str) -> float:
        with self._lock:
            return self.cooldowns.get(event_type, self.default_cooldown_sec)

    def reset_cooldowns(self) -> None:
        with self._lock:
            self._last_triggered_by_type.clear()
            self._recent_fingerprints.clear()

    def evaluate(
        self,
        event: ProactiveEvent,
        user_state: UserActivityState = UserActivityState.IDLE,
        current_time: Optional[float] = None,
    ) -> ProactiveDecision:
        """
        Evaluate an event deterministically.
        Returns ProactiveDecision (IGNORE, DEFER, NOTIFY, ASK, or ACT).
        """
        now = current_time or time.time()

        with self._lock:
            # 1. Clean up old fingerprint entries
            self._recent_fingerprints = {
                fp: ts
                for fp, ts in self._recent_fingerprints.items()
                if (now - ts) < self.duplicate_window_sec
            }

            # 2. Deduplication check
            fp = event.fingerprint()
            last_fp_time = self._recent_fingerprints.get(fp)
            if last_fp_time is not None and (now - last_fp_time) < self.duplicate_window_sec:
                logger.info("[PROACTIVE] event=%s deduplicated (fingerprint seen %.1fs ago)", event.event_type, now - last_fp_time)
                return ProactiveDecision(
                    decision=ProactiveDecisionType.IGNORE,
                    event=event,
                    reason=f"Duplicate event within {self.duplicate_window_sec}s window",
                    should_speak=False,
                )

            # 3. Severity Check (unless explicitly critical)
            if event.severity < self.min_severity and event.severity != EventSeverity.CRITICAL:
                logger.info("[PROACTIVE] event=%s ignored (severity %s < min %s)", event.event_type, event.severity.value, self.min_severity.value)
                return ProactiveDecision(
                    decision=ProactiveDecisionType.IGNORE,
                    event=event,
                    reason=f"Event severity ({event.severity.value}) below minimum threshold ({self.min_severity.value})",
                    should_speak=False,
                )

            # 4. Cooldown Check
            cooldown_dur = self.cooldowns.get(event.event_type, self.default_cooldown_sec)
            last_triggered = self._last_triggered_by_type.get(event.event_type)
            if last_triggered is not None and (now - last_triggered) < cooldown_dur:
                # Critical severity bypasses cooldown
                if event.severity != EventSeverity.CRITICAL:
                    remaining = cooldown_dur - (now - last_triggered)
                    logger.info("[PROACTIVE] event=%s on cooldown (remaining: %.1fs)", event.event_type, remaining)
                    return ProactiveDecision(
                        decision=ProactiveDecisionType.IGNORE,
                        event=event,
                        reason=f"Event type '{event.event_type}' on cooldown ({remaining:.1f}s remaining)",
                        should_speak=False,
                    )

            # 5. User Activity State Check (Defer if user or assistant is active, unless CRITICAL)
            if user_state in (
                UserActivityState.LISTENING,
                UserActivityState.SPEAKING,
                UserActivityState.THINKING,
                UserActivityState.BUSY,
            ):
                if event.severity != EventSeverity.CRITICAL:
                    logger.info("[PROACTIVE] event=%s deferred (user_state=%s)", event.event_type, user_state.value)
                    return ProactiveDecision(
                        decision=ProactiveDecisionType.DEFER,
                        event=event,
                        reason=f"User/Assistant is currently {user_state.value}; event deferred to queue",
                        should_speak=False,
                    )

            # Record fingerprint
            self._recent_fingerprints[fp] = now

        # 6. Generate Deterministic Decision & Message Template
        decision = self._generate_deterministic_decision(event)
        
        # If successfully decisioned to speak or act, update cooldown trigger time
        if decision.decision in (ProactiveDecisionType.NOTIFY, ProactiveDecisionType.ASK, ProactiveDecisionType.ACT):
            with self._lock:
                self._last_triggered_by_type[event.event_type] = now
            logger.info(
                "[PROACTIVE] event=%s severity=%s decision=%s should_speak=%s message='%s'",
                event.event_type,
                event.severity.value,
                decision.decision.value,
                decision.should_speak,
                decision.message,
            )

        return decision

    def _generate_deterministic_decision(self, event: ProactiveEvent) -> ProactiveDecision:
        """Generate deterministic messages and actions for known event types."""
        etype = event.event_type.lower().strip()
        data = event.data or {}

        # If event explicitly requires LLM reasoning
        if event.requires_llm:
            return ProactiveDecision(
                decision=ProactiveDecisionType.ASK,
                event=event,
                reason="Event flagged for LLM contextual reasoning",
                should_speak=True,
                requires_llm=True,
            )

        # 1. System Events
        if etype == "cpu_high":
            cpu = data.get("cpu_percent", 90.0)
            dur = data.get("duration_seconds", 120.0)
            msg = f"Sarthak, your CPU has been running above {cpu:.0f}% for the last {int(dur)} seconds. Want me to check what is causing it?"
            return ProactiveDecision(
                decision=ProactiveDecisionType.ASK,
                event=event,
                message=msg,
                tool_name="get_system_stats",
                tool_args={},
                reason="High CPU usage detected persistently",
                should_speak=True,
            )

        if etype == "memory_high":
            mem = data.get("memory_percent", 90.0)
            msg = f"Your memory usage is currently at {mem:.0f}%. Would you like me to check active memory processes?"
            return ProactiveDecision(
                decision=ProactiveDecisionType.ASK,
                event=event,
                message=msg,
                tool_name="get_system_stats",
                tool_args={},
                reason="High RAM usage detected",
                should_speak=True,
            )

        if etype == "disk_space_low":
            free_gb = data.get("free_gb", 5.0)
            mount = data.get("mount", "C:")
            msg = f"Disk space is running low on drive {mount} with only {free_gb:.1f} GB remaining."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Low disk space threshold reached",
                should_speak=True,
            )

        if etype == "process_crashed":
            pname = data.get("process_name", "Application")
            code = data.get("exit_code", 1)
            msg = f"Process {pname} crashed unexpectedly with exit code {code}. Want me to restart it?"
            return ProactiveDecision(
                decision=ProactiveDecisionType.ASK,
                event=event,
                message=msg,
                tool_name="open_app",
                tool_args={"app_name": pname},
                reason=f"Process {pname} crash detected",
                should_speak=True,
            )

        # 2. Development Events
        if etype == "server_stopped":
            sname = data.get("server_name", "Backend server")
            port = data.get("port", 8000)
            msg = f"Your {sname} on port {port} stopped. Would you like me to restart it?"
            return ProactiveDecision(
                decision=ProactiveDecisionType.ASK,
                event=event,
                message=msg,
                tool_name="open_app",
                tool_args={"target": sname},
                reason="Development server stopped",
                should_speak=True,
            )

        if etype == "test_suite_completed":
            suite = data.get("suite_name", "Test suite")
            total = data.get("total_tests", 0)
            dur = data.get("duration_sec", 0.0)
            msg = f"All {total} tests in {suite} passed successfully in {dur:.1f} seconds."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Test suite completed successfully",
                should_speak=True,
            )

        if etype == "test_suite_failed":
            suite = data.get("suite_name", "Test suite")
            failed = data.get("failed", 1)
            msg = f"{failed} tests failed in {suite}."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Test suite failure detected",
                should_speak=True,
            )

        if etype == "build_completed":
            target = data.get("target", "Project")
            dur = data.get("duration_sec", 0.0)
            msg = f"Build for {target} completed successfully in {dur:.1f} seconds."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Build completed successfully",
                should_speak=True,
            )

        if etype == "build_failed":
            target = data.get("target", "Project")
            err = data.get("error_message", "Unknown error")
            msg = f"Build for {target} failed: {err}."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Build failure detected",
                should_speak=True,
            )

        # 3. File Events
        if etype == "file_created":
            fpath = data.get("file_path", "file")
            msg = f"New file created at {fpath}."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="File creation detected",
                should_speak=True,
            )

        if etype == "file_changed":
            fpath = data.get("file_path", "file")
            msg = f"File modified: {fpath}."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="File change detected",
                should_speak=True,
            )

        # 4. Download Events
        if etype == "download_completed":
            fname = data.get("filename", "your file")
            msg = f"Your download of {fname} has finished."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Download completed",
                should_speak=True,
            )

        if etype == "download_failed":
            fname = data.get("filename", "file")
            err = data.get("error", "network error")
            msg = f"The download for {fname} failed: {err}."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Download failure",
                should_speak=True,
            )

        # 5. Time-based Events
        if etype == "reminder_approaching":
            title = data.get("title", "Event")
            mins = data.get("minutes_remaining", 5)
            msg = f"Reminder: {title} is starting in {mins} minutes."
            return ProactiveDecision(
                decision=ProactiveDecisionType.NOTIFY,
                event=event,
                message=msg,
                reason="Upcoming scheduled reminder",
                should_speak=True,
            )

        # Generic fallback
        summary = data.get("message") or f"Event {etype} received from {event.source}."
        return ProactiveDecision(
            decision=ProactiveDecisionType.NOTIFY,
            event=event,
            message=summary,
            reason="Generic event notification",
            should_speak=True,
        )
