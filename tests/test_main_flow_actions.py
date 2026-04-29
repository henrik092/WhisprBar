"""Tests for Flow-specific main actions."""

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
def test_paste_last_transcript_uses_last_successful_text(monkeypatch):
    from whisprbar import main

    main.state.last_transcript = "Last text"
    mock_paste = MagicMock()
    monkeypatch.setattr(main, "auto_paste", mock_paste)

    main.paste_last_transcript_callback()

    mock_paste.assert_called_once_with("Last text")


@pytest.mark.unit
def test_copy_last_transcript_uses_last_successful_text(monkeypatch):
    from whisprbar import main

    main.state.last_transcript = "Last text"
    mock_copy = MagicMock(return_value=True)
    monkeypatch.setattr(main, "copy_to_clipboard", mock_copy)

    main.copy_last_transcript_callback()

    mock_copy.assert_called_once_with("Last text")


@pytest.mark.unit
def test_hands_free_recording_toggles_recording(monkeypatch):
    from whisprbar import main

    start = MagicMock()
    stop = MagicMock()
    monkeypatch.setattr(main, "start_recording", start)
    monkeypatch.setattr(main, "stop_recording", stop)

    main.state.recording = False
    main.hands_free_recording_callback()
    start.assert_called_once()

    main.state.recording = True
    main.hands_free_recording_callback()
    stop.assert_called_once()
