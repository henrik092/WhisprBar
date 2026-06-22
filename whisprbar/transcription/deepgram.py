"""Deepgram Nova-3 transcription backend for WhisprBar."""

import asyncio
import contextlib
import json
import os
import queue
import threading
import weakref
import wave
from typing import List, Optional

import numpy as np

from .base import StreamingTranscriptionSession, Transcriber
from whisprbar.config import load_env_file_values
from whisprbar.utils import debug, error
from whisprbar.audio import SAMPLE_RATE, CHANNELS


class DeepgramHTTPError(RuntimeError):
    """Non-retryable HTTP response from Deepgram."""


_QUEUE_SENTINEL = object()


def _audio_chunk_to_pcm16_bytes(audio: np.ndarray) -> bytes:
    pcm = np.asarray(audio, dtype=np.float32).reshape(-1)
    if pcm.size == 0:
        return b""
    pcm16 = (np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16)
    return pcm16.tobytes()


class DeepgramRealtimeSession(StreamingTranscriptionSession):
    """Deepgram live WebSocket session fed from the audio callback."""

    def __init__(self, api_key: str, url: str):
        self.api_key = api_key
        self.url = url
        self._audio_queue: queue.Queue = queue.Queue(maxsize=512)
        self._closed = threading.Event()
        self._cancelled = threading.Event()
        self._result_parts: List[str] = []
        self._error: Optional[BaseException] = None
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()

    def push_audio(self, audio: np.ndarray) -> None:
        if self._closed.is_set():
            return

        chunk = np.asarray(audio, dtype=np.float32).reshape(-1).copy()
        if chunk.size == 0:
            return

        try:
            self._audio_queue.put_nowait(chunk)
        except queue.Full:
            debug("Deepgram realtime queue full; dropping live chunk and relying on batch fallback")

    def finish(self) -> Optional[str]:
        self._close_queue()
        self._thread.join(timeout=15.0)
        if self._thread.is_alive():
            debug("Deepgram realtime finish timed out")
            return None
        if self._error is not None:
            debug(f"Deepgram realtime session failed: {self._error}")
            return None
        transcript = " ".join(self._result_parts).strip()
        return transcript or None

    def cancel(self) -> None:
        self._cancelled.set()
        self._close_queue()
        self._thread.join(timeout=2.0)

    def _close_queue(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._audio_queue.put(_QUEUE_SENTINEL, timeout=1.0)
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self._audio_queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self._audio_queue.put_nowait(_QUEUE_SENTINEL)

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run_async())
        except BaseException as exc:
            self._error = exc

    async def _run_async(self) -> None:
        try:
            import websockets
        except Exception as exc:
            self._error = exc
            return

        headers = {"Authorization": f"Token {self.api_key}"}
        connect_kwargs = {
            "additional_headers": headers,
            "open_timeout": 10,
            "ping_interval": 20,
        }

        try:
            connection_cm = websockets.connect(self.url, **connect_kwargs)
        except TypeError:
            connect_kwargs.pop("additional_headers")
            connect_kwargs["extra_headers"] = headers
            connection_cm = websockets.connect(self.url, **connect_kwargs)

        async with connection_cm as websocket:
            finalize_received = asyncio.Event()
            receiver_task = asyncio.create_task(
                self._receive_results(websocket, finalize_received)
            )
            keepalive_task = asyncio.create_task(self._send_keepalives(websocket))

            try:
                while True:
                    item = await asyncio.to_thread(self._audio_queue.get)
                    if item is _QUEUE_SENTINEL:
                        break
                    if self._cancelled.is_set():
                        return
                    payload = _audio_chunk_to_pcm16_bytes(item)
                    if payload:
                        await websocket.send(payload)

                if self._cancelled.is_set():
                    return

                await websocket.send(json.dumps({"type": "Finalize"}))
                try:
                    await asyncio.wait_for(finalize_received.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    debug("Deepgram realtime finalize wait timed out")
                await websocket.send(json.dumps({"type": "CloseStream"}))
            finally:
                keepalive_task.cancel()
                receiver_task.cancel()
                await asyncio.gather(
                    keepalive_task,
                    receiver_task,
                    return_exceptions=True,
                )

    async def _send_keepalives(self, websocket) -> None:
        while not self._closed.is_set() and not self._cancelled.is_set():
            await asyncio.sleep(3.0)
            if self._closed.is_set() or self._cancelled.is_set():
                return
            await websocket.send(json.dumps({"type": "KeepAlive"}))

    async def _receive_results(self, websocket, finalize_received: asyncio.Event) -> None:
        try:
            async for message in websocket:
                self._handle_message(message, finalize_received)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._cancelled.is_set():
                self._error = exc

    def _handle_message(self, message, finalize_received: asyncio.Event) -> None:
        if not isinstance(message, str):
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        if data.get("from_finalize") or data.get("type") == "Metadata":
            finalize_received.set()

        if data.get("type") != "Results":
            return

        try:
            transcript = data["channel"]["alternatives"][0].get("transcript", "")
        except (KeyError, IndexError, AttributeError):
            return

        if transcript and data.get("is_final", False):
            self._result_parts.append(transcript.strip())


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

        Uses Deepgram's multilingual mode for the app's normal simple language
        hints so German dictation can still contain English words or phrases.
        Explicit locale tags are preserved for callers that intentionally need
        a narrow Deepgram language target.
        """
        language_code = (language or "").strip()
        normalized_language = language_code.lower()
        if (
            not normalized_language
            or normalized_language in {"auto", "multi", "de", "en"}
        ):
            language_param = "multi"
        else:
            language_param = language_code

        return (
            "/v1/listen?model=nova-3"
            f"&language={language_param}"
            "&smart_format=true"
            "&punctuate=true"
        )

    def _build_streaming_url(self, language: str) -> str:
        path = self._build_request_path(language)
        return (
            f"wss://api.deepgram.com{path}"
            f"&encoding=linear16"
            f"&sample_rate={SAMPLE_RATE}"
            f"&channels={CHANNELS}"
            "&interim_results=true"
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

    def supports_streaming(self) -> bool:
        """Deepgram supports live WebSocket streaming when websockets is installed."""
        return True

    def start_streaming(
        self,
        language: str = "de",
    ) -> Optional[StreamingTranscriptionSession]:
        """Start a live Deepgram WebSocket session."""
        if not self.ensure_client():
            return None

        try:
            import websockets  # noqa: F401
        except Exception as exc:
            debug(f"Deepgram realtime unavailable: {exc}")
            return None

        try:
            return DeepgramRealtimeSession(
                self.api_key,
                self._build_streaming_url(language),
            )
        except Exception as exc:
            debug(f"Failed to start Deepgram realtime session: {exc}")
            return None

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
