"""Thread-safe event bus for WhisprBar.

Provides a simple pub/sub mechanism to decouple modules. Handlers are
called synchronously in the emitting thread by default, or can be
dispatched to the GTK main thread via emit_on_main_thread().
"""

import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List


class EventBus:
    """Simple, thread-safe publish/subscribe event bus.

    Usage:
        bus = EventBus()
        bus.on("recording.started", my_handler)
        bus.emit("recording.started")
        bus.emit("transcription.complete", text="Hello world")
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def on(self, event: str, handler: Callable) -> None:
        """Register a handler for an event.

        Args:
            event: Event name (e.g., "recording.started").
            handler: Callable to invoke when the event is emitted.
        """
        with self._lock:
            if handler not in self._handlers[event]:
                self._handlers[event].append(handler)

    def off(self, event: str, handler: Callable) -> None:
        """Unregister a handler for an event.

        Args:
            event: Event name.
            handler: Previously registered handler to remove.
        """
        with self._lock:
            try:
                self._handlers[event].remove(handler)
            except ValueError:
                pass

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit an event, calling all registered handlers synchronously.

        Handlers are called in registration order. Exceptions in handlers
        are caught and printed to stderr to prevent one broken handler
        from blocking others.

        Args:
            event: Event name to emit.
            *args: Positional arguments passed to handlers.
            **kwargs: Keyword arguments passed to handlers.
        """
        with self._lock:
            handlers = list(self._handlers.get(event, []))

        for handler in handlers:
            try:
                handler(*args, **kwargs)
            except Exception as exc:
                import sys
                print(
                    f"[WARN] EventBus handler error for '{event}': {exc}",
                    file=sys.stderr,
                )

    def emit_on_main_thread(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit an event on the GTK main thread via GLib.idle_add().

        Use this when emitting from a background thread and handlers
        need to update GTK widgets.

        Args:
            event: Event name to emit.
            *args: Positional arguments passed to handlers.
            **kwargs: Keyword arguments passed to handlers.
        """
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda: self.emit(event, *args, **kwargs) or False)
        except ImportError:
            # Fallback: emit directly if GLib not available (e.g., in tests)
            self.emit(event, *args, **kwargs)

    def clear(self, event: str = None) -> None:
        """Remove all handlers, or handlers for a specific event.

        Args:
            event: If provided, only clear handlers for this event.
                   If None, clear all handlers.
        """
        with self._lock:
            if event is not None:
                self._handlers.pop(event, None)
            else:
                self._handlers.clear()

    def has_handlers(self, event: str) -> bool:
        """Check if any handlers are registered for an event."""
        with self._lock:
            return bool(self._handlers.get(event))


# Well-known event names (documentation, not enforced)
# These constants help avoid typos in event names.

RECORDING_STARTED = "recording.started"
RECORDING_STOPPED = "recording.stopped"
RECORDING_CANCELLED = "recording.cancelled"
PROCESSING_STARTED = "processing.started"
TRANSCRIPTION_STARTED = "transcription.started"
TRANSCRIPTION_COMPLETE = "transcription.complete"
TRANSCRIPTION_ERROR = "transcription.error"
CONFIG_CHANGED = "config.changed"
STATE_CHANGED = "state.changed"
OVERLAY_SHOW = "overlay.show"
OVERLAY_UPDATE = "overlay.update"
OVERLAY_HIDE = "overlay.hide"
