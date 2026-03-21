"""OpenAI Whisper API transcription backend for WhisprBar."""

import contextlib
import os
import tempfile
import threading
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from .base import Transcriber, OPENAI_MODEL
from whisprbar.config import load_env_file_values
from whisprbar.utils import debug
from whisprbar.audio import SAMPLE_RATE, CHANNELS


class OpenAITranscriber(Transcriber):
    """OpenAI Whisper API transcription backend.

    Transcribes audio using OpenAI's cloud API. Requires OPENAI_API_KEY.
    """

    def __init__(self):
        """Initialize OpenAI transcriber."""
        self.client = None
        self.client_lock = threading.Lock()

    def ensure_client(self) -> bool:
        """Ensure OpenAI client is initialized.

        Returns:
            True if client is ready, False if API key missing
        """
        with self.client_lock:
            if self.client is not None:
                return True

            # Try environment variable first
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                # Try config file
                env_values = load_env_file_values()
                api_key = env_values.get("OPENAI_API_KEY")

            if not api_key:
                debug("OpenAI API key not found")
                return False

            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=api_key)
                debug("OpenAI client initialized")
                return True
            except Exception as exc:
                debug(f"Failed to initialize OpenAI client: {exc}")
                return False

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using OpenAI Whisper API.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code

        Returns:
            Transcribed text or None on error
        """
        if not self.ensure_client():
            return None

        try:
            # Prepare audio: clip to [-1, 1] and convert to PCM16
            pcm = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm * 32767).astype(np.int16)

            # Write to temp WAV file in WhisprBar's temp directory
            from whisprbar.utils import get_whisprbar_temp_dir
            temp_dir = get_whisprbar_temp_dir()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=temp_dir) as tmp:
                tmp_path = Path(tmp.name)

            try:
                # Create WAV file
                with wave.open(str(tmp_path), "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(pcm16.tobytes())

                # Call OpenAI API
                with tmp_path.open("rb") as handle:
                    response = self.client.audio.transcriptions.create(
                        model=OPENAI_MODEL,
                        file=handle,
                        language=language,
                        temperature=0.0,
                    )

                transcript = response.text.strip()
                debug(f"OpenAI transcription: {len(transcript)} chars")
                return transcript

            finally:
                # Clean up temp file
                with contextlib.suppress(Exception):
                    tmp_path.unlink()

        except Exception as exc:
            debug(f"OpenAI transcription failed: {exc}")
            return None

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            "OpenAI Whisper API"
        """
        return "OpenAI Whisper API"

    def unload(self) -> None:
        """Unload OpenAI client to free resources."""
        with self.client_lock:
            if self.client is not None:
                self.client = None
                debug("OpenAI client unloaded")
