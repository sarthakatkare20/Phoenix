"""
Streaming Speech-to-Text (STT) Engine using faster-whisper.
Performs incremental partial transcription and final utterance normalization without blocking.
"""

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

from .config import PaaroSettings, settings

logger = logging.getLogger("paaro.stt")


class StreamingSTT:
    """
    Incremental streaming STT manager using faster-whisper.
    Processes in-memory audio chunks and emits partial & final transcriptions.
    """

    def __init__(
        self,
        config: Optional[PaaroSettings] = None,
        model: Optional[Any] = None,
    ):
        self.config = config or settings
        self.sample_rate = self.config.AUDIO_SAMPLE_RATE

        # Load WhisperModel or reuse provided instance
        if model is not None:
            self.model = model
        else:
            self.model = self._load_model()

        # Audio buffer for active utterance
        self._buffer: List[np.ndarray] = []
        self._buffer_lock = threading.Lock()

        # State tracking
        self._is_utterance_active = False
        self._speech_start_time: Optional[float] = None
        self._last_partial_time: float = 0.0
        self._last_partial_text: str = ""
        self._first_partial_time: Optional[float] = None
        self._final_transcript_emitted = False

        # Internal worker thread for async STT inference
        self._job_queue: queue.Queue = queue.Queue(maxsize=10)
        self._is_worker_running = True
        self._worker_thread = threading.Thread(
            target=self._stt_worker_loop,
            name="PaaroSttWorker",
            daemon=True,
        )
        self._worker_thread.start()

        # Listeners: callback(event_dict)
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._listeners_lock = threading.Lock()

    def _load_model(self) -> Optional[Any]:
        if WhisperModel is None:
            logger.warning("faster-whisper is not installed. STT will be disabled.")
            return None

        try:
            logger.info(
                "Loading faster-whisper model '%s' (device=%s, compute_type=%s)...",
                self.config.WHISPER_MODEL_SIZE,
                self.config.WHISPER_DEVICE,
                self.config.WHISPER_COMPUTE_TYPE,
            )
            t0 = time.time()
            model = WhisperModel(
                self.config.WHISPER_MODEL_SIZE,
                device=self.config.WHISPER_DEVICE,
                compute_type=self.config.WHISPER_COMPUTE_TYPE,
            )
            logger.info("faster-whisper model loaded in %.2fs", time.time() - t0)
            return model
        except Exception as e:
            logger.error("Failed to load faster-whisper model: %s", e)
            return None

    def add_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        with self._listeners_lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        with self._listeners_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _broadcast(self, event: Dict[str, Any]) -> None:
        listeners = []
        with self._listeners_lock:
            listeners = list(self._listeners)

        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error("Error in STT listener callback: %s", e)

    def on_speech_start(self, timestamp: Optional[float] = None) -> None:
        """Called when SpeechStateMachine detects SPEECH_START."""
        now = timestamp or time.time()
        with self._buffer_lock:
            self._buffer.clear()
            self._is_utterance_active = True
            self._speech_start_time = now
            self._last_partial_time = now
            self._last_partial_text = ""
            self._first_partial_time = None
            self._final_transcript_emitted = False

        # Clear any obsolete pending jobs
        while not self._job_queue.empty():
            try:
                self._job_queue.get_nowait()
            except queue.Empty:
                break

    def feed_audio(self, chunk: np.ndarray) -> None:
        """
        Feed audio frame (float32, 16kHz mono) while speaking.
        Periodically queues incremental partial transcription.
        """
        if not self._is_utterance_active or self.model is None:
            return

        now = time.time()
        with self._buffer_lock:
            self._buffer.append(chunk)
            total_samples = sum(len(c) for c in self._buffer)
            audio_duration = total_samples / self.sample_rate

            # Check if it's time for an incremental partial transcription
            time_since_partial = now - self._last_partial_time
            if (
                audio_duration >= self.config.STT_MIN_AUDIO_DURATION
                and time_since_partial >= self.config.STT_UPDATE_INTERVAL
            ):
                self._last_partial_time = now
                # Snapshot current audio buffer in memory
                audio_snapshot = np.concatenate(self._buffer, axis=0).copy()

                # Queue partial job without blocking
                try:
                    self._job_queue.put_nowait({
                        "type": "partial",
                        "audio": audio_snapshot,
                        "speech_start_time": self._speech_start_time,
                    })
                except queue.Full:
                    pass

    def on_speech_end(self, timestamp: Optional[float] = None) -> None:
        """Called when SpeechStateMachine detects SPEECH_END."""
        now = timestamp or time.time()
        with self._buffer_lock:
            if not self._is_utterance_active:
                return
            self._is_utterance_active = False

            if not self._buffer:
                return

            audio_full = np.concatenate(self._buffer, axis=0).copy()
            speech_start_time = self._speech_start_time
            self._buffer.clear()

        # Discard any stale pending partial jobs so final executes immediately
        while not self._job_queue.empty():
            try:
                self._job_queue.get_nowait()
            except queue.Empty:
                break

        # Queue final transcription job with top priority
        try:
            self._job_queue.put_nowait({
                "type": "final",
                "audio": audio_full,
                "speech_start_time": speech_start_time,
                "speech_end_time": now,
            })
        except queue.Full:
            try:
                self._job_queue.get_nowait()
            except queue.Empty:
                pass
            self._job_queue.put_nowait({
                "type": "final",
                "audio": audio_full,
                "speech_start_time": speech_start_time,
                "speech_end_time": now,
            })

    def cancel(self) -> None:
        """Cancel current utterance and discard pending STT jobs (e.g. on emergency stop)."""
        with self._buffer_lock:
            self._buffer.clear()
            self._is_utterance_active = False
            self._speech_start_time = None
            self._last_partial_text = ""
            self._final_transcript_emitted = False

        while not self._job_queue.empty():
            try:
                self._job_queue.get_nowait()
            except queue.Empty:
                break

    def transcribe_audio_array(self, audio: np.ndarray) -> str:
        """Run faster-whisper inference directly on a 1D float32 numpy array."""
        if self.model is None or len(audio) == 0:
            return ""

        # Normalize audio array
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        try:
            segments, info = self.model.transcribe(
                audio,
                language=self.config.STT_LANGUAGE,
                beam_size=self.config.WHISPER_BEAM_SIZE,
                temperature=self.config.WHISPER_TEMPERATURE,
                condition_on_previous_text=self.config.WHISPER_CONDITION_ON_PREVIOUS_TEXT,
                no_speech_threshold=self.config.WHISPER_NO_SPEECH_THRESHOLD,
                vad_filter=False,  # Silero VAD already filtered boundaries
            )

            text_segments = [s.text.strip() for s in segments if s.text.strip()]
            full_text = " ".join(text_segments).strip()
            return full_text
        except Exception as e:
            logger.error("Whisper transcription error: %s", e)
            return ""

    def _stt_worker_loop(self) -> None:
        """Background thread executing faster-whisper inference."""
        logger.info("StreamingSTT background worker started.")

        while self._is_worker_running:
            try:
                job = self._job_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if job is None or not self._is_worker_running:
                break

            job_type = job.get("type")
            audio = job.get("audio")
            speech_start_time = job.get("speech_start_time")

            if audio is None or len(audio) == 0:
                continue

            self._is_busy = True
            t_infer_start = time.time()
            text = self.transcribe_audio_array(audio)
            t_infer_end = time.time()
            infer_duration_ms = (t_infer_end - t_infer_start) * 1000.0

            if job_type == "partial":
                # Only broadcast if text is non-empty and changed
                if text and text != self._last_partial_text:
                    self._last_partial_text = text
                    now = time.time()
                    if self._first_partial_time is None and speech_start_time:
                        self._first_partial_time = now
                        first_partial_latency_ms = (now - speech_start_time) * 1000.0
                    else:
                        first_partial_latency_ms = None

                    event = {
                        "type": "stt",
                        "status": "partial",
                        "text": text,
                        "inference_ms": round(infer_duration_ms, 1),
                        "first_partial_latency_ms": round(first_partial_latency_ms, 1) if first_partial_latency_ms else None,
                        "timestamp": int(now * 1000),
                    }
                    self._broadcast(event)

            elif job_type == "final":
                speech_end_time = job.get("speech_end_time", t_infer_start)
                final_latency_ms = (t_infer_end - speech_end_time) * 1000.0
                total_utterance_duration = (speech_end_time - speech_start_time) if speech_start_time else (len(audio) / self.sample_rate)

                # Fall back to last partial text if final inference was blank but partial was present
                if not text and self._last_partial_text:
                    text = self._last_partial_text

                event = {
                    "type": "stt",
                    "status": "final",
                    "text": text,
                    "audio_duration_sec": round(total_utterance_duration, 2),
                    "inference_ms": round(infer_duration_ms, 1),
                    "final_latency_ms": round(final_latency_ms, 1),
                    "timestamp": int(t_infer_end * 1000),
                }
                self._broadcast(event)
                self._final_transcript_emitted = True
                self._last_partial_text = ""

            self._is_busy = False

        logger.info("StreamingSTT background worker stopped.")

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """Wait until all queued STT jobs have completed."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._job_queue.empty() and not getattr(self, "_is_busy", False):
                return True
            time.sleep(0.02)
        return False

    def close(self) -> None:
        """Shutdown STT worker thread."""
        self._is_worker_running = False
        try:
            self._job_queue.put_nowait(None)
        except Exception:
            pass
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
