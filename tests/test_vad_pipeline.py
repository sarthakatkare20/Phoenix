"""
Unit and Integration Tests for Paaro Realtime Voice & Silero VAD Pipeline (Step 1).
Validates:
- Test 1: No speech (IDLE state retention)
- Test 2: User starts speaking (IDLE -> SPEECH_START -> SPEAKING)
- Test 3: User stops speaking (SPEAKING -> SPEECH_END -> IDLE)
- Test 4: Short noise rejection (transient spikes do not trigger speech)
- Test 5: Short pause preservation (silence hangover prevents premature cutoffs)
- Test 6: Emergency stop (halts processing and resets state safely)
- Silero VAD local ONNX inference accuracy
"""

import unittest
import numpy as np
import time

from paaro.config import PaaroSettings
from paaro.security import SecurityContext
from paaro.silero_vad import SileroVAD
from paaro.speech_state_machine import SpeechStateMachine, SpeechState
from paaro.realtime_pipeline import RealtimeVoicePipeline


class TestSileroVAD(unittest.TestCase):
    """Verify Silero VAD local streaming inference."""

    def setUp(self):
        self.vad = SileroVAD(sample_rate=16000, threshold=0.5)

    def test_silero_vad_silence(self):
        """Pure silence should yield low speech probability (< 0.2)."""
        silence_frame = np.zeros(512, dtype=np.float32)
        prob = self.vad.process_frame(silence_frame)
        self.assertIsInstance(prob, float)
        self.assertLess(prob, 0.2, f"Silence probability unexpectedly high: {prob}")

    def test_silero_vad_stateful_reset(self):
        """Reset should zero out recurrent states."""
        self.vad.reset_state()
        self.assertEqual(np.count_nonzero(self.vad._h), 0)
        self.assertEqual(np.count_nonzero(self.vad._c), 0)
        self.assertEqual(np.count_nonzero(self.vad._context), 0)


class TestSpeechStateMachine(unittest.TestCase):
    """Verify all state transitions and timing hysteresis in the state machine."""

    def setUp(self):
        # 3 frames confirmation (~96ms), 0.6s silence duration (~18 frames of 32ms)
        self.sm = SpeechStateMachine(
            speech_start_confirmation=3,
            silence_duration_sec=0.6,
            frame_duration_sec=0.032,
        )
        self.events = []
        self.sm.add_listener(lambda state, ts, meta: self.events.append((state, meta)))

    def test_1_no_speech_stays_idle(self):
        """Test 1: No microphone speech -> stays IDLE."""
        for _ in range(20):
            st = self.sm.update(is_speech=False, speech_prob=0.05)
            self.assertEqual(st, SpeechState.IDLE)
        self.assertEqual(self.sm.current_state, SpeechState.IDLE)
        self.assertEqual(len(self.events), 0)

    def test_2_speech_start_to_speaking(self):
        """Test 2: User starts speaking -> IDLE -> SPEECH_START -> SPEAKING."""
        # Frame 1: speech detected, but confirmation threshold is 3
        st1 = self.sm.update(is_speech=True, speech_prob=0.8)
        self.assertEqual(st1, SpeechState.IDLE)

        # Frame 2: speech detected
        st2 = self.sm.update(is_speech=True, speech_prob=0.85)
        self.assertEqual(st2, SpeechState.IDLE)

        # Frame 3: confirmed speech start
        st3 = self.sm.update(is_speech=True, speech_prob=0.9)
        self.assertEqual(st3, SpeechState.SPEECH_START)
        self.assertEqual(self.sm.current_state, SpeechState.SPEAKING)

        # Frame 4+: continuous speaking
        st4 = self.sm.update(is_speech=True, speech_prob=0.92)
        self.assertEqual(st4, SpeechState.SPEAKING)

        # Check recorded events
        self.assertTrue(any(e[0] == SpeechState.SPEECH_START for e in self.events))

    def test_3_speech_end_to_idle(self):
        """Test 3: User stops speaking -> SPEAKING -> SPEECH_END -> IDLE."""
        # First transition into SPEAKING
        for _ in range(3):
            self.sm.update(is_speech=True, speech_prob=0.85)
        self.assertEqual(self.sm.current_state, SpeechState.SPEAKING)

        # Feed silence frames (0.6s / 0.032s = ~19 frames)
        silence_frames = int(0.6 / 0.032) + 1
        last_state = None
        for _ in range(silence_frames):
            last_state = self.sm.update(is_speech=False, speech_prob=0.05)

        self.assertEqual(last_state, SpeechState.SPEECH_END)
        self.assertEqual(self.sm.current_state, SpeechState.IDLE)
        self.assertTrue(any(e[0] == SpeechState.SPEECH_END for e in self.events))
        self.assertTrue(any(e[0] == SpeechState.IDLE for e in self.events))

    def test_4_short_noise_rejection(self):
        """Test 4: Short noise (e.g. 1-2 frames click/pop) should NOT trigger speech start/end."""
        # 1 isolated speech frame (e.g. click/key tap)
        st1 = self.sm.update(is_speech=True, speech_prob=0.8)
        self.assertEqual(st1, SpeechState.IDLE)

        # Followed by silence
        st2 = self.sm.update(is_speech=False, speech_prob=0.02)
        self.assertEqual(st2, SpeechState.IDLE)

        # Another 1 isolated speech frame
        st3 = self.sm.update(is_speech=True, speech_prob=0.75)
        self.assertEqual(st3, SpeechState.IDLE)

        # Followed by silence
        st4 = self.sm.update(is_speech=False, speech_prob=0.01)
        self.assertEqual(st4, SpeechState.IDLE)

        self.assertEqual(self.sm.current_state, SpeechState.IDLE)
        self.assertEqual(len(self.events), 0, "Short noise should not have generated any events")

    def test_5_short_pause_preservation(self):
        """Test 5: Short pause while speaking should NOT immediately trigger SPEECH_END."""
        # Transition to SPEAKING
        for _ in range(3):
            self.sm.update(is_speech=True, speech_prob=0.9)
        self.assertEqual(self.sm.current_state, SpeechState.SPEAKING)

        # Short pause of 5 frames (~160ms, well under the 600ms hangover)
        for _ in range(5):
            st = self.sm.update(is_speech=False, speech_prob=0.08)
            self.assertEqual(st, SpeechState.SPEAKING, "Short pause should remain in SPEAKING state")

        # User resumes speaking
        st_resume = self.sm.update(is_speech=True, speech_prob=0.88)
        self.assertEqual(st_resume, SpeechState.SPEAKING)
        self.assertEqual(self.sm.current_state, SpeechState.SPEAKING)

        # Ensure no SPEECH_END event was fired during the pause
        speech_ends = [e for e in self.events if e[0] == SpeechState.SPEECH_END]
        self.assertEqual(len(speech_ends), 0, "Premature SPEECH_END should not have triggered")


class TestSecurityAndEmergencyStop(unittest.TestCase):
    """Test 6: Realtime listener stops processing when emergency stop is active."""

    def test_6_emergency_stop_halts_pipeline(self):
        sec = SecurityContext()
        cfg = PaaroSettings(VAD_THRESHOLD=0.5)
        pipeline = RealtimeVoicePipeline(config=cfg, security=sec)

        # Put state machine in speaking state
        for _ in range(3):
            pipeline.state_machine.update(is_speech=True, speech_prob=0.95)
        self.assertEqual(pipeline.current_state, SpeechState.SPEAKING)

        # Trigger emergency stop
        sec.trigger_emergency_stop("Safety test triggered")
        self.assertTrue(sec.is_emergency_stopped)
        self.assertEqual(pipeline.current_state, SpeechState.IDLE, "Emergency stop must immediately force IDLE state")

        # Audio chunks pushed during emergency stop should be ignored
        dummy_chunk = np.ones(512, dtype=np.float32)
        pipeline._on_raw_audio_chunk(dummy_chunk)
        self.assertEqual(pipeline._audio_queue.qsize(), 0, "Audio queue must drop frames while emergency stop is active")

        # Clear emergency stop
        sec.clear_emergency_stop()
        self.assertFalse(sec.is_emergency_stopped)


if __name__ == "__main__":
    unittest.main()
