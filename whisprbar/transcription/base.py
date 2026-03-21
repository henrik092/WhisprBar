"""Base transcription classes and shared constants for WhisprBar.

Provides the abstract Transcriber base class and shared constants
used across all transcription backends.
"""

import os
from typing import Optional

import numpy as np

# Transcription model
OPENAI_MODEL = os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe")


class Transcriber:
    """Abstract base class for transcription backends."""

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio and return text. Returns None on error.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code (e.g., "de", "en")

        Returns:
            Transcribed text or None on error
        """
        raise NotImplementedError("Subclasses must implement transcribe()")

    def transcribe_chunk(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe a single chunk. Default implementation uses transcribe().

        Args:
            audio: Audio chunk as float32 numpy array
            language: Language code

        Returns:
            Transcribed text or None on error
        """
        return self.transcribe(audio, language)

    def supports_streaming(self) -> bool:
        """Check if this backend supports streaming transcription.

        Returns:
            True if streaming is supported
        """
        return False

    def get_name(self) -> str:
        """Get backend name for display.

        Returns:
            Human-readable backend name
        """
        raise NotImplementedError("Subclasses must implement get_name()")

    def unload(self) -> None:
        """Unload model/client to free memory.

        Called when backend is switched or app shuts down.
        Subclasses should implement this to free resources.
        """
        pass  # Default implementation does nothing
