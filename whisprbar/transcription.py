"""Transcription backends and processing for WhisprBar.

Provides multiple transcription backends (OpenAI API, faster-whisper, sherpa-onnx),
audio chunking for long recordings, and text postprocessing.
"""

import contextlib
import json
import os
import sys
import tempfile
import threading
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

# Import from whisprbar modules
from .config import cfg, load_env_file_values
from .utils import debug, notify, write_history
from .ui import show_live_overlay, update_live_overlay, hide_live_overlay

# Import audio constants for duration calculations and file writing
# Note: apply_vad/apply_noise_reduction are called in main.py BEFORE transcription
# This avoids circular import risk and double processing
from .audio import SAMPLE_RATE, CHANNELS

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
            from .utils import get_whisprbar_temp_dir
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


class DeepgramTranscriber(Transcriber):
    """Deepgram Nova-3 transcription backend.

    Transcribes audio using Deepgram's Nova-3 model via REST API.
    Requires DEEPGRAM_API_KEY.
    Sub-300ms latency - 6-10x faster than OpenAI Whisper.
    Uses persistent HTTP connection to avoid TCP+TLS handshake per request.
    """

    # Max idle time before proactively closing connection (seconds).
    # Deepgram likely closes idle connections after ~60s; we close earlier
    # to avoid hitting a stale connection that hangs on getresponse().
    _CONN_MAX_IDLE = 25

    def __init__(self):
        """Initialize Deepgram transcriber."""
        self.api_key = None
        self.client_lock = threading.Lock()
        self._conn = None  # Persistent HTTPS connection
        self._conn_used_at = 0.0  # monotonic time of last successful use

    def ensure_client(self) -> bool:
        """Ensure Deepgram API key is available.

        Returns:
            True if API key is ready, False if missing
        """
        with self.client_lock:
            if self.api_key is not None:
                return True

            # Try environment variable first
            api_key = os.getenv("DEEPGRAM_API_KEY")
            if not api_key:
                # Try config file
                env_values = load_env_file_values()
                api_key = env_values.get("DEEPGRAM_API_KEY")

            if not api_key:
                debug("Deepgram API key not found")
                return False

            self.api_key = api_key
            debug("Deepgram API key loaded")
            return True

    def _get_connection(self):
        """Get or create a persistent HTTPS connection to Deepgram.

        Reuses existing connection to avoid TCP+TLS handshake overhead
        (~200-500ms) on subsequent calls. Proactively closes idle
        connections to prevent stale-connection hangs.
        """
        import http.client
        import time as _time

        # Close idle connections proactively to avoid stale-connection hangs
        if self._conn is not None:
            idle = _time.monotonic() - self._conn_used_at
            if idle > self._CONN_MAX_IDLE:
                debug(f"Deepgram: closing idle connection ({idle:.0f}s > {self._CONN_MAX_IDLE}s)")
                with contextlib.suppress(Exception):
                    self._conn.close()
                self._conn = None

        if self._conn is not None:
            return self._conn

        self._conn = http.client.HTTPSConnection("api.deepgram.com", timeout=30)
        self._conn_used_at = _time.monotonic()
        debug("Deepgram: new HTTPS connection established")
        return self._conn

    def _send_request(self, url_path: str, wav_data: bytes) -> str:
        """Send request with automatic reconnection on stale connections."""
        import http.client
        import time as _time
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav",
            "Connection": "keep-alive",
        }
        conn = self._get_connection()
        try:
            conn.request("POST", url_path, body=wav_data, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            self._conn_used_at = _time.monotonic()
            return data
        except (http.client.HTTPException, OSError, ConnectionError):
            # Connection stale/lost, reconnect and retry once
            debug("Deepgram: connection lost, reconnecting...")
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None
            conn = self._get_connection()
            conn.request("POST", url_path, body=wav_data, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            self._conn_used_at = _time.monotonic()
            return data

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using Deepgram Nova-3 REST API.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code (e.g., "de", "en")

        Returns:
            Transcribed text or None on error
        """
        if not self.ensure_client():
            return None

        try:
            import io

            # Prepare audio: clip to [-1, 1] and convert to PCM16
            pcm = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm * 32767).astype(np.int16)

            # Write to WAV in memory
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm16.tobytes())

            wav_data = wav_buffer.getvalue()

            # Build Deepgram API URL path with parameters
            # Nova-3 with language=multi handles code-switching (e.g. German
            # with English words) natively without dropping foreign words.
            url_path = "/v1/listen?model=nova-3&language=multi&smart_format=true&punctuate=true"

            # Send request via persistent connection
            debug("Sending audio to Deepgram Nova-3 (language=multi)...")
            response_data = self._send_request(url_path, wav_data)
            result = json.loads(response_data)

            # Extract transcript from response
            # Deepgram response structure:
            # {"results": {"channels": [{"alternatives": [{"transcript": "..."}]}]}}
            try:
                transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]
                transcript = transcript.strip()
                debug(f"Deepgram transcription: {len(transcript)} chars")
                return transcript
            except (KeyError, IndexError) as e:
                debug(f"Deepgram response parsing failed: {e}")
                debug(f"Response: {result}")
                return None

        except Exception as exc:
            debug(f"Deepgram transcription failed: {exc}")
            return None

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            "Deepgram Nova-3"
        """
        return "Deepgram Nova-3 (multilingual)"

    def unload(self) -> None:
        """Unload Deepgram client and close persistent connection."""
        with self.client_lock:
            if self._conn is not None:
                with contextlib.suppress(Exception):
                    self._conn.close()
                self._conn = None
            if self.api_key is not None:
                self.api_key = None
                debug("Deepgram client unloaded")


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
                debug("Creating StreamingTranscriber")
                _transcriber = StreamingTranscriber()
            elif backend == "faster_whisper":
                debug("Creating FasterWhisperTranscriber")
                _transcriber = FasterWhisperTranscriber()
            elif backend == "elevenlabs":
                debug("Creating ElevenLabsTranscriber")
                _transcriber = ElevenLabsTranscriber()
            elif backend == "deepgram":
                debug("Creating DeepgramTranscriber")
                _transcriber = DeepgramTranscriber()
            else:
                # Default to OpenAI
                debug("Creating OpenAITranscriber")
                _transcriber = OpenAITranscriber()

        return _transcriber


def split_audio_into_chunks(
    audio: np.ndarray,
) -> List[Tuple[np.ndarray, int, int]]:
    """Split audio into overlapping chunks for parallel processing.

    Args:
        audio: Audio data as float32 numpy array

    Returns:
        List of (chunk_audio, start_sample, end_sample) tuples
    """
    duration_seconds = audio.size / SAMPLE_RATE
    chunk_duration = max(5.0, float(cfg.get("chunk_duration_seconds", 30.0)))
    overlap_duration = max(
        0.5, min(chunk_duration * 0.2, float(cfg.get("chunk_overlap_seconds", 2.0)))
    )

    chunk_samples = int(chunk_duration * SAMPLE_RATE)
    overlap_samples = int(overlap_duration * SAMPLE_RATE)
    step_samples = chunk_samples - overlap_samples

    chunks: List[Tuple[np.ndarray, int, int]] = []
    start = 0

    while start < audio.size:
        end = min(start + chunk_samples, audio.size)
        chunk = audio[start:end]

        # Skip chunks that are too short (min 1 second)
        if chunk.size < int(SAMPLE_RATE * 1.0):
            break

        chunks.append((chunk, start, end))

        # If we've reached the end, stop
        if end >= audio.size:
            break

        start += step_samples

    debug(
        f"Split {duration_seconds:.1f}s audio into {len(chunks)} chunks "
        f"(chunk={chunk_duration:.1f}s, overlap={overlap_duration:.1f}s)"
    )
    return chunks


def transcribe_chunk(
    chunk_audio: np.ndarray, chunk_index: int, total_chunks: int, language: str = "de"
) -> Optional[str]:
    """Transcribe a single chunk using current transcriber backend.

    Args:
        chunk_audio: Audio chunk as float32 numpy array
        chunk_index: Index of this chunk (0-based)
        total_chunks: Total number of chunks
        language: Language code (e.g., "de", "en")

    Returns:
        Transcribed text or None on error
    """
    try:
        chunk_duration = chunk_audio.size / SAMPLE_RATE
        debug(
            f"Transcribing chunk {chunk_index + 1}/{total_chunks} "
            f"({chunk_duration:.1f}s)"
        )

        transcriber = get_transcriber()
        transcript = transcriber.transcribe_chunk(chunk_audio, language)

        if transcript:
            debug(f"Chunk {chunk_index + 1}/{total_chunks}: {len(transcript)} chars")

        return transcript

    except Exception as exc:
        print(
            f"[ERROR] Chunk {chunk_index + 1} transcription failed: {exc}",
            file=sys.stderr,
        )
        return None


def merge_chunk_transcripts(
    transcripts: List[str], chunks_info: List[Tuple[np.ndarray, int, int]]
) -> str:
    """Merge overlapping chunk transcripts intelligently.

    Attempts to detect and remove duplicate text at chunk boundaries.

    Args:
        transcripts: List of transcript strings
        chunks_info: List of chunk metadata (not currently used)

    Returns:
        Merged transcript
    """
    if not transcripts:
        return ""

    if len(transcripts) == 1:
        return transcripts[0]

    # Start with first transcript
    merged = transcripts[0]

    # Merge remaining transcripts
    for i, transcript in enumerate(transcripts[1:], start=1):
        if not transcript:
            continue

        # Try to find overlap by checking last N words of merged
        # with first N words of current
        merged_words = merged.split()
        transcript_words = transcript.split()

        # Check for overlapping phrases (up to 10 words)
        overlap_found = False
        for overlap_len in range(
            min(10, len(merged_words), len(transcript_words)), 0, -1
        ):
            if merged_words[-overlap_len:] == transcript_words[:overlap_len]:
                # Found overlap, merge by skipping the duplicate
                merged = " ".join(merged_words + transcript_words[overlap_len:])
                overlap_found = True
                debug(f"Merged chunk {i} with {overlap_len}-word overlap")
                break

        if not overlap_found:
            # No overlap found, just append with space
            merged = merged + " " + transcript

    return merged


def transcribe_audio_chunked(audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio using chunking for better performance on long recordings.

    Splits audio into chunks, transcribes in parallel, and merges results.

    Args:
        audio: Audio data as float32 numpy array
        language: Language code (e.g., "de", "en")

    Returns:
        Transcribed text or None on error
    """
    chunks = split_audio_into_chunks(audio)

    if not chunks:
        debug("No chunks created, audio too short")
        return None

    notify(f"Transcribing {len(chunks)} chunks...")
    update_live_overlay(
        f"Transcribing {len(chunks)} chunks...", f"0/{len(chunks)} completed"
    )

    # Transcribe chunks in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed

    max_workers = min(5, len(chunks))  # Max 5 parallel requests
    transcripts: List[Optional[str]] = [None] * len(chunks)
    completed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(transcribe_chunk, chunk_audio, idx, len(chunks), language): idx
            for idx, (chunk_audio, _, _) in enumerate(chunks)
        }

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                transcripts[idx] = future.result()
                completed_count += 1

                # Update overlay with progress
                partial_text = " ".join(t for t in transcripts if t is not None)
                update_live_overlay(
                    partial_text or "Processing...",
                    f"Chunk {completed_count}/{len(chunks)} completed",
                )
            except Exception as exc:
                print(f"[ERROR] Chunk {idx + 1} failed: {exc}", file=sys.stderr)
                transcripts[idx] = None
                completed_count += 1

    # Filter out failed chunks
    valid_transcripts = [t for t in transcripts if t]

    if not valid_transcripts:
        debug("All chunks failed transcription")
        return None

    # Merge transcripts
    merged = merge_chunk_transcripts(valid_transcripts, chunks)
    debug(
        f"Final merged transcript: {len(merged)} chars from "
        f"{len(valid_transcripts)}/{len(chunks)} chunks"
    )

    return merged


def postprocess_fix_spacing(text: str) -> str:
    """Fix spacing issues in transcribed text.

    Removes multiple spaces, fixes punctuation spacing, and cleans up quotes/parens.

    Args:
        text: Input text

    Returns:
        Text with fixed spacing
    """
    import re

    # Remove multiple spaces
    text = re.sub(r" +", " ", text)

    # Fix punctuation spacing: remove space before, ensure space after
    # Handles: . , ! ? : ;
    text = re.sub(r"\s+([.,!?:;])", r"\1", text)  # Remove space before
    text = re.sub(r"([.,!?:;])(?=[^\s])", r"\1 ", text)  # Add space after if missing

    # Fix quotes and parentheses
    text = re.sub(r"\(\s+", "(", text)  # No space after opening paren
    text = re.sub(r"\s+\)", ")", text)  # No space before closing paren
    text = re.sub(r'"\s+', '"', text)  # No space after opening quote
    text = re.sub(r'\s+"', '"', text)  # No space before closing quote

    # Fix common formatting issues
    text = re.sub(r"\s+\.", ".", text)  # Remove space before period
    text = re.sub(r"\.\s*\)", ".)", text)  # Fix ". )" to ".)"
    text = re.sub(r"\(\s*\.", "(.", text)  # Fix "( ." to "(."

    return text.strip()


def postprocess_fix_capitalization(text: str, language: str = "de") -> str:
    """Fix capitalization issues in transcribed text.

    Capitalizes first character, after sentence punctuation, and applies
    language-specific rules.

    Args:
        text: Input text
        language: Language code for language-specific rules

    Returns:
        Text with fixed capitalization
    """
    import re

    if not text:
        return text

    # Capitalize first character
    text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()

    # Capitalize after sentence-ending punctuation (. ! ?)
    # Use Unicode-aware pattern to match lowercase letters including ä, ö, ü, é, etc.
    def capitalize_after_punct(match):
        punct = match.group(1)
        space = match.group(2)
        char = match.group(3)
        return punct + space + char.upper()

    text = re.sub(
        r"([.!?])(\s+)([a-zäöüßáéíóúàèìòùâêîôûçñ])",
        capitalize_after_punct,
        text,
        flags=re.IGNORECASE | re.UNICODE
    )

    # Language-specific fixes
    if language == "en":
        # Fix standalone "i" → "I"
        text = re.sub(r"\bi\b", "I", text)
        # Fix "i'" contractions (I'm, I'll, I've, etc.)
        text = re.sub(r"\bi'", "I'", text)

    return text


def postprocess_transcript(text: str, language: str = "de") -> str:
    """Apply all post-processing rules to the transcript.

    Args:
        text: Input transcript
        language: Language code

    Returns:
        Postprocessed transcript
    """
    if not cfg.get("postprocess_enabled"):
        return text

    original_length = len(text)
    debug(f"Post-processing transcript ({original_length} chars)")

    # Apply fixes in order
    if cfg.get("postprocess_fix_spacing", True):
        text = postprocess_fix_spacing(text)

    if cfg.get("postprocess_fix_capitalization", True):
        text = postprocess_fix_capitalization(text, language)

    # TODO: Advanced punctuation correction with transformer model
    if cfg.get("postprocess_fix_punctuation", False):
        debug("Advanced punctuation correction not yet implemented")

    final_length = len(text)
    if final_length != original_length:
        debug(
            f"Post-processing: {original_length} → {final_length} chars "
            f"(Δ{final_length - original_length:+d})"
        )

    return text




def transcribe_audio(audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio and return the text.

    IMPORTANT: Expects audio to be already preprocessed (VAD + noise reduction)
    by the caller (main.py). This function focuses on transcription only.

    This function:
    1. Checks if transcriber is available
    2. Validates audio has sufficient content
    3. Chooses between chunked or single-chunk transcription
    4. Applies postprocessing
    5. Returns the transcript text

    The caller is responsible for:
    - Audio preprocessing (VAD, noise reduction)
    - Clipboard operations
    - Auto-paste
    - Notifications

    Args:
        audio: Preprocessed audio data as float32 numpy array
        language: Language code (e.g., "de", "en")

    Returns:
        Transcribed text or None on error
    """
    # Check if transcriber is available
    transcriber = get_transcriber()
    if isinstance(transcriber, OpenAITranscriber) and not transcriber.ensure_client():
        debug("OpenAI API key not configured")
        return None

    # Show live overlay if enabled
    show_live_overlay(cfg, "Processing audio...")

    try:
        # Audio is already preprocessed (VAD + noise reduction done in main.py)
        processed = audio
        duration = processed.shape[0] / SAMPLE_RATE
        notify("Processing audio...")
        debug(f"Transcribing {duration:.2f}s of preprocessed audio")

        # Check if enough speech remains
        if processed.size < int(SAMPLE_RATE * 0.25):
            debug("Transcription skipped: audio too short (< 0.25s)")
            hide_live_overlay()
            return None

        # Check if we should use chunking
        chunking_enabled = cfg.get("chunking_enabled", True)
        chunking_threshold = max(
            30.0, float(cfg.get("chunking_threshold_seconds", 60.0))
        )
        use_chunking = chunking_enabled and duration >= chunking_threshold

        # Transcribe
        if use_chunking:
            debug(
                f"Using chunked transcription (duration {duration:.1f}s >= "
                f"threshold {chunking_threshold:.1f}s)"
            )
            transcript = transcribe_audio_chunked(processed, language)
            if transcript is None:
                hide_live_overlay()
                return None
        else:
            # Single-chunk transcription
            debug(f"Using single-chunk transcription (duration {duration:.1f}s)")

            transcript = transcriber.transcribe(processed, language)

            if transcript is None:
                hide_live_overlay()
                return None

            debug(f"Received transcript length: {len(transcript)}")

    except Exception as exc:
        debug(f"Transcription failed: {exc}")
        hide_live_overlay()
        return None

    if not transcript:
        hide_live_overlay()
        return None

    # Apply post-processing
    transcript = postprocess_transcript(transcript, language=language)

    # Update overlay with final transcript
    update_live_overlay(transcript, "Complete!")

    debug(f"Transcription complete: {len(transcript)} chars")
    return transcript
