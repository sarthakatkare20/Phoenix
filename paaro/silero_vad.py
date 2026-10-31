"""
Silero VAD Local Streaming Engine.
Provides low-latency, stateful voice activity detection directly in memory.
"""

import os
from typing import Optional, Tuple
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None


class SileroVAD:
    """
    Local Silero VAD stateful streaming model.
    Processes continuous 512-sample (32ms at 16kHz) audio chunks with recurrent state.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        context_size: int = 64,
    ):
        if sample_rate not in (8000, 16000):
            raise ValueError(f"Silero VAD only supports 8000Hz or 16000Hz. Given: {sample_rate}")

        self.sample_rate = sample_rate
        self.threshold = threshold
        self.context_size = context_size
        self.num_samples = 512 if sample_rate == 16000 else 256

        # Find model path
        if not model_path:
            model_path = self._find_default_model_path()

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Silero VAD ONNX model not found at {model_path}")

        # Initialize ONNX session
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.enable_cpu_mem_arena = False
        opts.log_severity_level = 4  # Suppress internal ONNX warnings

        self.session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )

        # Initialize recurrent states
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.context_size), dtype=np.float32)

    def _find_default_model_path(self) -> str:
        """Find bundled Silero VAD ONNX model from faster-whisper or local assets."""
        try:
            from faster_whisper.vad import get_assets_path
            path_v6 = os.path.join(get_assets_path(), "silero_vad_v6.onnx")
            if os.path.exists(path_v6):
                return path_v6
            path_v5 = os.path.join(get_assets_path(), "silero_vad.onnx")
            if os.path.exists(path_v5):
                return path_v5
        except Exception:
            pass

        # Fallback to current directory assets
        local_path = os.path.join(os.path.dirname(__file__), "assets", "silero_vad_v6.onnx")
        return local_path

    def reset_state(self) -> None:
        """Reset internal recurrent states and context buffer for a fresh session."""
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.context_size), dtype=np.float32)

    def process_frame(self, audio_frame: np.ndarray) -> float:
        """
        Process a single audio frame and return speech probability (0.0 to 1.0).
        audio_frame: 1D numpy array of float32 in [-1.0, 1.0] or int16 PCM.
        """
        if audio_frame.dtype == np.int16:
            # Convert PCM16 to float32
            audio_frame = audio_frame.astype(np.float32) / 32768.0
        elif audio_frame.dtype != np.float32:
            audio_frame = audio_frame.astype(np.float32)

        if audio_frame.ndim > 1:
            audio_frame = audio_frame.squeeze()

        # Check sample count
        if audio_frame.shape[0] != self.num_samples:
            if audio_frame.shape[0] < self.num_samples:
                # Zero-pad if frame is short
                audio_frame = np.pad(audio_frame, (0, self.num_samples - audio_frame.shape[0]))
            else:
                audio_frame = audio_frame[:self.num_samples]

        # Reshape to (1, num_samples)
        chunk = audio_frame.reshape(1, self.num_samples)

        # Concatenate context: shape (1, context_size + num_samples) = (1, 576)
        input_tensor = np.concatenate([self._context, chunk], axis=1)

        # Run ONNX inference
        outputs = self.session.run(
            None,
            {
                "input": input_tensor,
                "h": self._h,
                "c": self._c,
            },
        )

        speech_prob = float(outputs[0][0])
        self._h = outputs[1]
        self._c = outputs[2]

        # Update context buffer with the trailing samples of current chunk
        self._context = chunk[:, -self.context_size:].copy()

        return speech_prob

    def is_speech(self, audio_frame: np.ndarray, custom_threshold: Optional[float] = None) -> Tuple[bool, float]:
        """
        Stateful check if the audio chunk contains speech.
        Returns (is_speech_bool, speech_probability).
        """
        prob = self.process_frame(audio_frame)
        thresh = custom_threshold if custom_threshold is not None else self.threshold
        return (prob >= thresh, prob)
