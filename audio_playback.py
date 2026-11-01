"""
Continuous In-Memory Audio Playback Queue for Paaro TTS.
Uses sounddevice to stream synthesized PCM chunks without blocking or temporary disk files.
"""

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

logger = logging.getLogger("paaro.playback")


class AudioPlaybackQueue:
    """
    Thread-safe continuous audio playback queue.
    Accepts float32/int16 PCM chunks and plays them sequentially through sounddevice.
    """

    def __init__(
        self,
        sample_rate: int = 24000,
        max_queue_size: int = 20,
    ):
        self.sample_rate = sample_rate
        self.max_queue_size = max_queue_size

        self._audio_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._is_playing = False
        self._is_worker_running = True
        self._cancel_flag = threading.Event()
        self._playback_lock = threading.Lock()

        self._total_chunks_played = 0
        self._underrun_count = 0
        self._stale_audio_discard_count = 0
        self.active_generation_id: Optional[str] = None

        # Listeners for playback events
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._listeners_lock = threading.Lock()

        # Worker thread
        self._worker_thread = threading.Thread(
            target=self._playback_worker_loop,
            name="PaaroAudioPlaybackWorker",
            daemon=True,
        )
        self._worker_thread.start()

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def queue_depth(self) -> int:
        return self._audio_queue.qsize()

    def set_generation_id(self, generation_id: Optional[str]) -> None:
        """Set active generation ID for playback validation."""
        with self._playback_lock:
            self.active_generation_id = generation_id

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "queue_depth": self._audio_queue.qsize(),
            "total_chunks_played": self._total_chunks_played,
            "underrun_count": self._underrun_count,
            "stale_audio_discard_count": self._stale_audio_discard_count,
            "is_playing": self._is_playing,
            "active_generation_id": self.active_generation_id,
        }

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
                logger.error("Error in audio playback listener: %s", e)

    def enqueue(
        self,
        audio_chunk: np.ndarray,
        sample_rate: Optional[int] = None,
        metadata: Optional[dict] = None,
        generation_id: Optional[str] = None,
    ) -> None:
        """
        Enqueue a PCM audio chunk for playback.
        audio_chunk: 1D float32 or int16 numpy array.
        """
        if self._cancel_flag.is_set():
            return

        if audio_chunk is None or len(audio_chunk) == 0:
            return

        # Check generation match
        if generation_id and self.active_generation_id and generation_id != self.active_generation_id:
            self._stale_audio_discard_count += 1
            return

        # Normalize to float32 mono
        if audio_chunk.dtype == np.int16:
            audio_chunk = audio_chunk.astype(np.float32) / 32768.0
        elif audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)

        sr = sample_rate or self.sample_rate

        item = {
            "audio": audio_chunk,
            "sample_rate": sr,
            "metadata": metadata or {},
            "generation_id": generation_id or self.active_generation_id,
        }

        try:
            self._audio_queue.put_nowait(item)
        except queue.Full:
            logger.warning("Audio playback queue full; dropping oldest chunk.")
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass
            self._audio_queue.put_nowait(item)

    def cancel(self) -> float:
        """
        Immediately stop active audio output, purge pending queue, and reset.
        Returns time taken in milliseconds.
        """
        t0 = time.time()
        self._cancel_flag.set()
        self.active_generation_id = None

        # Stop active sounddevice stream
        if sd is not None:
            try:
                sd.stop()
            except Exception as e:
                logger.debug("Error calling sd.stop(): %s", e)

        # Drain queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
                self._stale_audio_discard_count += 1
            except queue.Empty:
                break

        self._is_playing = False
        t_elapsed_ms = (time.time() - t0) * 1000.0
        self._broadcast({
            "type": "tts_cancelled",
            "stop_duration_ms": round(t_elapsed_ms, 2),
            "timestamp": int(time.time() * 1000),
        })
        self._cancel_flag.clear()
        return t_elapsed_ms

    def _playback_worker_loop(self) -> None:
        """Background thread executing sequential audio playback."""
        logger.info("AudioPlaybackQueue worker thread started.")
        first_chunk_played = False

        while self._is_worker_running:
            try:
                item = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                if self._is_playing and self._audio_queue.empty():
                    self._is_playing = False
                    first_chunk_played = False
                    self._broadcast({
                        "type": "tts_done",
                        "timestamp": int(time.time() * 1000),
                    })
                continue

            if item is None or not self._is_worker_running:
                break

            if self._cancel_flag.is_set():
                continue

            gen_id = item.get("generation_id")
            if gen_id and self.active_generation_id and gen_id != self.active_generation_id:
                self._stale_audio_discard_count += 1
                continue

            audio = item.get("audio")
            sr = item.get("sample_rate", self.sample_rate)
            meta = item.get("metadata", {})

            if audio is None or len(audio) == 0:
                continue

            self._is_playing = True
            self._total_chunks_played += 1
            if not first_chunk_played:
                first_chunk_played = True
                self._broadcast({
                    "type": "tts_audio_start",
                    "timestamp": int(time.time() * 1000),
                    **meta,
                })

            # Play audio chunk
            duration_sec = len(audio) / sr
            if sd is not None:
                try:
                    sd.play(audio, samplerate=sr, blocking=False)
                    # Sleep for duration of chunk while checking cancel flag
                    end_time = time.time() + duration_sec
                    while time.time() < end_time:
                        if self._cancel_flag.is_set():
                            sd.stop()
                            break
                        time.sleep(0.015)
                except Exception as e:
                    logger.error("Error during sounddevice playback: %s", e)
                    # Simulate timing if audio device fails
                    time.sleep(min(duration_sec, 0.2))
            else:
                # Mock playback delay in headless environments
                time.sleep(min(duration_sec, 0.2))

            self._broadcast({
                "type": "tts_audio_chunk",
                "duration_sec": round(duration_sec, 3),
                "timestamp": int(time.time() * 1000),
                **meta,
            })

        logger.info("AudioPlaybackQueue worker thread stopped.")

    def close(self) -> None:
        """Shutdown playback worker."""
        self._is_worker_running = False
        self.cancel()
        try:
            self._audio_queue.put_nowait(None)
        except Exception:
            pass
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
