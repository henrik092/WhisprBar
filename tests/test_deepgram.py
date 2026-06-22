"""Unit tests for the Deepgram transcription backend."""

import gc
import asyncio
import json
import socket
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from whisprbar.transcription.deepgram import DeepgramRealtimeSession, DeepgramTranscriber


class FakeResponse:
    """Minimal HTTP response stub."""

    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body.encode("utf-8")


class FakeConnection:
    """Minimal HTTPSConnection stub with deterministic responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.request_count = 0
        self.closed = False

    def request(self, method, path, body=None, headers=None):
        self.request_count += 1
        self.last_request = {
            "method": method,
            "path": path,
            "body": body,
            "headers": headers,
        }

    def getresponse(self):
        if not self.responses:
            raise AssertionError("No fake responses left")
        status, body = self.responses.pop(0)
        return FakeResponse(status, body)

    def close(self):
        self.closed = True


class FailingRequestConnection(FakeConnection):
    """Connection test double that fails before an HTTP response exists."""

    def __init__(self, exc):
        super().__init__([])
        self.exc = exc

    def request(self, method, path, body=None, headers=None):
        self.request_count += 1
        raise self.exc


class RegistryConnection:
    """Weakref-able, hashable registry test double."""

    def close(self):
        return None


@pytest.mark.unit
def test_deepgram_http_error_is_not_retried(monkeypatch):
    """Deterministic HTTP failures should not trigger a second API request."""
    transcriber = DeepgramTranscriber()
    transcriber.api_key = "test-key"
    conn = FakeConnection([(429, '{"error":"rate limited"}')])

    monkeypatch.setattr(transcriber, "_get_connection", lambda: conn)

    with pytest.raises(Exception):
        transcriber._send_request("/v1/listen", b"wav-data", "audio/wav")

    assert conn.request_count == 1


@pytest.mark.unit
def test_deepgram_retries_transient_dns_resolution_failure(monkeypatch):
    """A short local DNS outage should not immediately discard the recording."""
    transcriber = DeepgramTranscriber()
    transcriber.api_key = "test-key"
    first_conn = FailingRequestConnection(socket.gaierror(-2, "temporary resolver failure"))
    second_conn = FakeConnection(
        [(200, '{"results":{"channels":[{"alternatives":[{"transcript":"ok"}]}]}}')]
    )
    connections = iter([first_conn, second_conn])

    monkeypatch.setattr(transcriber, "_get_connection", lambda: next(connections))
    monkeypatch.setattr(transcriber, "_close_thread_connection", lambda: None)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    result = transcriber._send_request("/v1/listen", b"wav-data", "audio/wav")

    assert '"transcript":"ok"' in result
    assert first_conn.request_count == 1
    assert second_conn.request_count == 1


@pytest.mark.unit
def test_deepgram_connection_registry_does_not_hold_strong_references():
    """Registry entries should disappear once the last strong reference is gone."""
    transcriber = DeepgramTranscriber()
    conn = RegistryConnection()

    transcriber._register_connection(conn)
    assert len(transcriber._conn_registry) == 1

    del conn
    gc.collect()

    assert len(transcriber._conn_registry) == 0


@pytest.mark.unit
def test_deepgram_build_request_path_uses_multilingual_for_default_hints():
    """Default app language hints should allow mixed German/English dictation."""
    transcriber = DeepgramTranscriber()

    assert "language=multi" in transcriber._build_request_path("de")
    assert "language=multi" in transcriber._build_request_path("en")
    assert "language=multi" in transcriber._build_request_path("auto")


@pytest.mark.unit
def test_deepgram_build_request_path_preserves_explicit_locale_tags():
    """Locale tags remain available for callers that need a narrow target."""
    transcriber = DeepgramTranscriber()

    assert "language=en-US" in transcriber._build_request_path("en-US")
    assert "language=de-CH" in transcriber._build_request_path("de-CH")


@pytest.mark.unit
def test_deepgram_build_streaming_url_uses_raw_pcm_parameters():
    """Deepgram live streams receive raw PCM16 with explicit audio parameters."""
    transcriber = DeepgramTranscriber()

    url = transcriber._build_streaming_url("de")

    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    assert "model=nova-3" in url
    assert "language=multi" in url
    assert "encoding=linear16" in url
    assert "sample_rate=16000" in url
    assert "channels=1" in url
    assert "interim_results=true" in url


@pytest.mark.unit
def test_deepgram_start_streaming_creates_live_session(monkeypatch):
    """Deepgram should use a live WebSocket session when available."""
    from whisprbar.transcription import deepgram as deepgram_module

    created = {}

    class FakeSession:
        def __init__(self, api_key, url):
            created["api_key"] = api_key
            created["url"] = url

    transcriber = DeepgramTranscriber()
    transcriber.api_key = "test-key"
    monkeypatch.setattr(transcriber, "ensure_client", lambda: True)
    monkeypatch.setattr(deepgram_module, "DeepgramRealtimeSession", FakeSession)

    session = transcriber.start_streaming("en")

    assert isinstance(session, FakeSession)
    assert created["api_key"] == "test-key"
    assert "language=multi" in created["url"]


@pytest.mark.unit
def test_deepgram_realtime_session_sends_binary_audio_and_finalizes(monkeypatch):
    """Live sessions should send PCM bytes and finalize before returning text."""
    sent_payloads = []
    captured = {}

    class FakeWebSocket:
        def __init__(self):
            self._messages = asyncio.Queue()

        async def send(self, payload):
            sent_payloads.append(payload)
            if isinstance(payload, str) and json.loads(payload).get("type") == "Finalize":
                await self._messages.put(
                    json.dumps(
                        {
                            "type": "Results",
                            "is_final": True,
                            "from_finalize": True,
                            "channel": {
                                "alternatives": [{"transcript": "hallo live"}]
                            },
                        }
                    )
                )

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self._messages.get()

    class FakeConnect:
        async def __aenter__(self):
            return FakeWebSocket()

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    def fake_connect(uri, **kwargs):
        captured["uri"] = uri
        captured["kwargs"] = kwargs
        return FakeConnect()

    monkeypatch.setitem(
        sys.modules,
        "websockets",
        SimpleNamespace(connect=fake_connect),
    )

    session = DeepgramRealtimeSession("test-key", "wss://api.deepgram.com/v1/listen")
    session.push_audio(np.array([0.1, 0.2], dtype=np.float32))

    assert session.finish() == "hallo live"
    assert captured["kwargs"]["additional_headers"]["Authorization"] == "Token test-key"
    assert any(isinstance(payload, bytes) for payload in sent_payloads)
    control_messages = [
        json.loads(payload)["type"]
        for payload in sent_payloads
        if isinstance(payload, str)
    ]
    assert "Finalize" in control_messages
    assert "CloseStream" in control_messages


@pytest.mark.unit
def test_deepgram_realtime_session_supports_legacy_websockets_headers(monkeypatch):
    """websockets 12.x expects extra_headers before entering the connection context."""
    attempts = []

    class FailingAdditionalHeadersConnect:
        async def __aenter__(self):
            raise TypeError(
                "BaseEventLoop.create_connection() got an unexpected keyword argument 'additional_headers'"
            )

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    class WorkingExtraHeadersConnect:
        async def __aenter__(self):
            raise RuntimeError("stop before network flow")

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    def fake_connect(uri, **kwargs):
        attempts.append((uri, kwargs))
        if "additional_headers" in kwargs:
            return FailingAdditionalHeadersConnect()
        if "extra_headers" in kwargs:
            return WorkingExtraHeadersConnect()
        raise AssertionError(f"missing websocket headers: {kwargs}")

    monkeypatch.setitem(
        sys.modules,
        "websockets",
        SimpleNamespace(connect=fake_connect),
    )

    session = DeepgramRealtimeSession("test-key", "wss://api.deepgram.com/v1/listen")

    assert session.finish() is None
    assert [sorted(kwargs) for _uri, kwargs in attempts] == [
        ["additional_headers", "open_timeout", "ping_interval"],
        ["extra_headers", "open_timeout", "ping_interval"],
    ]
    assert attempts[1][1]["extra_headers"]["Authorization"] == "Token test-key"
    assert attempts[1][1]["open_timeout"] == 10
    assert attempts[1][1]["ping_interval"] == 20


@pytest.mark.unit
def test_deepgram_realtime_session_reads_results_after_close_stream(monkeypatch):
    """CloseStream can flush final results even when Finalize emits no final event."""
    from whisprbar.transcription import deepgram as deepgram_module

    sent_payloads = []

    async def immediate_finalize_timeout(awaitable, timeout):
        if isinstance(awaitable, asyncio.Task):
            return await awaitable
        awaitable.close()
        raise asyncio.TimeoutError

    class FakeWebSocket:
        def __init__(self):
            self._messages = asyncio.Queue()

        async def send(self, payload):
            sent_payloads.append(payload)
            if isinstance(payload, str) and json.loads(payload).get("type") == "CloseStream":
                await self._messages.put(
                    json.dumps(
                        {
                            "type": "Results",
                            "is_final": True,
                            "channel": {
                                "alternatives": [{"transcript": "close stream final"}]
                            },
                        }
                    )
                )
                await self._messages.put(None)

        def __aiter__(self):
            return self

        async def __anext__(self):
            message = await self._messages.get()
            if message is None:
                raise StopAsyncIteration
            return message

    class FakeConnect:
        async def __aenter__(self):
            return FakeWebSocket()

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    monkeypatch.setattr(deepgram_module.asyncio, "wait_for", immediate_finalize_timeout)
    monkeypatch.setitem(
        sys.modules,
        "websockets",
        SimpleNamespace(connect=lambda _uri, **_kwargs: FakeConnect()),
    )

    session = DeepgramRealtimeSession("test-key", "wss://api.deepgram.com/v1/listen")

    assert session.finish() == "close stream final"
    assert [
        json.loads(payload)["type"]
        for payload in sent_payloads
        if isinstance(payload, str)
    ] == ["Finalize", "CloseStream"]


@pytest.mark.unit
def test_deepgram_realtime_session_discards_partial_text_after_queue_overflow(monkeypatch):
    """Dropped live audio chunks must force batch fallback instead of returning partial text."""
    monkeypatch.setattr(DeepgramRealtimeSession, "_run_thread", lambda self: None)
    session = DeepgramRealtimeSession("test-key", "wss://api.deepgram.com/v1/listen")
    session._result_parts.append("partial live text")

    while not session._audio_queue.full():
        session._audio_queue.put_nowait(np.ones(1, dtype=np.float32))

    session.push_audio(np.ones(1, dtype=np.float32))

    assert session.finish() is None


@pytest.mark.unit
def test_deepgram_realtime_session_discards_partial_text_when_close_drops_audio(monkeypatch):
    """A full queue at finish means the sentinel displaced live audio."""
    monkeypatch.setattr(DeepgramRealtimeSession, "_run_thread", lambda self: None)
    session = DeepgramRealtimeSession("test-key", "wss://api.deepgram.com/v1/listen")
    session._result_parts.append("partial live text")

    while not session._audio_queue.full():
        session._audio_queue.put_nowait(np.ones(1, dtype=np.float32))

    assert session.finish() is None


@pytest.mark.unit
def test_deepgram_realtime_session_cancels_worker_after_finish_timeout(monkeypatch):
    """Timed-out realtime workers should be cancelled before batch fallback."""
    monkeypatch.setattr(DeepgramRealtimeSession, "_run_thread", lambda self: None)
    session = DeepgramRealtimeSession("test-key", "wss://api.deepgram.com/v1/listen")
    joins = []
    cancelled = []

    class HungThread:
        def join(self, timeout=None):
            joins.append(timeout)

        def is_alive(self):
            return True

    session._thread = HungThread()
    monkeypatch.setattr(session, "cancel", lambda: cancelled.append(True))

    assert session.finish() is None
    assert joins == [15.0]
    assert cancelled == [True]


@pytest.mark.unit
def test_deepgram_unload_closes_registered_connections():
    """Unload should close currently tracked live connections."""
    transcriber = DeepgramTranscriber()
    transcriber.api_key = "test-key"
    conn = FakeConnection([(200, '{"results":{"channels":[{"alternatives":[{"transcript":"ok"}]}]}}')])

    transcriber._register_connection(conn)
    transcriber.unload()

    assert conn.closed is True
    assert transcriber.api_key is None
