"""Unit tests for audio feedback flow in whisprbar.main."""

from unittest.mock import MagicMock

import pytest

from whisprbar import main


@pytest.mark.unit
def test_on_recording_stop_plays_stop_feedback_without_audio(monkeypatch):
    """Stopping a recording should still play stop feedback before early return."""
    monkeypatch.setattr(main, "refresh_tray_indicator", lambda _state: None)
    monkeypatch.setattr(main, "refresh_menu", lambda _callbacks, _state: None)
    monkeypatch.setattr(main, "get_callbacks", lambda: {})
    monkeypatch.setattr(main, "get_recording_state", lambda: {"audio_data": None})

    play_audio_feedback = MagicMock()
    monkeypatch.setattr(main, "play_audio_feedback", play_audio_feedback)

    main.state.recording = True
    main.state.transcribing = False

    main.on_recording_stop()

    play_audio_feedback.assert_called_once_with("stop")
    assert main.state.recording is False
    assert main.state.transcribing is False
