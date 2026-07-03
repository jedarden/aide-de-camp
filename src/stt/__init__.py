"""
STT fallback module.

Provides server-side speech-to-text transcription for browsers without
Web Speech API support.
"""

from .fallback import STTFallback, get_stt_fallback

__all__ = ["STTFallback", "get_stt_fallback"]
