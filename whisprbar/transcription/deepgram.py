"""Deepgram Nova-3 transcription backend for WhisprBar."""

import contextlib
import json
import os
import threading
import wave
from typing import Optional

import numpy as np

from .base import Transcriber
from whisprbar.config import load_env_file_values
from whisprbar.utils import debug
from whisprbar.audio import SAMPLE_RATE, CHANNELS


class DeepgramTranscriber(Transcriber):
    """Deepgram Nova-3 transcription backend.

    Transcribes audio using Deepgram's Nova-3 model via REST API.
    Requires DEEPGRAM_API_KEY.
    Sub-300ms latency - 6-10x faster than OpenAI Whisper.
    Uses persistent HTTP connection to avoid TCP+TLS handshake per request.
    """

    # Max idle time before proactively closing the connection (seconds).
    # Deepgram doesn't document a server-side idle timeout, but their
    # infrastructure (behind Cloudflare) likely closes idle connections
    # around ~100s. We use 120s as a safe upper bound — still allows
    # connection reuse for typical usage while avoiding long hangs on
    # stale connections. _send_request() has retry logic as a fallback.
    _CONN_MAX_IDLE = 120

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
        connections to avoid long hangs when the server has already
        dropped them. _send_request() has retry logic as a fallback.
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
