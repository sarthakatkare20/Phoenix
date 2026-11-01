"""
Realtime Continuous Microphone Audio Capture Stream.
Uses sounddevice InputStream to stream low-latency 16 kHz mono frames without blocking.
"""

import logging
import queue
import threading
from typing import Callable, Optional
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

logger = logging.getLogger("paaro.audio")


class AudioCaptureStream:
    """
    Thread-safe continuous audio capture stream for microphone input.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        frame_samples: int = 512,
        device_index: Optional[int] = None,
        callback: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_samples = frame_samples
        self.device_index = device_index
        self._user_callback = callback

        self._stream: Optional[sd.InputStream] = None
        self._is_running = False
        self._is_paused = False
        self._lock = threading.Lock()
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """Low-latency audio hardware callback."""
        if status:
            logger.debug("Audio stream status flag: %s", status)

        if not self._is_running or self._is_paused:
            return

        # Clone and convert to float32 mono 1D array
        chunk = indata[:, 0].astype(np.float32).copy()

        # Dispatch via user callback or queue
        if self._user_callback:
            try:
                self._user_callback(chunk)
            except Exception as e:
                logger.error("Error in audio user callback: %s", e)
        else:
            try:
                self._audio_queue.put_nowait(chunk)
            except queue.Full:
                # Drop oldest frame to avoid latency lag
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    pass
                self._audio_queue.put_nowait(chunk)

    def start(self) -> None:
        """Start capturing audio from microphone."""
        with self._lock:
            if self._is_running:
                return

            if sd is None:
                raise RuntimeError("sounddevice is not installed. Audio capture cannot start.")

            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.frame_samples,
                    device=self.device_index,
                    channels=self.channels,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._is_running = True
                self._is_paused = False
                logger.info(
                    "AudioCaptureStream started: %d Hz, %d samples/block (~%.1f ms)",
                    self.sample_rate,
                    self.frame_samples,
                    (self.frame_samples / self.sample_rate) * 1000.0,
                )
            except Exception as e:
                self._is_running = False
                self._stream = None
                logger.error("Failed to start audio stream: %s", e)
                raise

    def pause(self) -> None:
        """Pause capture without closing device."""
        self._is_paused = True

    def resume(self) -> None:
        """Resume capture."""
        self._is_paused = False

    def stop(self) -> None:
        """Stop and close the audio stream."""
        with self._lock:
            self._is_running = False
            self._is_paused = False
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.debug("Error while closing audio stream: %s", e)
                finally:
                    self._stream = None
            logger.info("AudioCaptureStream stopped.")

    def read_frame(self, block: bool = True, timeout: Optional[float] = None) -> Optional[np.ndarray]:
        """Read a frame from the internal queue (if user_callback not set)."""
        try:
            return self._audio_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None
