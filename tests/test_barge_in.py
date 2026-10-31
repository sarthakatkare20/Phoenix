"""
Unit and Integration tests for Paaro Barge-in and Interruption Handling (Step 5).
"""

import asyncio
import time
import unittest
import numpy as np

from paaro.config import PaaroSettings
from paaro.security import SecurityContext
from paaro.speech_state_machine import SpeechState, SpeechStateMachine
from paaro.audio_playback import AudioPlaybackQueue
from paaro.kokoro_tts import BaseTTSBackend, StreamingTTS
from paaro.streaming_llm import StreamingLLM
from paaro.realtime_pipeline import RealtimeVoicePipeline


class MockTTSBackend(BaseTTSBackend):
    """Deterministic in-memory mock TTS backend for barge-in testing."""

    def __init__(self, synth_delay: float = 0.01):
        self.synth_delay = synth_delay
        self.synthesized_chunks = []

    def synthesize(self, text: str, voice: str = "mock", speed: float = 1.0):
        time.sleep(self.synth_delay)
        self.synthesized_chunks.append(text)
        sr = 24000
        duration_samples = int(sr * 0.1)  # 100ms tone
        samples = np.sin(2 * np.pi * 440 * np.arange(duration_samples) / sr).astype(np.float32) * 0.1
        return samples, sr


class TestBargeInPipeline(unittest.TestCase):
    """Test suite for Step 5 Barge-in and Interruption handling."""

    def setUp(self):
        self.config = PaaroSettings(
            VAD_ENABLED=False,
            STT_ENABLED=False,
            LLM_ENABLED=True,
            TTS_ENABLED=True,
            BARGE_IN_ENABLED=True,
            BARGE_IN_THRESHOLD=0.65,
            BARGE_IN_CONFIRMATION_FRAMES=3,
            BARGE_IN_GRACE_PERIOD_MS=50.0,
            BARGE_IN_MIN_ENERGY=0.005,
        )
        self.security = SecurityContext()
        self.playback = AudioPlaybackQueue(sample_rate=24000)
        self.tts = StreamingTTS(
            config=self.config,
            security=self.security,
            playback_queue=self.playback,
        )
        self.mock_backend = MockTTSBackend(synth_delay=0.01)
        self.tts.backend = self.mock_backend

        self.pipeline = RealtimeVoicePipeline(
            config=self.config,
            security=self.security,
            tts=self.tts,
        )

    def tearDown(self):
        self.pipeline.stop()
        self.tts.close()

    def test_1_state_transition_speaking_to_barge_in(self):
        """Test 1: User speaks while assistant is speaking -> Barge-in triggered -> Paaro stops."""
        events = []
        self.pipeline.add_event_listener(events.append)

        # Simulate Assistant Speaking
        self.tts.on_llm_start(generation_id="gen-1")
        self.tts.feed_text_delta("Paaro is currently explaining system statistics.", generation_id="gen-1")
        self.tts.flush_text(generation_id="gen-1")

        # Allow synthesis to queue into playback
        time.sleep(0.05)
        self.assertTrue(self.pipeline.is_assistant_speaking)

        # Simulate confirmed user speech start
        self.pipeline._on_state_machine_event(SpeechState.SPEECH_START, time.time(), {"prob": 0.85})

        # Verify barge-in event emitted and speech stopped
        event_types = [e.get("type") for e in events]
        self.assertIn("barge_in_detected", event_types)
        self.assertIn("generation_invalidated", event_types)
        self.assertFalse(self.pipeline.is_assistant_speaking)
        self.assertEqual(self.tts.playback.queue_depth, 0)

    def test_2_tts_cancellation_purges_everything(self):
        """Test 2: TTS cancellation immediately clears synth queue, text buffer, and active audio."""
        self.tts.on_llm_start(generation_id="gen-100")
        self.tts.feed_text_delta("Long pending sentence that should not be spoken.", generation_id="gen-100")

        # Instant cancel
        stop_ms = self.tts.cancel()
        self.assertGreaterEqual(stop_ms, 0.0)
        self.assertEqual(self.tts.chunker.buffer, "")
        self.assertEqual(self.tts.get_metrics()["synth_queue_depth"], 0)
        self.assertEqual(self.tts.playback.queue_depth, 0)
        self.assertIsNone(self.tts.active_generation_id)

    def test_3_llm_cancellation_halts_stream(self):
        """Test 3: LLM generation is cancelled and sets generation_id to empty."""
        llm = StreamingLLM(config=self.config, security=self.security)
        
        async def run_llm():
            stream = llm.stream_response("test prompt")
            first = await stream.__anext__()
            gen_id = first.get("generation_id")
            self.assertEqual(llm.current_generation_id, gen_id)
            
            # Cancel mid-generation
            cancelled_id = llm.cancel()
            self.assertEqual(cancelled_id, gen_id)
            self.assertEqual(llm.current_generation_id, "")
            self.assertTrue(llm._current_cancel_event.is_set())

        asyncio.run(run_llm())

    def test_4_generation_invalidation_discards_stale_tokens(self):
        """Test 4: Late tokens from cancelled generation are discarded and do not reach TTS."""
        self.tts.on_llm_start(generation_id="gen-A")
        self.tts.feed_text_delta("Valid text chunk A.", generation_id="gen-A")

        # Cancel generation A
        self.tts.cancel()

        # Start generation B
        self.tts.on_llm_start(generation_id="gen-B")
        
        # Late token arriving from generation A
        self.tts.feed_text_delta("Late lingering token from generation A.", generation_id="gen-A")
        
        # Token from generation B
        self.tts.feed_text_delta("Valid token from generation B.", generation_id="gen-B")
        self.tts.flush_text(generation_id="gen-B")

        # Wait for worker
        time.sleep(0.08)

        metrics = self.tts.get_metrics()
        self.assertGreaterEqual(metrics["stale_token_discard_count"], 1)
        self.assertIn("Valid token from generation B.", self.mock_backend.synthesized_chunks)
        self.assertNotIn("Late lingering token from generation A.", self.mock_backend.synthesized_chunks)

    def test_5_stale_audio_discarded(self):
        """Test 5: Audio chunk with outdated generation ID is dropped by playback queue."""
        chunk = np.zeros(240, dtype=np.float32)
        self.playback.set_generation_id("gen-NEW")

        # Enqueue chunk from old generation
        self.playback.enqueue(chunk, generation_id="gen-OLD")
        self.assertEqual(self.playback.queue_depth, 0)
        self.assertGreaterEqual(self.playback.get_metrics()["stale_audio_discard_count"], 1)

    def test_6_false_vad_short_noise_rejection_during_speaking(self):
        """Test 6: Short click / low energy noise while speaking does NOT trigger barge-in."""
        sm = SpeechStateMachine(
            speech_start_confirmation=3,
            frame_duration_sec=0.032,
        )

        # 1 frame noise (pop/click) with confirmation threshold = 4
        state = sm.update(is_speech=True, speech_prob=0.7, speech_start_confirmation=4)
        self.assertEqual(state, SpeechState.IDLE)

        # Next frame is silence
        state = sm.update(is_speech=False, speech_prob=0.1, speech_start_confirmation=4)
        self.assertEqual(state, SpeechState.IDLE)
        self.assertEqual(sm._consecutive_speech_frames, 0)

    def test_7_confirmed_user_speech_triggers_barge_in(self):
        """Test 7: Sustained user speech (>= confirmation frames) confirms SPEECH_START."""
        sm = SpeechStateMachine(
            speech_start_confirmation=3,
            frame_duration_sec=0.032,
        )

        # 4 consecutive speech frames
        for i in range(3):
            state = sm.update(is_speech=True, speech_prob=0.8, speech_start_confirmation=4)
            self.assertEqual(state, SpeechState.IDLE)

        # 4th frame triggers confirmed speech start
        state = sm.update(is_speech=True, speech_prob=0.8, speech_start_confirmation=4)
        self.assertEqual(state, SpeechState.SPEECH_START)
        self.assertEqual(sm.current_state, SpeechState.SPEAKING)

    def test_8_rapid_repeated_interruptions(self):
        """Test 8: Rapid repeated barge-in cycles do not deadlock or crash."""
        for cycle in range(5):
            gen_id = f"gen-cycle-{cycle}"
            self.tts.on_llm_start(generation_id=gen_id)
            self.tts.feed_text_delta(f"Cycle {cycle} sentence text.", generation_id=gen_id)
            
            # Immediately interrupt
            self.pipeline._on_state_machine_event(SpeechState.SPEECH_START, time.time(), {"prob": 0.9})
            self.assertFalse(self.pipeline.is_assistant_speaking)

        metrics = self.pipeline.get_barge_in_metrics()
        self.assertEqual(metrics["barge_in_count"], 5)

    def test_9_emergency_stop_halts_everything(self):
        """Test 9: Emergency stop halts active LLM, TTS, playback, and state machine."""
        self.tts.on_llm_start(generation_id="gen-emerg")
        self.tts.feed_text_delta("Critical system status check.", generation_id="gen-emerg")

        # Trigger Emergency Stop
        self.security.trigger_emergency_stop("Safety test stop")

        self.assertTrue(self.security.is_emergency_stopped)
        self.assertFalse(self.pipeline.is_assistant_speaking)
        self.assertEqual(self.tts.playback.queue_depth, 0)


if __name__ == "__main__":
    unittest.main()
