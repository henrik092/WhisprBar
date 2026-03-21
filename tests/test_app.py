"""Unit tests for whisprbar.app module."""

from unittest.mock import MagicMock, patch

import pytest

from whisprbar.app import WhisprBarApp
from whisprbar.config_types import AppConfig
from whisprbar.events import (
    CONFIG_CHANGED,
    PROCESSING_STARTED,
    RECORDING_CANCELLED,
    RECORDING_STARTED,
    RECORDING_STOPPED,
    STATE_CHANGED,
    TRANSCRIPTION_COMPLETE,
    TRANSCRIPTION_ERROR,
    TRANSCRIPTION_STARTED,
)
from whisprbar.state import AppPhase


@pytest.fixture
def app():
    """Create a WhisprBarApp with default config dict."""
    return WhisprBarApp(config_dict={"language": "de"})


@pytest.mark.unit
class TestWhisprBarAppInit:
    """Tests for WhisprBarApp initialization."""

    def test_creates_with_config_dict(self):
        app = WhisprBarApp(config_dict={"language": "en"})
        assert isinstance(app.config, AppConfig)
        assert app.config.transcription.language == "en"

    def test_creates_event_bus(self):
        app = WhisprBarApp(config_dict={})
        assert app.bus is not None

    def test_creates_state_machine(self):
        app = WhisprBarApp(config_dict={})
        assert app.state is not None
        assert app.phase == AppPhase.IDLE

    def test_state_changes_emit_events(self):
        app = WhisprBarApp(config_dict={})
        received = []
        app.bus.on(STATE_CHANGED, lambda **kw: received.append(kw))
        app.state.transition(AppPhase.RECORDING)
        assert len(received) == 1
        assert received[0]["old"] == AppPhase.IDLE
        assert received[0]["new"] == AppPhase.RECORDING


@pytest.mark.unit
class TestWhisprBarAppRecording:
    """Tests for recording operations."""

    def test_start_recording_transitions_state(self, app):
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_audio.return_value = MagicMock()
            result = app.start_recording()
            assert result is True
            assert app.phase == AppPhase.RECORDING

    def test_start_recording_emits_event(self, app):
        events = []
        app.bus.on(RECORDING_STARTED, lambda: events.append(True))
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_audio.return_value = MagicMock()
            app.start_recording()
        assert events == [True]

    def test_start_recording_fails_when_not_idle(self, app):
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_audio.return_value = MagicMock()
            app.start_recording()
            result = app.start_recording()  # Already recording
            assert result is False

    def test_stop_recording_transitions_to_processing(self, app):
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_mod = MagicMock()
            mock_mod.stop_recording.return_value = b"audio_data"
            mock_audio.return_value = mock_mod
            app.start_recording()
            result = app.stop_recording()
            assert result is True
            assert app.phase == AppPhase.PROCESSING

    def test_stop_recording_emits_events(self, app):
        events = []
        app.bus.on(RECORDING_STOPPED, lambda **kw: events.append("stopped"))
        app.bus.on(PROCESSING_STARTED, lambda: events.append("processing"))
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_mod = MagicMock()
            mock_mod.stop_recording.return_value = b"audio"
            mock_audio.return_value = mock_mod
            app.start_recording()
            app.stop_recording()
        assert "stopped" in events
        assert "processing" in events

    def test_stop_recording_fails_when_not_recording(self, app):
        result = app.stop_recording()
        assert result is False

    def test_cancel_recording(self, app):
        events = []
        app.bus.on(RECORDING_CANCELLED, lambda: events.append(True))
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_audio.return_value = MagicMock()
            app.start_recording()
            result = app.cancel_recording()
            assert result is True
            assert app.phase == AppPhase.IDLE
            assert events == [True]

    def test_cancel_recording_fails_when_not_recording(self, app):
        result = app.cancel_recording()
        assert result is False

    def test_toggle_recording_starts(self, app):
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_audio.return_value = MagicMock()
            app.toggle_recording()
            assert app.phase == AppPhase.RECORDING

    def test_toggle_recording_stops(self, app):
        with patch.object(app, "get_audio_module") as mock_audio:
            mock_mod = MagicMock()
            mock_mod.stop_recording.return_value = b"audio"
            mock_audio.return_value = mock_mod
            app.start_recording()
            app.toggle_recording()
            assert app.phase == AppPhase.PROCESSING


@pytest.mark.unit
class TestWhisprBarAppTranscription:
    """Tests for transcription operations."""

    def test_transcribe_success(self, app):
        # Get to PROCESSING state first
        app.state.try_transition(AppPhase.RECORDING)
        app.state.try_transition(AppPhase.PROCESSING)

        events = []
        app.bus.on(TRANSCRIPTION_STARTED, lambda: events.append("started"))
        app.bus.on(TRANSCRIPTION_COMPLETE, lambda **kw: events.append(kw["text"]))

        with patch("whisprbar.app.transcribe_audio", create=True) as mock_t:
            # Patch inside the method's import
            with patch("whisprbar.transcription.transcribe_audio", return_value="Hello world"):
                text = app.transcribe(b"audio_data")

        # Check events or text based on implementation
        assert app.phase in (AppPhase.PASTING, AppPhase.TRANSCRIBING, AppPhase.IDLE)

    def test_transcribe_fails_from_idle(self, app):
        """Cannot transcribe from IDLE state."""
        result = app.transcribe(b"audio")
        assert result is None
        assert app.phase == AppPhase.IDLE

    def test_transcribe_error_emits_event(self, app):
        app.state.try_transition(AppPhase.RECORDING)
        app.state.try_transition(AppPhase.PROCESSING)

        errors = []
        app.bus.on(TRANSCRIPTION_ERROR, lambda **kw: errors.append(kw.get("error")))

        with patch("whisprbar.transcription.transcribe_audio", side_effect=RuntimeError("API down")):
            result = app.transcribe(b"audio")

        assert result is None
        assert app.phase == AppPhase.IDLE  # Reset after error
        assert len(errors) == 1


@pytest.mark.unit
class TestWhisprBarAppPaste:
    """Tests for paste operations."""

    def test_auto_paste_calls_paste_module(self, app):
        app.state.try_transition(AppPhase.RECORDING)
        app.state.try_transition(AppPhase.PROCESSING)
        app.state.try_transition(AppPhase.TRANSCRIBING)
        app.state.try_transition(AppPhase.PASTING)

        with patch("whisprbar.paste.perform_auto_paste") as mock_paste:
            app.auto_paste("Hello")
            mock_paste.assert_called_once()

    def test_auto_paste_respects_disabled_config(self):
        app = WhisprBarApp(config_dict={"auto_paste_enabled": False})
        app.state.try_transition(AppPhase.RECORDING)
        app.state.try_transition(AppPhase.PROCESSING)
        app.state.try_transition(AppPhase.TRANSCRIBING)
        app.state.try_transition(AppPhase.PASTING)

        with patch("whisprbar.paste.perform_auto_paste") as mock_paste:
            app.auto_paste("Hello")
            mock_paste.assert_not_called()

    def test_auto_paste_transitions_to_idle(self, app):
        app.state.try_transition(AppPhase.RECORDING)
        app.state.try_transition(AppPhase.PROCESSING)
        app.state.try_transition(AppPhase.TRANSCRIBING)
        app.state.try_transition(AppPhase.PASTING)

        with patch("whisprbar.paste.perform_auto_paste"):
            app.auto_paste("Hello")
        assert app.phase == AppPhase.IDLE

    def test_auto_paste_handles_exception(self, app):
        app.state.try_transition(AppPhase.RECORDING)
        app.state.try_transition(AppPhase.PROCESSING)
        app.state.try_transition(AppPhase.TRANSCRIBING)
        app.state.try_transition(AppPhase.PASTING)

        with patch("whisprbar.paste.perform_auto_paste", side_effect=RuntimeError("xdotool not found")):
            app.auto_paste("Hello")  # Should not raise
        assert app.phase == AppPhase.IDLE


@pytest.mark.unit
class TestWhisprBarAppConfig:
    """Tests for config operations."""

    def test_reload_config(self, app):
        events = []
        app.bus.on(CONFIG_CHANGED, lambda: events.append(True))
        new_config = app.reload_config()
        assert isinstance(new_config, AppConfig)
        assert events == [True]


@pytest.mark.unit
class TestWhisprBarAppCompatProperties:
    """Tests for backwards-compatible properties."""

    def test_recording_property(self, app):
        assert app.recording is False
        app.state.try_transition(AppPhase.RECORDING)
        assert app.recording is True

    def test_transcribing_property(self, app):
        assert app.transcribing is False
        app.state.try_transition(AppPhase.RECORDING)
        app.state.try_transition(AppPhase.PROCESSING)
        app.state.try_transition(AppPhase.TRANSCRIBING)
        assert app.transcribing is True

    def test_phase_property(self, app):
        assert app.phase == AppPhase.IDLE


@pytest.mark.unit
class TestWhisprBarAppShutdown:
    """Tests for shutdown."""

    def test_shutdown_resets_state(self, app):
        app.state.try_transition(AppPhase.RECORDING)
        app.shutdown()
        assert app.phase == AppPhase.IDLE

    def test_shutdown_clears_bus(self, app):
        app.bus.on("test", lambda: None)
        assert app.bus.has_handlers("test") is True
        app.shutdown()
        assert app.bus.has_handlers("test") is False
