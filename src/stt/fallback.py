"""
STT fallback integration using whisper-stt service.

Provides server-side speech-to-text transcription for browsers without
Web Speech API support. Accepts audio files (webm/opus) and forwards
to the deployed whisper-stt service.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class STTFallback:
    """
    Speech-to-text fallback using whisper-stt service.

    whisper-stt is exposed at whisper.ardenone.com via Traefik on the
    Tailscale mesh. This module provides:
    - Audio file transcription
    - Fallback for browsers without Web Speech API
    """

    # whisper-stt service URL (Tailscale mesh)
    # Configurable via ADC_WHISPER_STT_URL env var
    DEFAULT_STT_URL = "https://whisper.ardenone.com"

    def __init__(self, stt_url: str | None = None):
        self.stt_url = stt_url or os.getenv("ADC_WHISPER_STT_URL", self.DEFAULT_STT_URL)
        self._is_available = None  # None = unknown, True = available, False = unavailable
        self._failure_count = 0

    async def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = "webm",
    ) -> Optional[str]:
        """
        Transcribe audio data to text using whisper-stt.

        Args:
            audio_data: Raw audio bytes (webm/opus format from MediaRecorder)
            audio_format: Audio format hint (default: "webm")

        Returns:
            Transcribed text, or None if transcription failed.

        Raises:
            httpx.RequestError: If the request fails
            httpx.HTTPStatusError: If the request returns an error status
        """
        try:
            # Prepare multipart form data
            files = {
                "file": ("audio.webm", audio_data, "audio/webm"),
            }
            data = {
                "format": audio_format,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                # whisper-stt uses /transcribe endpoint
                response = await client.post(
                    f"{self.stt_url}/transcribe",
                    files=files,
                    data=data,
                )

                if response.status_code == 200:
                    result = response.json()
                    text = result.get("text", "").strip()

                    if text:
                        logger.info(f"STT transcription successful: {text[:50]}...")
                        self._is_available = True
                        return text
                    else:
                        logger.warning("STT returned empty transcription")
                        self._is_available = False
                        return None
                else:
                    error_msg = f"status {response.status_code} - {response.text}"
                    self._handle_transcription_failure(error_msg)
                    return None

        except httpx.RequestError as e:
            error_msg = f"request error: {e}"
            self._handle_transcription_failure(error_msg)
            return None
        except Exception as e:
            error_msg = f"unexpected error: {e}"
            self._handle_transcription_failure(error_msg)
            return None

    async def check_available(self) -> bool:
        """Check if whisper-stt service is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try to reach the health endpoint
                response = await client.get(
                    f"{self.stt_url}/health",
                )
                is_available = response.status_code == 200
                self._is_available = is_available
                return is_available
        except Exception:
            self._is_available = False
            return False

    def get_status(self) -> dict:
        """
        Get the current STT service status.

        Returns:
            Dict with keys:
            - available: bool or None (None = unknown yet)
            - stt_url: str
            - failure_count: int
        """
        return {
            "available": self._is_available,
            "stt_url": self.stt_url,
            "failure_count": self._failure_count,
        }

    def _handle_transcription_failure(self, error_context: str = ""):
        """Handle a transcription failure."""
        self._is_available = False
        self._failure_count += 1
        logger.warning(
            f"STT transcription failed at {self.stt_url}. "
            f"Error: {error_context if error_context else 'unknown error'}. "
            f"Failure #{self._failure_count}."
        )


# Global STT fallback instance
_stt_fallback: Optional[STTFallback] = None


def get_stt_fallback() -> STTFallback:
    """Get or create the global STT fallback instance."""
    global _stt_fallback
    if _stt_fallback is None:
        _stt_fallback = STTFallback()
    return _stt_fallback
