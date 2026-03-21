"""Transcription backends and processing for WhisprBar.

Provides multiple transcription backends (OpenAI API, Deepgram Nova-3,
ElevenLabs Scribe v2, faster-whisper local, sherpa-onnx streaming),
audio chunking for long recordings, and text postprocessing.

This package is a drop-in replacement for the monolithic transcription.py module.
All public names are re-exported here for backwards compatibility.
"""

# Base class and constants
from .base import Transcriber, OPENAI_MODEL

# Backend implementations
from .openai import OpenAITranscriber
from .deepgram import DeepgramTranscriber
from .elevenlabs import ElevenLabsTranscriber
from .faster_whisper import FasterWhisperTranscriber
from .sherpa import StreamingTranscriber

# Factory and instance management
from .factory import get_transcriber

# Chunking and main transcription orchestration
from .chunking import (
    transcribe_audio,
    transcribe_audio_chunked,
    transcribe_chunk,
    merge_chunk_transcripts,
)

# Postprocessing
from .postprocess import (
    postprocess_transcript,
    postprocess_fix_spacing,
    postprocess_fix_capitalization,
)

# Re-export from audio for backwards compatibility
# (split_audio_into_chunks was historically accessible via transcription module)
from whisprbar.audio import split_audio_into_chunks

__all__ = [
    # Base
    "Transcriber",
    "OPENAI_MODEL",
    # Backends
    "OpenAITranscriber",
    "DeepgramTranscriber",
    "ElevenLabsTranscriber",
    "FasterWhisperTranscriber",
    "StreamingTranscriber",
    # Factory
    "get_transcriber",
    # Chunking / orchestration
    "transcribe_audio",
    "transcribe_audio_chunked",
    "transcribe_chunk",
    "merge_chunk_transcripts",
    # Postprocessing
    "postprocess_transcript",
    "postprocess_fix_spacing",
    "postprocess_fix_capitalization",
    # Re-exported from audio
    "split_audio_into_chunks",
]
