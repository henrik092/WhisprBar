"""ElevenLabs Scribe v2 Realtime transcription backend for WhisprBar."""

import os
import threading
from typing import Optional

import numpy as np

from .base import Transcriber
from whisprbar.config import load_env_file_values
from whisprbar.utils import debug
from whisprbar.audio import SAMPLE_RATE


class ElevenLabsTranscriber(Transcriber):
    """ElevenLabs Scribe v2 Realtime transcription backend.

    Transcribes audio using ElevenLabs Scribe v2 Realtime API.
    Requires ELEVENLABS_API_KEY.
    """

    def __init__(self):
        """Initialize ElevenLabs transcriber."""
        self.client = None
        self.client_lock = threading.Lock()

    def ensure_client(self) -> bool:
        """Ensure ElevenLabs client is initialized.

        Returns:
            True if client is ready, False if API key missing
        """
        with self.client_lock:
            if self.client is not None:
                return True

            # Try environment variable first
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                # Try config file
                env_values = load_env_file_values()
                api_key = env_values.get("ELEVENLABS_API_KEY")

            if not api_key:
                debug("ElevenLabs API key not found")
                return False

            try:
                from elevenlabs import ElevenLabs

                self.client = ElevenLabs(api_key=api_key)
                debug("ElevenLabs client initialized")
                return True
            except Exception as exc:
                debug(f"Failed to initialize ElevenLabs client: {exc}")
                return False

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using ElevenLabs Scribe v2 Realtime.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code (e.g., "de", "en")

        Returns:
            Transcribed text or None on error
        """
        if not self.ensure_client():
            return None

        try:
            import asyncio
            import base64
            from elevenlabs import (
                AudioFormat,
                CommitStrategy,
                RealtimeAudioOptions,
                RealtimeEvents,
            )

            # Convert language code to ElevenLabs format
            # ElevenLabs accepts ISO-639-1 codes (e.g., "de", "en")
            # No conversion needed - WhisprBar already uses compatible codes
            lang_code = language

            # Prepare audio: clip to [-1, 1] and convert to PCM16
            pcm = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm * 32767).astype(np.int16)

            # Convert to base64
            audio_bytes = pcm16.tobytes()
            audio_base64 = base64.b64encode(audio_bytes).decode()

            # Async transcription function
            async def transcribe_async():
                connection = None
                try:
                    # Connect to ElevenLabs Scribe v2 Realtime with timeout
                    connection = await asyncio.wait_for(
                        self.client.speech_to_text.realtime.connect(
                            RealtimeAudioOptions(
                                model_id="scribe_v2_realtime",
                                audio_format=AudioFormat.PCM_16000,
                                sample_rate=SAMPLE_RATE,
                                commit_strategy=CommitStrategy.MANUAL,
                                language_code=lang_code,
                            )
                        ),
                        timeout=30.0  # 30 second connection timeout
                    )

                    # Storage for result with thread-safe event
                    result_text = []
                    transcript_received = asyncio.Event()

                    # Callback for committed transcript
                    def on_committed_transcript(data):
                        text = data.get("text", "")
                        if text:
                            result_text.append(text)
                            debug(f"ElevenLabs committed: {text}")
                            transcript_received.set()

                    # Register event handler
                    connection.on(
                        RealtimeEvents.COMMITTED_TRANSCRIPT, on_committed_transcript
                    )

                    # Send audio in chunks (max 1 second = 32000 bytes at 16kHz)
                    chunk_size = 32000
                    for i in range(0, len(audio_base64), chunk_size):
                        chunk = audio_base64[i : i + chunk_size]
                        await connection.send(
                            {"audio_base_64": chunk, "sample_rate": SAMPLE_RATE}
                        )

                    # Commit and wait for final result
                    await connection.commit()

                    # Wait for transcript with timeout instead of arbitrary sleep
                    try:
                        await asyncio.wait_for(transcript_received.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        debug("ElevenLabs transcript wait timed out, using partial result")

                    # Return combined transcript
                    return " ".join(result_text).strip()

                except asyncio.TimeoutError:
                    debug("ElevenLabs connection timed out")
                    return None
                except Exception as exc:
                    debug(f"ElevenLabs async transcription failed: {exc}")
                    return None
                finally:
                    # Always close connection to prevent resource leak
                    if connection is not None:
                        try:
                            await connection.close()
                        except Exception as close_exc:
                            debug(f"Error closing ElevenLabs connection: {close_exc}")

            # Run async function in event loop
            transcript = asyncio.run(transcribe_async())

            if transcript:
                debug(f"ElevenLabs transcription: {len(transcript)} chars")
                return transcript
            else:
                debug("ElevenLabs returned empty transcript")
                return None

        except Exception as exc:
            debug(f"ElevenLabs transcription failed: {exc}")
            return None

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            "ElevenLabs Scribe v2 Realtime"
        """
        return "ElevenLabs Scribe v2 Realtime"

    def unload(self) -> None:
        """Unload ElevenLabs client to free resources."""
        with self.client_lock:
            if self.client is not None:
                self.client = None
                debug("ElevenLabs client unloaded")
