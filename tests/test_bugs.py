"""Regression tests for historically reported critical bugs."""

import json

import pytest

from whisprbar import config, transcription


def _apply_config(overrides: dict) -> None:
    """Apply config overrides in-place to preserve imported cfg references."""
    config.cfg.clear()
    config.cfg.update(config.DEFAULT_CFG.copy())
    config.cfg.update(overrides)


@pytest.mark.unit
def test_bug1_config_migration(monkeypatch, tmp_path):
    """Legacy single hotkey should migrate into hotkeys.toggle_recording."""
    config_path = tmp_path / "whisprbar.json"
    data_dir = tmp_path / "whisprbar_data"
    hist_file = data_dir / "history.jsonl"

    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "HIST_FILE", hist_file)

    old_config = {
        "language": "de",
        "hotkey": "F8",  # legacy field
        "transcription_backend": "openai",
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(old_config, handle)

    config.reset_config()
    loaded = config.load_config()

    assert loaded["hotkeys"]["toggle_recording"] == "F8"
    assert loaded["hotkey"] == "F8"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("backend", "expected_cls"),
    [
        ("openai", transcription.OpenAITranscriber),
        ("faster_whisper", transcription.FasterWhisperTranscriber),
        ("streaming", transcription.StreamingTranscriber),
        ("invalid_backend", transcription.OpenAITranscriber),
    ],
)
def test_bug2_backend_selection(backend, expected_cls):
    """Configured backend should map to the expected transcriber class."""
    _apply_config({"transcription_backend": backend})
    transcription._transcriber = None

    transcriber = transcription.get_transcriber()

    assert isinstance(transcriber, expected_cls)


@pytest.mark.unit
def test_bug3_postprocessing_flag():
    """When postprocessing is disabled, transcript text must remain unchanged."""
    test_text = "hello world .  this is a test  sentence. another one here  ."
    _apply_config(
        {
            "postprocess_enabled": False,
            "postprocess_fix_spacing": True,
            "postprocess_fix_capitalization": True,
        }
    )

    result = transcription.postprocess_transcript(test_text, "en")

    assert result == test_text
