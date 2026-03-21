"""Local faster-whisper transcription backend for WhisprBar."""

import threading
from typing import Optional

import numpy as np

from .base import Transcriber
from whisprbar.config import cfg
from whisprbar.utils import debug


class FasterWhisperTranscriber(Transcriber):
    """Local faster-whisper transcription backend (CPU/GPU).

    Transcribes audio locally using faster-whisper. Supports CPU and GPU.
    Model is downloaded to ~/.cache/huggingface/hub/ on first use.
    """

    def __init__(self):
        """Initialize faster-whisper transcriber."""
        self.model = None
        self.model_lock = threading.Lock()
        self.model_size = None
        self.device = None

    def ensure_model(self) -> bool:
        """Ensure faster-whisper model is loaded.

        Returns:
            True if model is ready, False on error
        """
        with self.model_lock:
            if self.model is not None:
                return True

            # Get model settings from config
            model_size = cfg.get("faster_whisper_model", "medium")
            device = cfg.get("faster_whisper_device", "cpu")
            compute_type = cfg.get("faster_whisper_compute_type", "int8")

            try:
                from faster_whisper import WhisperModel

                debug(
                    f"Loading faster-whisper: {model_size} on {device} ({compute_type})"
                )

                # Model will be downloaded to cache automatically
                self.model = WhisperModel(
                    model_size,
                    device=device,
                    compute_type=compute_type,
                    download_root=None,  # Use default cache
                )

                self.model_size = model_size
                self.device = device
                debug("faster-whisper model loaded successfully")
                return True

            except Exception as exc:
                debug(f"Failed to load faster-whisper model: {exc}")
                return False

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using faster-whisper.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code

        Returns:
            Transcribed text or None on error
        """
        if not self.ensure_model():
            return None

        try:
            # Prepare audio (faster-whisper expects float32)
            pcm = np.clip(audio, -1.0, 1.0).astype(np.float32)

            # Transcribe
            segments, info = self.model.transcribe(
                pcm,
                language=language,
                beam_size=5,
                vad_filter=False,  # We already do VAD preprocessing
                word_timestamps=False,
            )

            # Collect all segments
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            result = " ".join(text_parts).strip()
            debug(f"faster-whisper transcription: {len(result)} chars")
            return result

        except Exception as exc:
            debug(f"faster-whisper transcription failed: {exc}")
            return None

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            Backend name with model info if available
        """
        if self.model_size:
            return f"faster-whisper ({self.model_size}, {self.device})"
        return "faster-whisper (offline)"

    def unload(self) -> None:
        """Unload faster-whisper model to free memory (~4 GB for large model)."""
        with self.model_lock:
            if self.model is not None:
                # Delete model and force garbage collection
                del self.model
                self.model = None
                self.model_size = None
                self.device = None
                import gc
                gc.collect()
                debug("faster-whisper model unloaded and memory freed")
