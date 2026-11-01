"""
Unit and Integration tests for Paaro Realtime Streaming TTS Pipeline (Step 4).
"""

import asyncio
import time
import unittest
import numpy as np

from config import PaaroSettings
from security import SecurityContext
from text_chunker import TextChunker
from audio_playback import AudioPlaybackQueue
from kokoro_tts import (
    BaseTTSBackend,
    Pyttsx3Backend,
    KokoroONNXBackend,
    StreamingTTS,
)
from realtime_pipeline import RealtimeVoicePipeline
from streaming_llm import StreamingLLM


class MockTTSBackend(BaseTTSBackend):
    """Deterministic in-memory mock TTS backend for testing."""

    def __init__(self, synth_delay: float = 0.01):
        self.synth_delay = synth_delay
        self.synthesized_chunks = []

    def synthesize(self, text: str, voice: str = "mock", speed: float = 1.0):
        time.sleep(self.synth_delay)
        self.synthesized_chunks.append(text)
        sr = 24000
        # Generate short 50ms synthetic PCM tone
        duration_samples = int(sr * 0.05)
        samples = np.sin(2 * np.pi * 440 * np.arange(duration_samples) / sr).astype(np.float32) * 0.1
        return samples, sr


class TestTextChunker(unittest.TestCase):
    """Test text chunking and boundary detection rules."""

    def setUp(self):
        self.chunker = TextChunker(min_chars=10, max_chars=80)

    def test_single_sentence(self):
        chunks = self.chunker.feed("Hello world, this is a test.")
        self.assertEqual(chunks, ["Hello world, this is a test."])
        self.assertIsNone(self.chunker.flush())

    def test_incremental_streaming_tokens(self):
        tokens = ["Hey ", "Sarthak", ", I ", "can ", "help you ", "with that. ", "Let's ", "get started."]
        emitted = []
        for tok in tokens:
            chunks = self.chunker.feed(tok)
            emitted.extend(chunks)

        tail = self.chunker.flush()
        if tail:
            emitted.append(tail)

        # Min chars = 10, so split on comma and periods
        self.assertIn("Hey Sarthak,", emitted)
        self.assertIn("I can help you with that.", emitted)
        self.assertIn("Let's get started.", emitted)

    def test_newlines_and_punctuation(self):
        self.chunker.reset()
        c1 = self.chunker.feed("Line one is ready!\nLine two is here?")
        self.assertEqual(len(c1), 2)
        self.assertEqual(c1[0], "Line one is ready!")
        self.assertEqual(c1[1], "Line two is here?")

    def test_long_sentence_fallback_splitting(self):
        self.chunker = TextChunker(min_chars=10, max_chars=40)
        long_text = "This is a very long sentence without any punctuation that definitely exceeds forty chars."
        chunks = self.chunker.feed(long_text)
        tail = self.chunker.flush()
        if tail:
            chunks.append(tail)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 50)

    def test_empty_and_whitespace_only(self):
        self.assertEqual(self.chunker.feed(""), [])
        self.assertEqual(self.chunker.feed("   "), [])
        self.assertIsNone(self.chunker.flush())


class TestAudioPlaybackQueue(unittest.TestCase):
    """Test non-blocking audio queue FIFO ordering, metrics and cancellation."""

    def setUp(self):
        self.playback = AudioPlaybackQueue(sample_rate=24000, max_queue_size=10)

    def tearDown(self):
        self.playback.close()

    def test_enqueue_and_events(self):
        events = []
        self.playback.add_listener(events.append)

        chunk = np.zeros(240, dtype=np.float32)  # 10ms
        self.playback.enqueue(chunk, sample_rate=24000, metadata={"id": 1})
        self.playback.enqueue(chunk, sample_rate=24000, metadata={"id": 2})

        # Allow worker to process
        for _ in range(20):
            if any(e.get("type") == "tts_audio_chunk" for e in events):
                break
            time.sleep(0.05)

        event_types = [e.get("type") for e in events]
        self.assertIn("tts_audio_start", event_types)
        self.assertIn("tts_audio_chunk", event_types)

    def test_cancellation(self):
        events = []
        self.playback.add_listener(events.append)

        # Enqueue long chunk
        long_chunk = np.zeros(24000 * 2, dtype=np.float32)
        self.playback.enqueue(long_chunk)
        self.playback.enqueue(long_chunk)

        # Cancel immediately
        self.playback.cancel()
        self.assertEqual(self.playback.queue_depth, 0)
        self.assertFalse(self.playback.is_playing)

        event_types = [e.get("type") for e in events]
        self.assertIn("tts_cancelled", event_types)


class TestStreamingTTS(unittest.TestCase):
    """Test asynchronous synthesis worker and pipelined feed."""

    def setUp(self):
        self.config = PaaroSettings(
            TTS_ENABLED=True,
            TTS_CHUNK_MIN_CHARS=10,
            TTS_CHUNK_MAX_CHARS=80,
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

    def tearDown(self):
        self.tts.close()

    def test_pipelined_synthesis(self):
        events = []
        self.tts.add_listener(events.append)

        self.tts.on_llm_start()
        self.tts.feed_text_delta("First sentence is here. ")
        self.tts.feed_text_delta("Second sentence follows right after.")
        self.tts.flush_text()

        # Wait for worker synthesis
        time.sleep(0.2)

        self.assertIn("First sentence is here.", self.mock_backend.synthesized_chunks)
        self.assertIn("Second sentence follows right after.", self.mock_backend.synthesized_chunks)

        metrics = self.tts.get_metrics()
        self.assertGreaterEqual(metrics["total_chunks_synthesized"], 2)

    def test_cancellation_purges_queues(self):
        self.tts.on_llm_start()
        self.tts.feed_text_delta("This chunk will be cancelled before playing.")
        self.tts.cancel()

        self.assertEqual(self.tts.chunker.buffer, "")
        self.assertEqual(self.tts.get_metrics()["synth_queue_depth"], 0)

    def test_error_handling_in_synthesis(self):
        class BrokenBackend(BaseTTSBackend):
            def synthesize(self, text: str, voice: str = "", speed: float = 1.0):
                raise RuntimeError("Synthesizer GPU error")

        self.tts.backend = BrokenBackend()
        self.tts.on_llm_start()
        self.tts.feed_text_delta("Testing crash recovery.")
        self.tts.flush_text()

        time.sleep(0.05)
        # Should not raise uncaught exception
        self.assertTrue(self.tts._is_worker_running)


class TestRealtimePipelineTTSIntegration(unittest.TestCase):
    """Test full integration: Pipeline -> Streaming LLM -> Text Chunker -> TTS -> Playback Queue."""

    def setUp(self):
        self.config = PaaroSettings(
            VAD_ENABLED=False,
            STT_ENABLED=False,
            LLM_ENABLED=True,
            TTS_ENABLED=True,
        )
        self.security = SecurityContext()
        self.tts = StreamingTTS(config=self.config, security=self.security)
        self.mock_backend = MockTTSBackend(synth_delay=0.005)
        self.tts.backend = self.mock_backend

        self.pipeline = RealtimeVoicePipeline(
            config=self.config,
            security=self.security,
            tts=self.tts,
        )

    def tearDown(self):
        self.pipeline.stop()

    def test_llm_stream_to_tts_flow(self):
        async def run_simulated_stream():
            loop = asyncio.get_running_loop()
            self.pipeline.set_async_loop(loop)

            class MockStreamingLLM(StreamingLLM):
                async def stream_response(self, prompt: str, history=None):
                    chunks = [
                        "Hello there! ",
                        "I am Paaro, ",
                        "your personal assistant. ",
                        "How can I help you today?",
                    ]
                    for c in chunks:
                        await asyncio.sleep(0.01)
                        yield c

            self.pipeline.llm = MockStreamingLLM(config=self.config, security=self.security)
            await self.pipeline._process_llm_stream("introduce yourself")

        asyncio.run(run_simulated_stream())
        time.sleep(0.2)

        # Verify TTS synthesized chunks incrementally
        self.assertGreater(len(self.mock_backend.synthesized_chunks), 0)
        self.assertTrue(any("Hello there!" in c for c in self.mock_backend.synthesized_chunks))

    def test_emergency_stop_cancels_all(self):
        self.tts.on_llm_start()
        self.tts.feed_text_delta("Critical system status check in progress.")

        # Trigger emergency stop
        self.security.trigger_emergency_stop("Safety test stop")

        self.assertTrue(self.security.is_emergency_stopped)
        self.assertEqual(self.tts.chunker.buffer, "")
        self.assertEqual(self.tts.playback.queue_depth, 0)


if __name__ == "__main__":
    unittest.main()
