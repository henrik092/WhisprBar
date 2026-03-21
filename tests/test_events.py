"""Unit tests for whisprbar.events module."""

import threading

import pytest

from whisprbar.events import (
    EventBus,
    RECORDING_STARTED,
    RECORDING_STOPPED,
    TRANSCRIPTION_COMPLETE,
    STATE_CHANGED,
)


@pytest.mark.unit
class TestEventBus:
    """Tests for the EventBus class."""

    def test_on_and_emit(self):
        """Handler receives emitted event."""
        bus = EventBus()
        received = []
        bus.on("test", lambda: received.append(True))
        bus.emit("test")
        assert received == [True]

    def test_emit_with_args(self):
        """Handler receives positional and keyword arguments."""
        bus = EventBus()
        received = []
        bus.on("test", lambda x, y=None: received.append((x, y)))
        bus.emit("test", 42, y="hello")
        assert received == [(42, "hello")]

    def test_multiple_handlers(self):
        """Multiple handlers called in registration order."""
        bus = EventBus()
        order = []
        bus.on("test", lambda: order.append("first"))
        bus.on("test", lambda: order.append("second"))
        bus.on("test", lambda: order.append("third"))
        bus.emit("test")
        assert order == ["first", "second", "third"]

    def test_handler_deduplication(self):
        """Same handler registered twice is only called once."""
        bus = EventBus()
        count = []

        def handler():
            count.append(1)

        bus.on("test", handler)
        bus.on("test", handler)
        bus.emit("test")
        assert len(count) == 1

    def test_off_removes_handler(self):
        """off() removes a previously registered handler."""
        bus = EventBus()
        received = []

        def handler():
            received.append(True)

        bus.on("test", handler)
        bus.off("test", handler)
        bus.emit("test")
        assert received == []

    def test_off_nonexistent_handler(self):
        """off() silently ignores unregistered handler."""
        bus = EventBus()
        bus.off("test", lambda: None)  # Should not raise

    def test_emit_nonexistent_event(self):
        """Emitting an event with no handlers does nothing."""
        bus = EventBus()
        bus.emit("nonexistent")  # Should not raise

    def test_handler_exception_does_not_block_others(self, capsys):
        """Exception in one handler doesn't prevent others from running."""
        bus = EventBus()
        received = []

        bus.on("test", lambda: (_ for _ in ()).throw(ValueError("boom")))
        bus.on("test", lambda: received.append("ok"))

        # Replace the error-raising handler with one that actually raises
        bus.clear("test")

        def bad_handler():
            raise ValueError("boom")

        bus.on("test", bad_handler)
        bus.on("test", lambda: received.append("ok"))
        bus.emit("test")

        assert received == ["ok"]
        captured = capsys.readouterr()
        assert "boom" in captured.err

    def test_clear_specific_event(self):
        """clear(event) only removes handlers for that event."""
        bus = EventBus()
        a_called = []
        b_called = []
        bus.on("a", lambda: a_called.append(True))
        bus.on("b", lambda: b_called.append(True))
        bus.clear("a")
        bus.emit("a")
        bus.emit("b")
        assert a_called == []
        assert b_called == [True]

    def test_clear_all(self):
        """clear() with no args removes all handlers."""
        bus = EventBus()
        called = []
        bus.on("a", lambda: called.append("a"))
        bus.on("b", lambda: called.append("b"))
        bus.clear()
        bus.emit("a")
        bus.emit("b")
        assert called == []

    def test_has_handlers(self):
        """has_handlers returns True/False correctly."""
        bus = EventBus()
        assert bus.has_handlers("test") is False
        handler = lambda: None
        bus.on("test", handler)
        assert bus.has_handlers("test") is True
        bus.off("test", handler)
        assert bus.has_handlers("test") is False

    def test_thread_safety(self):
        """Concurrent emit/on calls don't crash."""
        bus = EventBus()
        results = []
        errors = []

        def emitter():
            for _ in range(100):
                try:
                    bus.emit("test")
                except Exception as e:
                    errors.append(e)

        def registrar():
            for i in range(100):
                try:
                    bus.on("test", lambda: results.append(1))
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=emitter), threading.Thread(target=registrar)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_emit_on_main_thread_fallback(self):
        """emit_on_main_thread falls back to sync emit when GLib unavailable."""
        bus = EventBus()
        received = []
        bus.on("test", lambda: received.append(True))
        # In test env without GTK, should fall back to direct emit
        bus.emit_on_main_thread("test")
        assert received == [True]

    def test_event_name_constants_are_strings(self):
        """Event name constants are non-empty strings."""
        assert isinstance(RECORDING_STARTED, str) and RECORDING_STARTED
        assert isinstance(RECORDING_STOPPED, str) and RECORDING_STOPPED
        assert isinstance(TRANSCRIPTION_COMPLETE, str) and TRANSCRIPTION_COMPLETE
        assert isinstance(STATE_CHANGED, str) and STATE_CHANGED
