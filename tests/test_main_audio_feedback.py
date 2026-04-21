"""Unit tests for audio feedback flow in whisprbar.main."""

import threading
from unittest.mock import MagicMock

import numpy as np

import pytest

from whisprbar import config, main
from whisprbar.audio import SAMPLE_RATE


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


@pytest.mark.unit
def test_transcribe_processed_audio_returns_result_even_if_slow(monkeypatch):
    """Successful transcriptions must not be discarded by a fixed wall-clock cutoff."""
    monotonic_values = iter([10.0, 70.0])
    monkeypatch.setattr(main.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(main, "transcribe_audio", lambda audio, language: "hello world")

    text, elapsed_ms = main._transcribe_processed_audio(
        np.ones(SAMPLE_RATE, dtype=np.float32),
        "de",
    )

    assert text == "hello world"
    assert elapsed_ms == pytest.approx(60000.0)


@pytest.mark.unit
def test_on_recording_stop_starts_only_one_background_thread_for_transcription(
    monkeypatch, mock_config
):
    """The transcription flow should not spawn a second worker thread around transcribe_audio()."""
    created_targets = []

    class ImmediateThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self._target = target
            self.daemon = daemon
            created_targets.append(target)

        def start(self):
            if self._target is not None:
                self._target()

    mock_config.update(
        {
            "noise_reduction_enabled": False,
            "auto_paste_enabled": False,
            "min_audio_energy": 0.0,
            "live_overlay_display_duration": 0.5,
            "language": "de",
        }
    )
    config.cfg.clear()
    config.cfg.update(mock_config)

    monkeypatch.setattr(main.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(main, "refresh_tray_indicator", lambda _state: None)
    monkeypatch.setattr(main, "refresh_menu", lambda _callbacks, _state: None)
    monkeypatch.setattr(main, "get_callbacks", lambda: {})
    monkeypatch.setattr(main, "notify", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "copy_to_clipboard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "play_audio_feedback", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main,
        "get_recording_state",
        lambda: {"audio_data": np.ones(SAMPLE_RATE, dtype=np.float32)},
    )
    monkeypatch.setattr(main, "transcribe_audio", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "TRANSCRIPTION_SEMAPHORE", threading.Semaphore(2))

    from whisprbar import audio, ui
    from whisprbar.ui import recording_indicator

    monkeypatch.setattr(audio, "apply_noise_reduction", lambda audio_data: audio_data)
    monkeypatch.setattr(audio, "apply_vad", lambda audio_data: audio_data)
    monkeypatch.setattr(ui, "show_live_overlay", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui, "update_live_overlay", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui, "hide_live_overlay", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(recording_indicator, "show_recording_indicator", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(recording_indicator, "hide_recording_indicator", lambda *_args, **_kwargs: None)

    main.state.recording = True
    main.state.transcribing = False

    main.on_recording_stop()

    assert len(created_targets) == 1
