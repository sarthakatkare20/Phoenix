"""
Sarvam AI Saaras STT (Speech-to-Text) Engine for Project Phoenix.
Optimized for Indian Accents, Indian English (en-IN), Hindi (hi-IN), and Code-Mixed Hinglish.
Uses Saaras V4 via Sarvam AI REST API.
"""

import io
import logging
import os
from typing import Any, Dict, Optional, Union
import numpy as np

try:
    import httpx
except ImportError:
    httpx = None

try:
    import soundfile as sf
except ImportError:
    sf = None

from config import settings

logger = logging.getLogger("paaro.stt.sarvam")

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


class SarvamSTTClient:
    """Client for Sarvam AI Saaras Speech-to-Text API."""

    def __init__(self, api_key: Optional[str] = None):
        self._explicit_key = api_key

    @property
    def api_key(self) -> Optional[str]:
        k = self._explicit_key or getattr(settings, "SARVAM_API_KEY", None) or os.environ.get("SARVAM_API_KEY")
        if not k:
            for env_path in [".env.local", ".env"]:
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("SARVAM_API_KEY="):
                                return line.strip().split("=", 1)[1].strip()
        return k

    @property
    def is_configured(self) -> bool:
        k = self.api_key
        return bool(k and k.strip())

    async def transcribe_async(
        self,
        audio_data: Union[bytes, np.ndarray, str],
        sample_rate: int = 16000,
        model: str = "saaras:v4",
        mode: str = "codemix",
        language_code: str = "hi-IN",
    ) -> Optional[Dict[str, Any]]:
        """
        Transcribe audio using Sarvam Saaras V4.
        Supports raw wav bytes, numpy float32/int16 PCM, or file path.
        """
        if not self.is_configured:
            logger.debug("Sarvam STT not configured (SARVAM_API_KEY is missing).")
            return None

        if httpx is None:
            logger.warning("httpx is required for Sarvam STT async requests.")
            return None

        # Prepare audio bytes in memory
        wav_bytes: bytes
        if isinstance(audio_data, str):
            with open(audio_data, "rb") as f:
                wav_bytes = f.read()
        elif isinstance(audio_data, bytes):
            wav_bytes = audio_data
        elif isinstance(audio_data, np.ndarray):
            if sf is None:
                logger.error("soundfile is required to convert numpy array to WAV for Sarvam STT.")
                return None
            bio = io.BytesIO()
            # Convert float32 to int16 PCM
            if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
                pcm16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
            else:
                pcm16 = audio_data.astype(np.int16)
            sf.write(bio, pcm16, sample_rate, format="WAV", subtype="PCM_16")
            wav_bytes = bio.getvalue()
        else:
            logger.error("Unsupported audio data type for Sarvam STT: %s", type(audio_data))
            return None

        headers = {
            "api-subscription-key": self.api_key.strip(),
        }

        data = {
            "model": model or getattr(settings, "SARVAM_STT_MODEL", "saaras:v4"),
            "mode": mode or getattr(settings, "SARVAM_STT_MODE", "codemix"),
            "language_code": language_code or getattr(settings, "SARVAM_LANGUAGE_CODE", "hi-IN"),
        }

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(SARVAM_STT_URL, headers=headers, data=data, files=files)
                if res.status_code == 200:
                    resp_data = res.json()
                    transcript = resp_data.get("transcript", "").strip()
                    logger.info("[SARVAM STT] Success (%s): '%s'", mode, transcript)
                    return {
                        "transcript": transcript,
                        "language_code": resp_data.get("language_code", language_code),
                        "raw": resp_data,
                    }
                else:
                    logger.error("[SARVAM STT] API error (%d): %s", res.status_code, res.text[:200])
                    return None
        except Exception as e:
            logger.error("[SARVAM STT] Request failed: %s", e)
            return None

    def transcribe_sync(
        self,
        audio_data: Union[bytes, np.ndarray, str],
        sample_rate: int = 16000,
        model: str = "saaras:v4",
        mode: str = "codemix",
        language_code: str = "hi-IN",
    ) -> Optional[Dict[str, Any]]:
        """Synchronous wrapper for transcribe_async."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(
                        asyncio.run,
                        self.transcribe_async(audio_data, sample_rate, model, mode, language_code)
                    ).result()
            return loop.run_until_complete(
                self.transcribe_async(audio_data, sample_rate, model, mode, language_code)
            )
        except Exception:
            return asyncio.run(self.transcribe_async(audio_data, sample_rate, model, mode, language_code))


sarvam_client = SarvamSTTClient()
