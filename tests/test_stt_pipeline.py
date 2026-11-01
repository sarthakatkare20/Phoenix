"""
Unit and Integration Tests for Paaro Realtime Voice & Streaming STT Pipeline (Step 2).
Validates:
- Test 1: Silence -> No transcript
- Test 2: Simple utterance ("Hello Jarvis") produces one final transcript
- Test 3: Longer utterance ("Hey Jarvis open Chrome and search YouTube") produces one final transcript
- Test 4: Partial transcript updates emitted while speaking
- Test 5: Final transcript emitted exactly once after SPEECH_END
- Test 6: Short pause does NOT prematurely finalize transcript
- Test 7: Silence after speech triggers final transcription
- Test 8: Emergency stop cancels/resets pending STT
- Test 9: No duplicate final transcripts
- Test 10: Performance / latency benchmarks (speech_start -> first_partial, speech_end -> final)
"""

import os
import tempfile
import time
import unittest
import numpy as np
import pyttsx3
import scipy.signal
import soundfile as sf
from faster_whisper import WhisperModel

from config import PaaroSettings
from security import SecurityContext
from speech_state_machine import SpeechState
from streaming_stt import StreamingSTT
from realtime_pipeline import RealtimeVoicePipeline

_SHARED_MODEL = None


def get_shared_whisper_model():
    global _SHARED_MODEL
    if _SHARED_MODEL is None:
        _SHARED_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _SHARED_MODEL


def synthesize_speech_pcm16(text: str, target_sr: int = 16000) -> np.ndarray:
    """Helper to synthesize realistic speech audio for unit testing."""
    engine = pyttsx3.init()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    try:
        engine.save_to_file(text, tmp_path)
        engine.runAndWait()
        audio, sr = sf.read(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if audio.ndim > 1:
        audio = audio[:, 0]

    if sr != target_sr:
        num_target_samples = int(len(audio) * target_sr / sr)
        audio = scipy.signal.resample(audio, num_target_samples)

    return audio.astype(np.float32)


class TestStreamingSTT(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared_model = get_shared_whisper_model()

    def setUp(self):
        self.cfg = PaaroSettings(
            STT_ENABLED=True,
            WHISPER_MODEL_SIZE="base",
            WHISPER_DEVICE="cpu",
            WHISPER_COMPUTE_TYPE="int8",
            STT_UPDATE_INTERVAL=0.3,
            STT_LANGUAGE="en",
        )
        self.stt = StreamingSTT(config=self.cfg, model=self.shared_model)
        self.events = []
        self.stt.add_listener(lambda ev: self.events.append(ev))

    def tearDown(self):
        self.stt.close()

    def wait_for_final(self, timeout: float = 5.0):
        """Wait for worker thread to process final transcript."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            finals = [e for e in self.events if e.get("status") == "final"]
            if len(finals) > 0:
                self.stt.wait_idle(timeout=1.0)
                return [e for e in self.events if e.get("status") == "final"]
            time.sleep(0.05)
        return [e for e in self.events if e.get("status") == "final"]

    def test_1_silence_produces_no_transcript(self):
        """Test 1: Silence -> No transcript."""
        silence_frame = np.zeros(512, dtype=np.float32)
        for _ in range(10):
            self.stt.feed_audio(silence_frame)
        time.sleep(0.1)

        self.assertEqual(len(self.events), 0, "Silence should not generate transcripts")

    def test_2_simple_utterance_final_transcript(self):
        """Test 2: Simple utterance produces exactly one final transcript."""
        audio = synthesize_speech_pcm16("Hello Jarvis")
        chunks = [audio[i : i + 512] for i in range(0, len(audio), 512)]

        t_start = time.time()
        self.stt.on_speech_start(t_start)

        for chunk in chunks:
            self.stt.feed_audio(chunk)

        t_end = time.time()
        self.stt.on_speech_end(t_end)

        final_events = self.wait_for_final(timeout=5.0)
        self.assertEqual(len(final_events), 1, f"Expected exactly 1 final event, got {len(final_events)}")
        final_text = final_events[0].get("text", "").lower()
        self.assertTrue("hello" in final_text or "jarvis" in final_text, f"Unexpected text: {final_text}")

    def test_3_longer_utterance_final_transcript(self):
        """Test 3: Longer utterance produces one final transcript."""
        audio = synthesize_speech_pcm16("Hey Jarvis open Chrome and search YouTube")
        chunks = [audio[i : i + 512] for i in range(0, len(audio), 512)]

        t_start = time.time()
        self.stt.on_speech_start(t_start)

        for chunk in chunks:
            self.stt.feed_audio(chunk)

        t_end = time.time()
        self.stt.on_speech_end(t_end)

        final_events = self.wait_for_final(timeout=5.0)
        self.assertEqual(len(final_events), 1)
        final_text = final_events[0].get("text", "").lower()
        self.assertTrue("chrome" in final_text or "youtube" in final_text or "jarvis" in final_text, f"Text: {final_text}")

    def test_4_partial_transcript_updates_while_speaking(self):
        """Test 4: Partial transcript updates emitted while speaking."""
        self.stt.update_interval = 0.2
        audio = synthesize_speech_pcm16("Hey Jarvis what is the weather today in London")
        chunks = [audio[i : i + 512] for i in range(0, len(audio), 512)]

        t_start = time.time()
        self.stt.on_speech_start(t_start)

        # Feed first half of chunks
        mid = len(chunks) // 2
        for chunk in chunks[:mid]:
            self.stt.feed_audio(chunk)

        # Allow partial inference to complete
        deadline = time.time() + 4.0
        while time.time() < deadline:
            partial_events = [e for e in self.events if e.get("status") == "partial"]
            if partial_events:
                break
            time.sleep(0.05)

        # Feed remaining chunks
        for chunk in chunks[mid:]:
            self.stt.feed_audio(chunk)

        t_end = time.time()
        self.stt.on_speech_end(t_end)

        final_events = self.wait_for_final(timeout=5.0)
        partial_events = [e for e in self.events if e.get("status") == "partial"]

        self.assertGreaterEqual(len(partial_events), 1, "Expected at least 1 partial transcript event")
        self.assertEqual(len(final_events), 1, "Expected exactly 1 final transcript event")

    def test_5_final_transcript_emitted_once(self):
        """Test 5: Final transcript emitted exactly once after SPEECH_END."""
        audio = synthesize_speech_pcm16("Turn on the lights")
        chunks = [audio[i : i + 512] for i in range(0, len(audio), 512)]

        self.stt.on_speech_start()
        for chunk in chunks:
            self.stt.feed_audio(chunk)
        self.stt.on_speech_end()

        final_events = self.wait_for_final(timeout=5.0)
        self.assertEqual(len(final_events), 1)

    def test_6_short_pause_does_not_finalize(self):
        """Test 6: Short pause during speech does NOT finalize transcript."""
        audio_part1 = synthesize_speech_pcm16("Open Chrome")
        audio_part2 = synthesize_speech_pcm16("and search Google")
        silence_pause = np.zeros(16000 // 4, dtype=np.float32)  # 250ms pause

        chunks1 = [audio_part1[i : i + 512] for i in range(0, len(audio_part1), 512)]
        pause_chunks = [silence_pause[i : i + 512] for i in range(0, len(silence_pause), 512)]
        chunks2 = [audio_part2[i : i + 512] for i in range(0, len(audio_part2), 512)]

        self.stt.on_speech_start()
        for c in chunks1:
            self.stt.feed_audio(c)

        for c in pause_chunks:
            self.stt.feed_audio(c)

        final_during_pause = [e for e in self.events if e.get("status") == "final"]
        self.assertEqual(len(final_during_pause), 0, "Pause should not finalize utterance")

        for c in chunks2:
            self.stt.feed_audio(c)

        self.stt.on_speech_end()
        final_events = self.wait_for_final(timeout=5.0)
        self.assertEqual(len(final_events), 1)

    def test_7_silence_after_speech_triggers_final(self):
        """Test 7: Silence after speech triggers final transcription via pipeline."""
        sec = SecurityContext()
        pipeline = RealtimeVoicePipeline(config=self.cfg, security=sec, stt=self.stt)
        pipe_events = []
        pipeline.add_event_listener(lambda ev: pipe_events.append(ev))

        # Transition state machine: IDLE -> SPEECH_START -> SPEAKING
        pipeline.state_machine.update(is_speech=True, speech_prob=0.95)
        pipeline.state_machine.update(is_speech=True, speech_prob=0.95)
        pipeline.state_machine.update(is_speech=True, speech_prob=0.95)
        self.assertEqual(pipeline.current_state, SpeechState.SPEAKING)

        audio = synthesize_speech_pcm16("Hello Jarvis")
        chunks = [audio[i : i + 512] for i in range(0, len(audio), 512)]
        for c in chunks:
            self.stt.feed_audio(c)

        # Feed silence frames to trigger SPEECH_END
        silence_frames = int(self.cfg.VAD_SILENCE_DURATION / 0.032) + 2
        for _ in range(silence_frames):
            pipeline.state_machine.update(is_speech=False, speech_prob=0.01)

        self.assertEqual(pipeline.current_state, SpeechState.IDLE)
        
        # Wait for final transcript in pipeline events
        deadline = time.time() + 5.0
        final_pipe_events = []
        while time.time() < deadline:
            final_pipe_events = [e for e in pipe_events if e.get("type") == "stt" and e.get("status") == "final"]
            if final_pipe_events:
                break
            time.sleep(0.05)

        self.assertEqual(len(final_pipe_events), 1, "SPEECH_END must trigger final transcription")

    def test_8_emergency_stop_cancels_stt(self):
        """Test 8: Emergency stop cancels/resets STT immediately."""
        sec = SecurityContext()
        pipeline = RealtimeVoicePipeline(config=self.cfg, security=sec, stt=self.stt)

        pipeline.state_machine.update(is_speech=True, speech_prob=0.9)
        pipeline.state_machine.update(is_speech=True, speech_prob=0.9)
        pipeline.state_machine.update(is_speech=True, speech_prob=0.9)

        audio = synthesize_speech_pcm16("Stop everything immediately")
        for i in range(0, len(audio), 512):
            self.stt.feed_audio(audio[i : i + 512])

        # Trigger emergency stop
        sec.trigger_emergency_stop("Safety test halt")

        time.sleep(0.1)
        self.assertFalse(self.stt._is_utterance_active, "STT utterance must be inactive after emergency stop")
        self.assertEqual(len(self.stt._buffer), 0, "STT buffer must be cleared on emergency stop")

    def test_9_no_duplicate_final_transcripts(self):
        """Test 9: Verify no duplicate final transcripts are emitted."""
        audio = synthesize_speech_pcm16("Test duplicate prevention")
        chunks = [audio[i : i + 512] for i in range(0, len(audio), 512)]

        self.stt.on_speech_start()
        for c in chunks:
            self.stt.feed_audio(c)
        self.stt.on_speech_end()
        self.stt.on_speech_end()

        final_events = self.wait_for_final(timeout=5.0)
        self.assertEqual(len(final_events), 1, "Must never emit duplicate final transcripts")

    def test_10_latency_benchmark(self):
        """Test 10: Performance and latency measurements."""
        audio = synthesize_speech_pcm16("Hey Jarvis play classical music")
        chunks = [audio[i : i + 512] for i in range(0, len(audio), 512)]

        t0 = time.time()
        self.stt.on_speech_start(t0)

        for chunk in chunks:
            self.stt.feed_audio(chunk)
            time.sleep(0.02)

        t_speech_end = time.time()
        self.stt.on_speech_end(t_speech_end)

        final_events = self.wait_for_final(timeout=5.0)
        self.assertTrue(len(final_events) >= 1)

        final_ev = final_events[0]
        final_latency_ms = final_ev.get("final_latency_ms", 0.0)
        infer_ms = final_ev.get("inference_ms", 0.0)

        print(f"\n==================== LATENCY BENCHMARK ====================")
        print(f"  Utterance: '{final_ev.get('text')}'")
        print(f"  Audio Duration: {final_ev.get('audio_duration_sec')}s")
        print(f"  Whisper Inference Time: {infer_ms:.1f} ms")
        print(f"  SPEECH_END -> Final Transcript Latency: {final_latency_ms:.1f} ms")
        print(f"===========================================================")


if __name__ == "__main__":
    unittest.main()
