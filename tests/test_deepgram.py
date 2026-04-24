"""Unit tests for the Deepgram transcription backend."""

import gc
import socket
import pytest

from whisprbar.transcription.deepgram import DeepgramTranscriber


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
def test_deepgram_build_request_path_uses_explicit_language():
    """Explicit language codes should be sent to Deepgram instead of forcing multi."""
    transcriber = DeepgramTranscriber()

    assert "language=de" in transcriber._build_request_path("de")
    assert "language=en" in transcriber._build_request_path("en")
    assert "language=multi" in transcriber._build_request_path("auto")


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
