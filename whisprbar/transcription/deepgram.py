"""Deepgram Nova-3 transcription backend for WhisprBar."""

import contextlib
import json
import os
import threading
import weakref
import wave
from typing import Optional

import numpy as np

from .base import Transcriber
from whisprbar.config import load_env_file_values
from whisprbar.utils import debug, error
from whisprbar.audio import SAMPLE_RATE, CHANNELS


class DeepgramHTTPError(RuntimeError):
    """Non-retryable HTTP response from Deepgram."""


class DeepgramTranscriber(Transcriber):
    """Deepgram Nova-3 transcription backend.

    Transcribes audio using Deepgram's Nova-3 model via REST API.
    Requires DEEPGRAM_API_KEY.
    Sub-300ms latency - 6-10x faster than OpenAI Whisper.
    Uses persistent HTTP connection(s) to avoid TCP+TLS handshake per request.

    NOTE:
    ThreadPool chunking can call this transcriber from multiple threads in
    parallel. `http.client.HTTPSConnection` is not thread-safe, so we keep
    one persistent connection per thread.
    """

    # Max idle time before proactively closing the connection (seconds).
    # Deepgram doesn't document a server-side idle timeout. Testing shows
    # connections go stale well before 120s, causing long hangs. 55s works
    # reliably in practice — connection reuse still helps for rapid-fire
    # recordings, and a fresh handshake (~200-500ms) is acceptable for
    # longer gaps. _send_request() has retry logic as a fallback.
    _CONN_MAX_IDLE = 55
    _DNS_RETRY_DELAYS = (0.25, 0.75)

    def __init__(self):
        """Initialize Deepgram transcriber."""
        self.api_key = None
        self.client_lock = threading.Lock()

        # One persistent connection per thread for thread-safe reuse.
        self._thread_local = threading.local()

        # Track live connections without keeping dead worker-thread connections alive.
        self._conn_registry = weakref.WeakSet()
        self._conn_registry_lock = threading.Lock()

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

    def _register_connection(self, conn) -> None:
        with self._conn_registry_lock:
            self._conn_registry.add(conn)

    def _unregister_connection(self, conn) -> None:
        with self._conn_registry_lock:
            self._conn_registry.discard(conn)

    def _close_thread_connection(self) -> None:
        conn = getattr(self._thread_local, "conn", None)
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
            self._unregister_connection(conn)
        self._thread_local.conn = None
        self._thread_local.conn_used_at = 0.0

    def _get_connection(self):
        """Get or create a persistent HTTPS connection for current thread.

        Reuses the calling thread's connection to avoid TCP+TLS handshake
        overhead (~200-500ms) on subsequent calls. Proactively closes idle
        connections to avoid long hangs when the server has already dropped
        them. _send_request() has retry logic as a fallback.
        """
        import http.client
        import time as _time

        conn = getattr(self._thread_local, "conn", None)
        conn_used_at = float(getattr(self._thread_local, "conn_used_at", 0.0) or 0.0)

        # Close idle connections proactively to avoid stale-connection hangs
        if conn is not None:
            idle = _time.monotonic() - conn_used_at
            if idle > self._CONN_MAX_IDLE:
                debug(
                    f"Deepgram: closing idle connection "
                    f"({idle:.0f}s > {self._CONN_MAX_IDLE}s)"
                )
                with contextlib.suppress(Exception):
                    conn.close()
                self._unregister_connection(conn)
                conn = None

        if conn is not None:
            return conn

        conn = http.client.HTTPSConnection("api.deepgram.com", timeout=30)
        self._thread_local.conn = conn
        self._thread_local.conn_used_at = _time.monotonic()
        self._register_connection(conn)
        debug("Deepgram: new thread-local HTTPS connection established")
        return conn

    def _send_request(self, url_path: str, payload: bytes, content_type: str) -> str:
        """Send request with automatic reconnection on stale connections."""
        import http.client
        import socket
        import time as _time

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type,
            "Connection": "keep-alive",
        }

        def _do_request(conn):
            t0 = _time.monotonic()
            conn.request("POST", url_path, body=payload, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8")
            elapsed_ms = (_time.monotonic() - t0) * 1000
            if response.status != 200:
                error(
                    f"Deepgram: HTTP {response.status} after "
                    f"{elapsed_ms:.0f}ms — {data[:300]}"
                )
                raise DeepgramHTTPError(f"HTTP {response.status}: {data[:200]}")
            debug(
                f"Deepgram: response {response.status} in {elapsed_ms:.0f}ms "
                f"({len(data)} bytes)"
            )
            self._thread_local.conn_used_at = _time.monotonic()
            return data

        def _do_request_with_dns_retry():
            conn = self._get_connection()
            for dns_attempt in range(len(self._DNS_RETRY_DELAYS) + 1):
                try:
                    return _do_request(conn)
                except socket.gaierror as exc:
                    if dns_attempt >= len(self._DNS_RETRY_DELAYS):
                        error(f"Deepgram: DNS resolution failed for api.deepgram.com ({exc})")
                        raise

                    delay = self._DNS_RETRY_DELAYS[dns_attempt]
                    debug(
                        f"Deepgram: DNS resolution failed for api.deepgram.com "
                        f"({exc}); retrying in {delay:.2f}s"
                    )
                    self._close_thread_connection()
                    _time.sleep(delay)
                    conn = self._get_connection()
            raise RuntimeError("unreachable")

        try:
            return _do_request_with_dns_retry()
        except DeepgramHTTPError:
            raise
        except socket.gaierror:
            raise
        except (http.client.HTTPException, OSError, ConnectionError) as exc:
            # Connection stale/lost or HTTP error, reconnect and retry once
            debug(
                f"Deepgram: request failed ({type(exc).__name__}: {exc}), reconnecting..."
            )
            self._close_thread_connection()
            return _do_request_with_dns_retry()

    def _build_request_path(self, language: str) -> str:
        """Build Deepgram API URL path with parameters.

        Uses requested language when provided (e.g. "de", "en") for better
        punctuation and formatting. Falls back to language=multi to support
        code-switching when language is missing/auto.
        """
        language_code = (language or "").strip().lower()
        if not language_code or language_code in {"auto", "multi"}:
            language_param = "multi"
        else:
            language_param = language_code

        return (
            "/v1/listen?model=nova-3"
            f"&language={language_param}"
            "&smart_format=true"
            "&punctuate=true"
        )

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
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm16.tobytes())

            wav_data = wav_buffer.getvalue()

            # Build Deepgram API URL path with parameters
            url_path = self._build_request_path(language)

            # Send request via persistent per-thread connection
            debug(f"Sending audio to Deepgram Nova-3 (language={language})...")
            response_data = self._send_request(
                url_path,
                payload=wav_data,
                content_type="audio/wav",
            )
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
            import socket

            if isinstance(exc, socket.gaierror):
                error(
                    "Deepgram: DNS error — cannot resolve api.deepgram.com "
                    f"({exc}). Check DNS/AdGuard/network."
                )
            elif isinstance(exc, DeepgramHTTPError):
                pass
            elif isinstance(exc, (ConnectionError, OSError)):
                error(f"Deepgram: network error — {type(exc).__name__}: {exc}")
            elif isinstance(exc, TimeoutError):
                error(f"Deepgram: request timed out ({exc})")
            else:
                error(f"Deepgram transcription failed: {type(exc).__name__}: {exc}")
            return None

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            "Deepgram Nova-3"
        """
        return "Deepgram Nova-3 (multilingual)"

    def unload(self) -> None:
        """Unload Deepgram client and close persistent connections."""
        with self.client_lock:
            # Close current thread's connection and clear thread-local state.
            self._close_thread_connection()

            # Close any remaining connections created by worker threads.
            with self._conn_registry_lock:
                all_conns = list(self._conn_registry)
                self._conn_registry.clear()

            for conn in all_conns:
                with contextlib.suppress(Exception):
                    conn.close()

            if self.api_key is not None:
                self.api_key = None
                debug("Deepgram client unloaded")
