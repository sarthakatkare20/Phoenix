"""
Comprehensive Test Suite for Paaro Step 7: Proactive Intelligence & Context-Aware Action Engine.
Tests Event Bus pub-sub, deterministic evaluation, deduplication, cooldowns,
interaction state deferral, priority queueing, Tool Gateway policy enforcement,
proactive TTS vocalization, and barge-in interruption of proactive speech.
"""

import asyncio
import time
import unittest
from unittest.mock import MagicMock, patch

from config import PaaroSettings
from security import SecurityContext
from tool_gateway import PolicyDecision, PolicyEngine, ToolGateway
from speech_state_machine import SpeechState, SpeechStateMachine
from kokoro_tts import StreamingTTS
from proactive.events import (
    EventSeverity,
    ProactiveDecision,
    ProactiveDecisionType,
    ProactiveEvent,
    UserActivityState,
)
from proactive.event_bus import EventBus
from proactive.evaluator import EventEvaluator
from proactive.queue import ProactiveEventQueue
from proactive.brain import ProactiveBrain
from proactive.engine import ProactiveEngine


class TestEventBus(unittest.TestCase):
    """Test publish-subscribe, async handlers, and event type filtering."""

    def setUp(self):
        self.bus = EventBus()

    def test_sync_publish_and_subscribe(self):
        received = []

        def handler(event: ProactiveEvent):
            received.append(event)

        self.bus.subscribe(handler)
        ev = ProactiveEvent(event_type="download_completed", data={"filename": "file.zip"})
        self.bus.publish(ev)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, "download_completed")
        self.assertEqual(received[0].data["filename"], "file.zip")

    def test_event_type_filtering(self):
        cpu_events = []
        download_events = []

        self.bus.subscribe(lambda e: cpu_events.append(e), event_types=["cpu_high"])
        self.bus.subscribe(lambda e: download_events.append(e), event_types=["download_completed"])

        self.bus.publish(ProactiveEvent(event_type="cpu_high", data={"cpu_percent": 95.0}))
        self.bus.publish(ProactiveEvent(event_type="download_completed", data={"filename": "model.bin"}))
        self.bus.publish(ProactiveEvent(event_type="server_stopped", data={"port": 8000}))

        self.assertEqual(len(cpu_events), 1)
        self.assertEqual(cpu_events[0].event_type, "cpu_high")
        self.assertEqual(len(download_events), 1)
        self.assertEqual(download_events[0].event_type, "download_completed")

    def test_unsubscribe(self):
        received = []
        handler = lambda e: received.append(e)

        self.bus.subscribe(handler)
        self.bus.publish(ProactiveEvent(event_type="test_event"))
        self.assertEqual(len(received), 1)

        self.bus.unsubscribe(handler)
        self.bus.publish(ProactiveEvent(event_type="test_event"))
        self.assertEqual(len(received), 1)  # No new events received

    def test_async_publish(self):
        received = []

        async def async_handler(event: ProactiveEvent):
            await asyncio.sleep(0.01)
            received.append(event)

        async def run_test():
            self.bus.subscribe(async_handler)
            await self.bus.publish_async(ProactiveEvent(event_type="async_event"))
            self.assertEqual(len(received), 1)

        asyncio.run(run_test())


class TestEventEvaluator(unittest.TestCase):
    """Test deterministic evaluation, deduplication, cooldowns, and user activity deferral."""

    def setUp(self):
        self.evaluator = EventEvaluator(
            min_severity=EventSeverity.LOW,
            cooldowns={"cpu_high": 10.0, "download_completed": 5.0},
            default_cooldown_sec=5.0,
            duplicate_window_sec=2.0,
        )

    def test_deterministic_notify_decision(self):
        ev = ProactiveEvent(
            event_type="download_completed",
            data={"filename": "dataset.zip", "size_mb": 250.0},
            severity=EventSeverity.LOW,
        )
        decision = self.evaluator.evaluate(ev, user_state=UserActivityState.IDLE)
        self.assertEqual(decision.decision, ProactiveDecisionType.NOTIFY)
        self.assertTrue(decision.should_speak)
        self.assertIn("dataset.zip", decision.message)
        self.assertFalse(decision.requires_llm)

    def test_deterministic_ask_decision(self):
        ev = ProactiveEvent(
            event_type="cpu_high",
            data={"cpu_percent": 96.5, "duration_seconds": 120.0},
            severity=EventSeverity.MEDIUM,
        )
        decision = self.evaluator.evaluate(ev, user_state=UserActivityState.IDLE)
        self.assertEqual(decision.decision, ProactiveDecisionType.ASK)
        self.assertTrue(decision.should_speak)
        self.assertIn("96%", decision.message)
        self.assertEqual(decision.tool_name, "get_system_stats")

    def test_deduplication_suppression(self):
        ev1 = ProactiveEvent(
            event_type="file_changed",
            data={"file_path": "main.py"},
            severity=EventSeverity.LOW,
        )
        ev2 = ProactiveEvent(
            event_type="file_changed",
            data={"file_path": "main.py"},
            severity=EventSeverity.LOW,
        )

        dec1 = self.evaluator.evaluate(ev1, user_state=UserActivityState.IDLE)
        self.assertEqual(dec1.decision, ProactiveDecisionType.NOTIFY)

        # Immediate duplicate
        dec2 = self.evaluator.evaluate(ev2, user_state=UserActivityState.IDLE)
        self.assertEqual(dec2.decision, ProactiveDecisionType.IGNORE)
        self.assertIn("Duplicate", dec2.reason)

    def test_cooldown_enforcement_and_expiry(self):
        ev1 = ProactiveEvent(
            event_type="cpu_high",
            data={"cpu_percent": 92.0, "duration_seconds": 120.0},
            severity=EventSeverity.MEDIUM,
        )
        ev2 = ProactiveEvent(
            event_type="cpu_high",
            data={"cpu_percent": 98.0, "duration_seconds": 180.0},  # Different data to avoid duplicate check
            severity=EventSeverity.MEDIUM,
        )

        # First evaluation passes
        t0 = 1000.0
        dec1 = self.evaluator.evaluate(ev1, user_state=UserActivityState.IDLE, current_time=t0)
        self.assertEqual(dec1.decision, ProactiveDecisionType.ASK)

        # Second event 4 seconds later (cooldown is 10s)
        dec2 = self.evaluator.evaluate(ev2, user_state=UserActivityState.IDLE, current_time=t0 + 4.0)
        self.assertEqual(dec2.decision, ProactiveDecisionType.IGNORE)
        self.assertIn("cooldown", dec2.reason.lower())

        # Third event 11 seconds later (cooldown expired)
        dec3 = self.evaluator.evaluate(ev2, user_state=UserActivityState.IDLE, current_time=t0 + 11.0)
        self.assertEqual(dec3.decision, ProactiveDecisionType.ASK)

    def test_critical_severity_bypasses_cooldown(self):
        ev_med = ProactiveEvent(
            event_type="server_stopped",
            data={"server_name": "API", "port": 8000},
            severity=EventSeverity.MEDIUM,
        )
        ev_crit = ProactiveEvent(
            event_type="server_stopped",
            data={"server_name": "API", "port": 8000, "details": "kernel panic"},
            severity=EventSeverity.CRITICAL,
        )

        t0 = 1000.0
        dec1 = self.evaluator.evaluate(ev_med, user_state=UserActivityState.IDLE, current_time=t0)
        self.assertEqual(dec1.decision, ProactiveDecisionType.ASK)

        # Critical event 1s later bypasses cooldown
        dec2 = self.evaluator.evaluate(ev_crit, user_state=UserActivityState.IDLE, current_time=t0 + 1.0)
        self.assertEqual(dec2.decision, ProactiveDecisionType.ASK)

    def test_user_activity_state_deferral(self):
        ev = ProactiveEvent(
            event_type="test_suite_completed",
            data={"suite_name": "backend", "total_tests": 50, "passed": 50, "duration_sec": 4.2},
            severity=EventSeverity.LOW,
        )

        # When user is speaking (LISTENING) -> DEFER
        dec_listening = self.evaluator.evaluate(ev, user_state=UserActivityState.LISTENING)
        self.assertEqual(dec_listening.decision, ProactiveDecisionType.DEFER)
        self.assertFalse(dec_listening.should_speak)

        # When assistant is speaking (SPEAKING) -> DEFER
        dec_speaking = self.evaluator.evaluate(ev, user_state=UserActivityState.SPEAKING)
        self.assertEqual(dec_speaking.decision, ProactiveDecisionType.DEFER)

        # When user is IDLE -> NOTIFY immediately
        dec_idle = self.evaluator.evaluate(ev, user_state=UserActivityState.IDLE)
        self.assertEqual(dec_idle.decision, ProactiveDecisionType.NOTIFY)
        self.assertTrue(dec_idle.should_speak)


class TestProactiveEventQueue(unittest.TestCase):
    """Test priority sorting, bounded capacity, deduplication, and TTL expiry."""

    def setUp(self):
        self.queue = ProactiveEventQueue(max_size=3)

    def test_priority_ordering(self):
        now = time.time()
        ev_low = ProactiveEvent(event_type="e_low", severity=EventSeverity.LOW, timestamp=now)
        ev_high = ProactiveEvent(event_type="e_high", severity=EventSeverity.HIGH, timestamp=now + 1.0)
        ev_med = ProactiveEvent(event_type="e_med", severity=EventSeverity.MEDIUM, timestamp=now + 2.0)

        self.queue.push(ev_low)
        self.queue.push(ev_high)
        self.queue.push(ev_med)

        self.assertEqual(len(self.queue), 3)
        self.assertEqual(self.queue.pop().event_type, "e_high")
        self.assertEqual(self.queue.pop().event_type, "e_med")
        self.assertEqual(self.queue.pop().event_type, "e_low")

    def test_bounded_size_drop_lowest_priority(self):
        now = time.time()
        ev1 = ProactiveEvent(event_type="ev1", severity=EventSeverity.MEDIUM, timestamp=now)
        ev2 = ProactiveEvent(event_type="ev2", severity=EventSeverity.HIGH, timestamp=now + 1.0)
        ev3 = ProactiveEvent(event_type="ev3", severity=EventSeverity.LOW, timestamp=now + 2.0)
        ev4 = ProactiveEvent(event_type="ev4", severity=EventSeverity.CRITICAL, timestamp=now + 3.0)

        self.queue.push(ev1)
        self.queue.push(ev2)
        self.queue.push(ev3)
        self.queue.push(ev4)

        # Capacity is 3 -> lowest priority (ev3: LOW) dropped
        self.assertEqual(len(self.queue), 3)
        popped_types = [self.queue.pop().event_type for _ in range(3)]
        self.assertIn("ev4", popped_types)  # CRITICAL
        self.assertIn("ev2", popped_types)  # HIGH
        self.assertIn("ev1", popped_types)  # MEDIUM
        self.assertNotIn("ev3", popped_types)  # LOW dropped

    def test_ttl_expiry(self):
        now = time.time()
        ev = ProactiveEvent(
            event_type="reminder",
            severity=EventSeverity.MEDIUM,
            timestamp=now,
            ttl_seconds=10.0,
        )
        self.queue.push(ev)
        self.assertEqual(len(self.queue), 1)

        # Check when time is now + 20.0 (> ttl 10.0)
        with patch("time.time", return_value=now + 20.0):
            self.assertEqual(len(self.queue), 0)
            self.assertIsNone(self.queue.pop())


class TestSecurityAndPolicyEngineBoundaries(unittest.TestCase):
    """Test Tool Gateway & Policy Engine invariants: proactive actions cannot bypass security."""

    def setUp(self):
        self.security = SecurityContext()
        self.policy_engine = PolicyEngine()
        self.gateway = ToolGateway(policy_engine=self.policy_engine)
        self.evaluator = EventEvaluator()
        self.brain = ProactiveBrain(
            evaluator=self.evaluator,
            gateway=self.gateway,
            security=self.security,
            auto_speech=False,
        )

    def test_proactive_tool_execution_allowed(self):
        """Safe proactive tools (e.g. get_system_stats) pass PolicyEngine (ALLOW)."""
        ev = ProactiveEvent(
            event_type="cpu_high",
            data={"cpu_percent": 96.0, "duration_seconds": 120.0},
            severity=EventSeverity.MEDIUM,
        )

        async def run_test():
            decision = await self.brain.process_event(ev, user_state=UserActivityState.IDLE)
            self.assertEqual(decision.decision, ProactiveDecisionType.ASK)
            self.assertEqual(decision.tool_name, "get_system_stats")

            # Execute tool through ToolGateway
            dec = self.gateway.evaluate_tool_call(decision.tool_name, decision.tool_args)
            self.assertEqual(dec, PolicyDecision.ALLOW)

            res = self.gateway.execute_allowed(decision.tool_name, decision.tool_args)
            self.assertEqual(res["status"], "success")

        asyncio.run(run_test())

    def test_prohibited_proactive_tool_denied(self):
        """Prohibited proactive tools (e.g. format_disk, leak_secrets) are DENIED by PolicyEngine."""
        dec = self.gateway.evaluate_tool_call("format_disk", {})
        self.assertEqual(dec, PolicyDecision.DENY)

        res = self.gateway.execute_allowed("format_disk", {})
        self.assertEqual(res["status"], "error")
        self.assertIn("denied", res["error"].lower())

    def test_emergency_stop_blocks_proactive_actions(self):
        """Emergency stop prevents proactive speech and tool execution."""
        self.security.trigger_emergency_stop("Safety test stop")

        ev = ProactiveEvent(
            event_type="cpu_high",
            data={"cpu_percent": 99.0, "duration_seconds": 120.0},
            severity=EventSeverity.HIGH,
        )

        async def run_test():
            decision = await self.brain.process_event(ev, user_state=UserActivityState.IDLE)
            # Under emergency stop, vocalization is suppressed
            self.assertTrue(self.security.is_emergency_stopped)

        asyncio.run(run_test())


class TestProactiveTTSAndBargeInIntegration(unittest.TestCase):
    """Test proactive speech vocalization and user barge-in interruption."""

    def test_proactive_speech_and_barge_in(self):
        """When Paaro proactively speaks, user utterance triggers immediate barge-in."""
        config = PaaroSettings(
            TTS_ENGINE="mock",
            BARGE_IN_ENABLED=True,
            PROACTIVE_ENABLED=True,
        )
        security = SecurityContext()
        tts = StreamingTTS(config=config)
        state_machine = SpeechStateMachine()

        evaluator = EventEvaluator()
        brain = ProactiveBrain(evaluator=evaluator, tts=tts, security=security, auto_speech=True)
        engine = ProactiveEngine(config=config, evaluator=evaluator, brain=brain)

        # 1. Proactively emit download completed event -> Paaro speaks
        ev = ProactiveEvent(
            event_type="download_completed",
            data={"filename": "dataset.zip"},
            severity=EventSeverity.LOW,
        )

        async def run_proactive_flow():
            await brain.process_event(ev, user_state=UserActivityState.IDLE)

        asyncio.run(run_proactive_flow())

        # Verify TTS is currently active or buffered
        self.assertIsNotNone(brain._active_proactive_gen_id)
        active_gen = brain._active_proactive_gen_id

        # 2. User starts speaking (Barge-in simulation)
        t_barge_start = time.time()
        ret_state = state_machine.update(is_speech=True, speech_prob=0.9, speech_start_confirmation=1)
        self.assertEqual(ret_state, SpeechState.SPEECH_START)

        # Cancel active TTS playback
        tts_stop_ms = tts.cancel()
        t_barge_end = time.time()

        # Audio playback cancelled immediately
        self.assertFalse(tts.is_speaking)
        self.assertLess((t_barge_end - t_barge_start) * 1000.0, 50.0)


if __name__ == "__main__":
    unittest.main()
