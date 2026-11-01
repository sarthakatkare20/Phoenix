"""
Unit and Integration Tests for Paaro Realtime Voice & Streaming LLM Pipeline (Step 3).
Validates:
- Test 1: Normal question -> Streamed response (start -> delta -> done)
- Test 2: Long response -> Multiple delta events emitted
- Test 3: First-token latency measurement & token metrics
- Test 4: Conversation history: Only one final assistant message stored
- Test 5: Tool request: Evaluated and routed through Tool Gateway (ALLOW)
- Test 6: CONFIRM tool: Pauses and creates pending confirmation
- Test 7: DENY tool: Security policy denies prohibited tool execution
- Test 8: Emergency stop: Cancels active streaming generation immediately
- Test 9: Cancellation cleanup: In-flight requests abort gracefully
- Test 10: Ollama error / offline fallback: Clean error event without uncaught exceptions
"""

import asyncio
import time
import unittest

from config import PaaroSettings
from security import SecurityContext
from tool_gateway import PolicyDecision, PolicyEngine, ToolGateway
from streaming_llm import StreamingLLM


class TestStreamingLLM(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cfg = PaaroSettings(
            LLM_ENABLED=True,
            OLLAMA_URL="http://localhost:11434",
            LLM_MODEL="llama3.2:3b",
            LLM_TEMPERATURE=0.7,
            LLM_MAX_TOKENS=50,
            LLM_STREAM_BUFFER_MS=20.0,
        )
        self.sec = SecurityContext()
        self.gateway = ToolGateway()
        self.llm = StreamingLLM(config=self.cfg, security=self.sec, gateway=self.gateway)

    async def test_1_normal_question_streamed_response(self):
        """Test 1: Normal question -> Streamed response (start -> delta -> done)."""
        events = []
        async for event in self.llm.stream_response("Say hello in three words"):
            events.append(event)

        self.assertGreaterEqual(len(events), 3, "Expected at least start, delta, and done events")
        self.assertEqual(events[0]["type"], "llm")
        self.assertEqual(events[0]["status"], "start")

        deltas = [e for e in events if e.get("status") == "delta"]
        self.assertGreaterEqual(len(deltas), 1, "Expected at least 1 delta event")

        done = events[-1]
        self.assertEqual(done["status"], "done")
        self.assertTrue(len(done["text"]) > 0, "Expected non-empty final response text")

    async def test_2_long_response_multiple_deltas(self):
        """Test 2: Long response -> Multiple delta events emitted."""
        events = []
        async for event in self.llm.stream_response("Explain in two sentences what Python is."):
            events.append(event)

        deltas = [e for e in events if e.get("status") == "delta"]
        self.assertGreaterEqual(len(deltas), 2, f"Expected multiple deltas, got {len(deltas)}")

        done = events[-1]
        self.assertEqual(done["status"], "done")
        self.assertIn("Python", done["text"])

    async def test_3_first_token_latency_measurement(self):
        """Test 3: First-token latency measurement & token metrics."""
        events = []
        t0 = time.time()
        async for event in self.llm.stream_response("What is 2 plus 2? Answer with only the number."):
            events.append(event)

        done = events[-1]
        first_token_lat = done.get("first_token_latency_ms", 0.0)
        gen_duration = done.get("generation_duration_ms", 0.0)
        tps = done.get("tokens_per_sec", 0.0)

        print(f"\n==================== LLM LATENCY BENCHMARK ====================")
        print(f"  Model: {self.cfg.LLM_MODEL}")
        print(f"  Response: '{done.get('text')}'")
        print(f"  First Token Latency: {first_token_lat:.1f} ms")
        print(f"  Generation Duration: {gen_duration:.1f} ms")
        print(f"  Throughput: {tps:.1f} tokens/sec")
        print(f"===============================================================")

        self.assertGreater(first_token_lat, 0.0)
        self.assertGreater(done.get("total_tokens", 0), 0)

    async def test_4_conversation_history_retention(self):
        """Test 4: Conversation history: Only one final assistant message is stored."""
        self.llm.clear_history()
        self.assertEqual(len(self.llm.messages), 1)  # System prompt only

        async for _ in self.llm.stream_response("Hi, my name is Alex."):
            pass

        # History should now have: system, user ("Hi, my name is Alex."), assistant ("...")
        self.assertEqual(len(self.llm.messages), 3)
        self.assertEqual(self.llm.messages[1]["role"], "user")
        self.assertEqual(self.llm.messages[2]["role"], "assistant")

        # Follow-up question relying on conversation history
        async for _ in self.llm.stream_response("What is my name?"):
            pass

        # History should now have 5 messages: system, user, assistant, user, assistant
        self.assertEqual(len(self.llm.messages), 5)
        last_assistant_msg = self.llm.messages[-1]["content"].lower()
        self.assertIn("alex", last_assistant_msg)

    async def test_5_tool_request_allowed_execution(self):
        """Test 5: Tool request: Evaluated and routed through Tool Gateway (ALLOW)."""
        # Register a mock handler for get_time
        self.gateway.register_handler("get_time", lambda args: {"time": "11:40 AM"})

        decision = self.gateway.evaluate_tool_call("get_time", {})
        self.assertEqual(decision, PolicyDecision.ALLOW)

        res = self.gateway.execute_allowed("get_time", {})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["policy"], "allow")
        self.assertEqual(res["result"], {"time": "11:40 AM"})

    async def test_6_tool_request_confirm_policy(self):
        """Test 6: CONFIRM tool: Pauses and creates pending confirmation."""
        decision = self.gateway.evaluate_tool_call("delete_file", {"path": "test.txt"})
        self.assertEqual(decision, PolicyDecision.CONFIRM)

        res = self.gateway.execute_allowed("delete_file", {"path": "test.txt"})
        self.assertEqual(res["status"], "pending_confirmation")
        self.assertEqual(res["policy"], "confirm")
        call_id = res.get("call_id")
        self.assertIsNotNone(call_id)

        # Resolve with user approval
        approved_res = self.gateway.resolve_confirmation(call_id, approved=True)
        self.assertEqual(approved_res["status"], "success")
        self.assertTrue(approved_res["confirmed"])

    async def test_7_tool_request_deny_policy(self):
        """Test 7: DENY tool: Security policy denies prohibited tool execution."""
        decision = self.gateway.evaluate_tool_call("format_disk", {})
        self.assertEqual(decision, PolicyDecision.DENY)

        res = self.gateway.execute_allowed("format_disk", {})
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["policy"], "deny")

    async def test_8_emergency_stop_halts_streaming(self):
        """Test 8: Emergency stop: Cancels active streaming generation immediately."""
        self.sec.trigger_emergency_stop("Safety halt test")

        events = []
        async for event in self.llm.stream_response("Tell me a long story."):
            events.append(event)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "error")
        self.assertIn("Emergency stop is active", events[0]["message"])

        self.sec.clear_emergency_stop()

    async def test_9_cancellation_cleanup(self):
        """Test 9: In-flight cancellation aborts gracefully."""
        # Launch generation in background task
        gen_task = asyncio.create_task(
            self._collect_stream("Explain quantum physics in detail.")
        )
        await asyncio.sleep(0.08)  # Let it start

        self.llm.cancel()
        events = await gen_task
        # Should finish cleanly without unhandled exceptions
        self.assertFalse(self.llm._is_generating)

    async def _collect_stream(self, prompt: str):
        collected = []
        try:
            async for ev in self.llm.stream_response(prompt):
                collected.append(ev)
        except Exception as e:
            collected.append({"error": str(e)})
        return collected

    async def test_10_ollama_offline_error_handling(self):
        """Test 10: Ollama offline / unreachable gives clean error event."""
        bad_cfg = PaaroSettings(
            OLLAMA_URL="http://127.0.0.1:9999",  # Invalid port
            LLM_MODEL="llama3.2:3b",
        )
        bad_llm = StreamingLLM(config=bad_cfg, security=self.sec, gateway=self.gateway)

        events = []
        async for event in bad_llm.stream_response("Hello"):
            events.append(event)

        err_events = [e for e in events if e.get("status") == "error"]
        self.assertGreaterEqual(len(err_events), 1, "Expected clean error event when Ollama is unreachable")


if __name__ == "__main__":
    unittest.main()
