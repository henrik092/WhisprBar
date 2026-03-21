"""Transcriber factory and instance management for WhisprBar."""

import threading
from typing import Optional

from .base import Transcriber
from whisprbar.config import cfg
from whisprbar.utils import debug

# Global transcriber instance
_transcriber: Optional[Transcriber] = None
_transcriber_lock = threading.Lock()


def get_transcriber() -> Transcriber:
    """Get the current transcriber instance based on config.

    Creates a new transcriber if backend has changed or none exists.
    Thread-safe.

    Returns:
        Transcriber instance (OpenAI, FasterWhisper, Streaming, ElevenLabs, or Deepgram)
    """
    global _transcriber

    backend = cfg.get("transcription_backend", "openai")

    with _transcriber_lock:
        # Reset transcriber if backend changed
        if _transcriber is not None:
            # Lazy imports to determine current backend type
            from .openai import OpenAITranscriber
            from .faster_whisper import FasterWhisperTranscriber
            from .sherpa import StreamingTranscriber
            from .elevenlabs import ElevenLabsTranscriber
            from .deepgram import DeepgramTranscriber

            current_backend = (
                "openai"
                if isinstance(_transcriber, OpenAITranscriber)
                else "faster_whisper"
                if isinstance(_transcriber, FasterWhisperTranscriber)
                else "streaming"
                if isinstance(_transcriber, StreamingTranscriber)
                else "elevenlabs"
                if isinstance(_transcriber, ElevenLabsTranscriber)
                else "deepgram"
                if isinstance(_transcriber, DeepgramTranscriber)
                else "unknown"
            )
            if current_backend != backend:
                debug(f"Backend changed from {current_backend} to {backend}")
                # Unload old model/client to free memory before switching
                _transcriber.unload()
                _transcriber = None

        # Create transcriber if needed
        if _transcriber is None:
            if backend == "streaming":
                from .sherpa import StreamingTranscriber
                debug("Creating StreamingTranscriber")
                _transcriber = StreamingTranscriber()
            elif backend == "faster_whisper":
                from .faster_whisper import FasterWhisperTranscriber
                debug("Creating FasterWhisperTranscriber")
                _transcriber = FasterWhisperTranscriber()
            elif backend == "elevenlabs":
                from .elevenlabs import ElevenLabsTranscriber
                debug("Creating ElevenLabsTranscriber")
                _transcriber = ElevenLabsTranscriber()
            elif backend == "deepgram":
                from .deepgram import DeepgramTranscriber
                debug("Creating DeepgramTranscriber")
                _transcriber = DeepgramTranscriber()
            else:
                # Default to OpenAI
                from .openai import OpenAITranscriber
                debug("Creating OpenAITranscriber")
                _transcriber = OpenAITranscriber()

        return _transcriber
