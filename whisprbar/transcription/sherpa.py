"""Sherpa-onnx streaming transcription backend for WhisprBar."""

import os
import threading
from typing import Optional

import numpy as np

from .base import Transcriber
from whisprbar.config import cfg
from whisprbar.utils import debug
from whisprbar.audio import SAMPLE_RATE


class StreamingTranscriber(Transcriber):
    """Streaming transcription backend using sherpa-onnx Whisper models.

    Transcribes audio using sherpa-onnx ONNX runtime. Supports streaming.
    Model is downloaded from Hugging Face on first use.
    """

    def __init__(self):
        """Initialize sherpa-onnx transcriber."""
        self.recognizer = None
        self.model_lock = threading.Lock()
        self.model_name = None

    def ensure_model(self) -> bool:
        """Ensure sherpa-onnx model is loaded.

        Returns:
            True if model is ready, False on error
        """
        with self.model_lock:
            if self.recognizer is not None:
                return True

            model_name = cfg.get("streaming_model", "tiny")

            # Import sherpa_onnx
            try:
                import sherpa_onnx
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                debug(f"sherpa-onnx import failed: {exc}")
                return False

            # Download model if needed
            try:
                model_dir = snapshot_download(
                    repo_id=f"csukuangfj/sherpa-onnx-whisper-{model_name}",
                    cache_dir=os.path.expanduser("~/.cache/sherpa-onnx"),
                )
                debug(f"sherpa-onnx model downloaded to: {model_dir}")
            except Exception as exc:
                debug(f"Model download failed: {exc}")
                return False

            # Create recognizer
            try:
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                    encoder=os.path.join(model_dir, f"{model_name}-encoder.int8.onnx"),
                    decoder=os.path.join(model_dir, f"{model_name}-decoder.int8.onnx"),
                    tokens=os.path.join(model_dir, f"{model_name}-tokens.txt"),
                    language=cfg.get("language", "de"),
                    task="transcribe",
                    num_threads=2,
                    provider="cpu",
                )
                self.model_name = model_name
                debug(f"sherpa-onnx recognizer created with model: {model_name}")
                return True
            except Exception as exc:
                debug(f"Failed to create recognizer: {exc}")
                return False

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using sherpa-onnx.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code (currently not used by sherpa-onnx)

        Returns:
            Transcribed text or None on error
        """
        debug("StreamingTranscriber.transcribe() called")
        if not self.ensure_model():
            debug("sherpa-onnx model not available")
            return None

        try:
            # Resample to 16kHz if needed (Whisper always uses 16kHz)
            target_sr = 16000
            if audio.shape[0] > 0:
                current_sr = SAMPLE_RATE
                if current_sr != target_sr:
                    debug(f"Resampling audio from {current_sr}Hz to {target_sr}Hz")
                    # Simple resampling using numpy
                    duration = len(audio) / current_sr
                    target_length = int(duration * target_sr)
                    indices = np.linspace(0, len(audio) - 1, target_length)
                    audio = np.interp(indices, np.arange(len(audio)), audio)

            # Normalize audio to float32 [-1, 1]
            pcm = np.clip(audio, -1.0, 1.0).astype(np.float32)
            debug(f"Audio prepared: {len(pcm)} samples")

            # Create stream and transcribe
            debug("Creating sherpa-onnx stream...")
            stream = self.recognizer.create_stream()
            debug("Feeding audio to stream...")
            stream.accept_waveform(target_sr, pcm)
            debug("Decoding stream...")
            self.recognizer.decode_stream(stream)
            debug("Decoding complete, getting result...")

            text = stream.result.text.strip()
            debug(f"Raw transcription result: '{text}'")

            # Filter out Whisper hallucinations
            if text in ("[Musik]", "[Music]", "[Silence]", "[BLANK_AUDIO]", ""):
                debug("Filtered out hallucination")
                return None

            debug(f"sherpa-onnx transcription: {text[:100]}...")
            return text

        except Exception as exc:
            debug(f"sherpa-onnx transcription failed: {exc}")
            import traceback

            debug(traceback.format_exc())
            return None

    def supports_streaming(self) -> bool:
        """Check if streaming is supported.

        Returns:
            True (sherpa-onnx supports streaming)
        """
        return True

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            Backend name with model info if available
        """
        if self.model_name:
            return f"sherpa-onnx streaming ({self.model_name})"
        return "sherpa-onnx streaming"

    def unload(self) -> None:
        """Unload sherpa-onnx recognizer to free memory."""
        with self.model_lock:
            if self.recognizer is not None:
                # Delete recognizer and force garbage collection
                del self.recognizer
                self.recognizer = None
                self.model_name = None
                import gc
                gc.collect()
                debug("sherpa-onnx recognizer unloaded and memory freed")
