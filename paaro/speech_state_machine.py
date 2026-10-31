"""
Speech State Machine for Paaro Realtime Voice.
Manages robust transitions between IDLE, SPEECH_START, SPEAKING, and SPEECH_END.
"""

from enum import Enum
import time
from typing import Callable, List, Optional


class SpeechState(str, Enum):
    IDLE = "idle"
    SPEECH_START = "speech_start"
    SPEAKING = "speaking"
    SPEECH_END = "speech_end"


class SpeechStateMachine:
    """
    Robust Speech State Machine with hysteresis and configurable hangover durations.
    """

    def __init__(
        self,
        speech_start_confirmation: int = 3,
        silence_duration_sec: float = 0.6,
        frame_duration_sec: float = 0.032,  # 32ms
    ):
        self.speech_start_confirmation = max(1, speech_start_confirmation)
        self.silence_duration_sec = silence_duration_sec
        self.frame_duration_sec = frame_duration_sec
        self.silence_frames_threshold = int(self.silence_duration_sec / self.frame_duration_sec)

        self._state: SpeechState = SpeechState.IDLE
        self._consecutive_speech_frames: int = 0
        self._consecutive_silence_frames: int = 0
        self._speech_start_time: Optional[float] = None
        self._last_speech_time: Optional[float] = None
        self._listeners: List[Callable[[SpeechState, float, dict], None]] = []

    @property
    def current_state(self) -> SpeechState:
        return self._state

    def add_listener(self, listener: Callable[[SpeechState, float, dict], None]) -> None:
        """Register listener for state changes: callback(new_state, timestamp, metadata)."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[SpeechState, float, dict], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self, new_state: SpeechState, metadata: Optional[dict] = None) -> None:
        now = time.time()
        meta = metadata or {}
        for listener in self._listeners:
            try:
                listener(new_state, now, meta)
            except Exception:
                pass

    def reset(self) -> None:
        """Reset state machine back to IDLE."""
        prev_state = self._state
        self._state = SpeechState.IDLE
        self._consecutive_speech_frames = 0
        self._consecutive_silence_frames = 0
        self._speech_start_time = None
        self._last_speech_time = None
        if prev_state != SpeechState.IDLE:
            self._notify(SpeechState.IDLE, {"reason": "reset"})

    def update(
        self,
        is_speech: bool,
        speech_prob: float,
        speech_start_confirmation: Optional[int] = None,
    ) -> SpeechState:
        """
        Feed a single audio frame detection result into the state machine.
        Returns the updated SpeechState.
        """
        now = time.time()
        confirmation_threshold = (
            speech_start_confirmation
            if speech_start_confirmation is not None
            else self.speech_start_confirmation
        )

        if self._state == SpeechState.IDLE:
            if is_speech:
                self._consecutive_speech_frames += 1
                if self._consecutive_speech_frames >= confirmation_threshold:
                    # Confirmed speech start
                    self._state = SpeechState.SPEAKING
                    self._speech_start_time = now
                    self._last_speech_time = now
                    self._consecutive_silence_frames = 0
                    self._notify(SpeechState.SPEECH_START, {"prob": speech_prob})
                    return SpeechState.SPEECH_START
            else:
                # Reset speech counter on silence
                self._consecutive_speech_frames = 0
            return SpeechState.IDLE

        elif self._state in (SpeechState.SPEAKING, SpeechState.SPEECH_START):
            if is_speech:
                self._state = SpeechState.SPEAKING
                self._consecutive_silence_frames = 0
                self._last_speech_time = now
                return SpeechState.SPEAKING
            else:
                self._consecutive_silence_frames += 1
                silence_elapsed = self._consecutive_silence_frames * self.frame_duration_sec
                if silence_elapsed >= self.silence_duration_sec:
                    # Speech has ended
                    duration = (now - self._speech_start_time) if self._speech_start_time else 0.0
                    self._state = SpeechState.IDLE
                    self._consecutive_speech_frames = 0
                    self._consecutive_silence_frames = 0
                    self._speech_start_time = None
                    self._last_speech_time = None
                    
                    # Notify speech_end first, then idle
                    self._notify(SpeechState.SPEECH_END, {"duration": duration, "prob": speech_prob})
                    self._notify(SpeechState.IDLE, {"prob": speech_prob})
                    return SpeechState.SPEECH_END
                else:
                    # In silence hangover/grace period, still treated as speaking
                    return SpeechState.SPEAKING

        return self._state
