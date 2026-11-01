"""
Streaming Text-to-Speech (TTS) Engine for Paaro.
Pipelined architecture: Text Chunker -> Kokoro/Local TTS Synthesis -> Audio Playback Queue.
Synthesizes speech concurrently while the LLM generates tokens.
"""

import io
import logging
import queue
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np

try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

from config import PaaroSettings, settings
from security import SecurityContext, security_context
from text_chunker import TextChunker
from audio_playback import AudioPlaybackQueue

logger = logging.getLogger("paaro.tts")


class BaseTTSBackend:
    """Abstract interface for audio synthesis engines."""

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> Tuple[np.ndarray, int]:
        """Synthesize text into a 1D float32 PCM numpy array and sample rate."""
        raise NotImplementedError


class KokoroONNXBackend(BaseTTSBackend):
    """Kokoro ONNX Engine implementation."""

    def __init__(self, model_path: Optional[str] = None, voices_path: Optional[str] = None):
        try:
            import kokoro_onnx
            self._kokoro = kokoro_onnx.Kokoro(model_path, voices_path) if model_path else None
        except Exception as e:
            logger.warning("Kokoro ONNX backend init failed: %s. Will fallback to local TTS.", e)
            self._kokoro = None

    def synthesize(self, text: str, voice: str = "af_sarah", speed: float = 1.0) -> Tuple[np.ndarray, int]:
        if self._kokoro is None:
            raise RuntimeError("Kokoro ONNX model is not loaded.")
        samples, sr = self._kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        return samples.astype(np.float32), sr


class Pyttsx3Backend(BaseTTSBackend):
    """Reliable low-latency local TTS engine fallback for Windows/cross-platform."""

    def __init__(self):
        self._lock = threading.Lock()

    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> Tuple[np.ndarray, int]:
        if pyttsx3 is None or sf is None:
            # Fallback to pure silent mock buffer
            sr = 22050
            duration = max(0.2, len(text) * 0.05)
            samples = np.zeros(int(sr * duration), dtype=np.float32)
            return samples, sr

        with self._lock:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name

            try:
                engine = pyttsx3.init()
                rate = engine.getProperty("rate")
                engine.setProperty("rate", int(rate * speed))
                engine.save_to_file(text, tmp_path)
                engine.runAndWait()
                audio, sr = sf.read(tmp_path)
            finally:
                import os
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

        if audio.ndim > 1:
            audio = audio[:, 0]

        return audio.astype(np.float32), sr


class StreamingTTS:
    """
    Pipelined streaming TTS manager.
    Receives token deltas from LLM, chunks text into sentences, synthesizes audio
    asynchronously, and feeds the AudioPlaybackQueue.
    """

    def __init__(
        self,
        config: Optional[PaaroSettings] = None,
        security: Optional[SecurityContext] = None,
        playback_queue: Optional[AudioPlaybackQueue] = None,
    ):
        self.config = config or settings
        self.security = security or security_context

        # Text Chunker
        self.chunker = TextChunker(
            min_chars=self.config.TTS_CHUNK_MIN_CHARS,
            max_chars=self.config.TTS_CHUNK_MAX_CHARS,
        )

        # Audio Playback
        self.playback = playback_queue or AudioPlaybackQueue(
            sample_rate=self.config.TTS_SAMPLE_RATE,
            max_queue_size=self.config.TTS_QUEUE_MAX_SIZE,
        )

        # Select Backend
        self.backend: BaseTTSBackend
        if self.config.TTS_ENGINE == "kokoro":
            try:
                self.backend = KokoroONNXBackend()
                if getattr(self.backend, "_kokoro", None) is None:
                    self.backend = Pyttsx3Backend()
            except Exception:
                self.backend = Pyttsx3Backend()
        else:
            self.backend = Pyttsx3Backend()

        # Synthesis Worker Queue & Thread
        self._synth_queue: queue.Queue = queue.Queue(maxsize=30)
        self._is_worker_running = True
        self._cancel_flag = threading.Event()
        self._current_generation_id: Optional[str] = None
        self._stale_token_discard_count = 0
        self._stale_audio_discard_count = 0

        # Latency & performance metrics
        self._session_start_time: Optional[float] = None
        self._llm_first_token_time: Optional[float] = None
        self._first_audio_played_time: Optional[float] = None
        self._total_chunks_synthesized = 0
        self._total_synthesis_time_ms = 0.0
        self._cancel_count = 0

        # Listeners
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._listeners_lock = threading.Lock()

        # Connect playback notifications
        self.playback.add_listener(self._on_playback_event)

        # Start synthesis worker
        self._synth_thread = threading.Thread(
            target=self._synthesis_worker_loop,
            name="PaaroTtsSynthWorker",
            daemon=True,
        )
        self._synth_thread.start()

    @property
    def is_speaking(self) -> bool:
        return self.playback.is_playing or not self._synth_queue.empty()

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
                logger.error("Error in TTS listener callback: %s", e)

    def _on_playback_event(self, event: Dict[str, Any]) -> None:
        if event.get("type") == "tts_audio_start":
            now = time.time()
            if self._first_audio_played_time is None and self._llm_first_token_time:
                self._first_audio_played_time = now
                latency_ms = (now - self._llm_first_token_time) * 1000.0
                event["llm_first_token_to_audio_ms"] = round(latency_ms, 1)

        self._broadcast(event)

    @property
    def active_generation_id(self) -> Optional[str]:
        return self._current_generation_id

    def on_llm_start(self, timestamp: Optional[float] = None, generation_id: Optional[str] = None) -> None:
        """Called when LLM generation begins."""
        self.cancel()
        if isinstance(timestamp, str) and generation_id is None:
            generation_id = timestamp
            timestamp = time.time()
        self._session_start_time = timestamp or time.time()
        self._current_generation_id = generation_id
        self.playback.set_generation_id(generation_id)
        self._llm_first_token_time = None
        self._first_audio_played_time = None
        self._total_chunks_synthesized = 0
        self._total_synthesis_time_ms = 0.0

        self._broadcast({
            "type": "tts_start",
            "generation_id": generation_id,
            "timestamp": int((self._session_start_time) * 1000),
        })

    def feed_text_delta(self, delta: str, generation_id: Optional[str] = None) -> None:
        """Feed a streaming token delta from the LLM."""
        if not self.config.TTS_ENABLED or self.security.is_emergency_stopped:
            return

        if generation_id and self._current_generation_id and generation_id != self._current_generation_id:
            self._stale_token_discard_count += 1
            return

        if self._llm_first_token_time is None:
            self._llm_first_token_time = time.time()

        chunks = self.chunker.feed(delta)
        for chunk in chunks:
            self._enqueue_chunk(chunk, generation_id=generation_id or self._current_generation_id)

    def flush_text(self, generation_id: Optional[str] = None) -> None:
        """Called when LLM generation completes (`done`)."""
        if not self.config.TTS_ENABLED or self.security.is_emergency_stopped:
            return

        if generation_id and self._current_generation_id and generation_id != self._current_generation_id:
            return

        tail_chunk = self.chunker.flush()
        if tail_chunk:
            self._enqueue_chunk(tail_chunk, generation_id=generation_id or self._current_generation_id)

    def _enqueue_chunk(self, text_chunk: str, generation_id: Optional[str] = None) -> None:
        if not text_chunk.strip():
            return

        item = {
            "text": text_chunk.strip(),
            "queued_time": time.time(),
            "generation_id": generation_id or self._current_generation_id,
        }
        try:
            self._synth_queue.put_nowait(item)
        except queue.Full:
            logger.warning("TTS synthesis queue full; dropping text chunk.")

    def cancel(self) -> float:
        """Cancel active synthesis and playback immediately. Returns duration in ms."""
        t0 = time.time()
        self._cancel_count += 1
        self._cancel_flag.set()
        old_gen = self._current_generation_id
        self._current_generation_id = None

        # Clear text chunker
        self.chunker.reset()

        # Drain synthesis queue
        while not self._synth_queue.empty():
            try:
                self._synth_queue.get_nowait()
                self._stale_token_discard_count += 1
            except queue.Empty:
                break

        # Stop playback
        playback_stop_ms = self.playback.cancel()
        t_elapsed_ms = (time.time() - t0) * 1000.0

        if old_gen:
            self._broadcast({
                "type": "tts_interrupted",
                "cancelled_generation_id": old_gen,
                "duration_ms": round(t_elapsed_ms, 2),
                "playback_stop_ms": round(playback_stop_ms, 2),
                "timestamp": int(time.time() * 1000),
            })

        self._cancel_flag.clear()
        return t_elapsed_ms

    def _synthesis_worker_loop(self) -> None:
        """Background thread synthesizing text chunks into PCM audio."""
        logger.info("StreamingTTS synthesis worker started.")

        while self._is_worker_running:
            try:
                item = self._synth_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if item is None or not self._is_worker_running:
                break

            if self._cancel_flag.is_set() or self.security.is_emergency_stopped:
                continue

            item_gen = item.get("generation_id")
            if item_gen and self._current_generation_id and item_gen != self._current_generation_id:
                self._stale_token_discard_count += 1
                continue

            text = item.get("text", "")
            queued_time = item.get("queued_time", time.time())

            if not text:
                continue

            t_start = time.time()
            try:
                pcm_data, sr = self.backend.synthesize(
                    text=text,
                    voice=self.config.TTS_VOICE,
                    speed=self.config.TTS_SPEED,
                )
            except Exception as e:
                logger.error("TTS synthesis error on '%s': %s", text, e)
                continue

            t_end = time.time()
            synth_ms = (t_end - t_start) * 1000.0

            if (
                self._cancel_flag.is_set()
                or self.security.is_emergency_stopped
                or (item_gen and self._current_generation_id and item_gen != self._current_generation_id)
            ):
                self._stale_audio_discard_count += 1
                continue

            self._total_chunks_synthesized += 1
            self._total_synthesis_time_ms += synth_ms

            # Enqueue synthesized PCM chunk into audio playback queue
            self.playback.enqueue(
                audio_chunk=pcm_data,
                sample_rate=sr,
                metadata={
                    "text": text,
                    "synth_ms": round(synth_ms, 1),
                    "queued_to_synth_ms": round((t_start - queued_time) * 1000.0, 1),
                },
                generation_id=item_gen or self._current_generation_id,
            )

        logger.info("StreamingTTS synthesis worker stopped.")

    def get_metrics(self) -> Dict[str, Any]:
        avg_synth_ms = (
            self._total_synthesis_time_ms / max(1, self._total_chunks_synthesized)
            if self._total_chunks_synthesized > 0
            else 0.0
        )
        llm_first_token_to_audio_ms = None
        if self._first_audio_played_time and self._llm_first_token_time:
            llm_first_token_to_audio_ms = round(
                (self._first_audio_played_time - self._llm_first_token_time) * 1000.0, 1
            )

        return {
            "engine": self.config.TTS_ENGINE,
            "voice": self.config.TTS_VOICE,
            "active_generation_id": self._current_generation_id,
            "total_chunks_synthesized": self._total_chunks_synthesized,
            "avg_synth_latency_ms": round(avg_synth_ms, 1),
            "cancel_count": self._cancel_count,
            "stale_token_discard_count": self._stale_token_discard_count,
            "stale_audio_discard_count": self._stale_audio_discard_count,
            "synth_queue_depth": self._synth_queue.qsize(),
            "llm_first_token_to_audio_ms": llm_first_token_to_audio_ms,
            "playback": self.playback.get_metrics(),
        }

    def close(self) -> None:
        """Shutdown TTS synthesis and playback."""
        self._is_worker_running = False
        self.cancel()
        try:
            self._synth_queue.put_nowait(None)
        except Exception:
            pass
        if self._synth_thread.is_alive():
            self._synth_thread.join(timeout=1.0)
        self.playback.close()
