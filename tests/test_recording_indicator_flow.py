"""Tests for Flow Mode recording indicator helpers."""

import pytest

from whisprbar.ui import recording_indicator as indicator


@pytest.mark.unit
def test_flow_indicator_enabled_from_config():
    assert indicator._is_flow_indicator_enabled({"flow_mode_enabled": True}) is True
    assert indicator._is_flow_indicator_enabled({"flow_mode_enabled": False}) is False
    assert indicator._is_flow_indicator_enabled({}) is False


@pytest.mark.unit
def test_flow_phase_labels_include_rewriting():
    cfg = {"language": "en"}

    assert indicator._flow_phase_label(indicator.PHASE_RECORDING, cfg) == "Listening"
    assert indicator._flow_phase_label(indicator.PHASE_PROCESSING, cfg) == "Processing"
    assert indicator._flow_phase_label(indicator.PHASE_TRANSCRIBING, cfg) == "Transcribing"
    assert indicator._flow_phase_label(indicator.PHASE_REWRITING, cfg) == "Rewriting"
    assert indicator._flow_phase_label(indicator.PHASE_PASTING, cfg) == "Pasting"
    assert indicator._flow_phase_label(indicator.PHASE_COMPLETE, cfg) == "Done"
    assert indicator._flow_phase_label("unknown", cfg) == "Working"


@pytest.mark.unit
def test_flow_hotkey_label_uses_toggle_binding():
    cfg = {"hotkeys": {"toggle_recording": "CTRL_R"}, "hotkey": "F9"}

    assert indicator._flow_hotkey_label(cfg) == "Right Ctrl"


@pytest.mark.unit
def test_flow_hotkey_label_falls_back_to_legacy_hotkey():
    assert indicator._flow_hotkey_label({"hotkey": "F9"}) == "F9"


@pytest.mark.unit
def test_voice_activity_intensity_exaggerates_speech_levels():
    assert indicator._voice_activity_intensity(0.0) == 0.0
    assert indicator._voice_activity_intensity(0.08) < 0.25
    assert indicator._voice_activity_intensity(0.35) >= 0.45
    assert indicator._voice_activity_intensity(1.0) == 1.0


@pytest.mark.unit
def test_listening_capsule_metrics_make_speech_border_clearer():
    quiet = indicator._listening_capsule_metrics(0.0, height=30)
    speaking = indicator._listening_capsule_metrics(0.75, height=30)

    assert quiet["border_alpha"] < 0.25
    assert speaking["border_alpha"] >= 0.45
    assert speaking["border_width"] > quiet["border_width"]
    assert speaking["label_alpha"] >= quiet["label_alpha"]


@pytest.mark.unit
def test_flow_recording_uses_warm_listening_accent():
    recording = indicator.RecordingIndicator({"flow_mode_enabled": True})
    recording._phase = indicator.PHASE_RECORDING
    listening_color = recording._flow_accent_color()

    transcribing = indicator.RecordingIndicator({"flow_mode_enabled": True})
    transcribing._phase = indicator.PHASE_TRANSCRIBING
    transcribing_color = transcribing._flow_accent_color()

    assert listening_color[0] > listening_color[2]
    assert listening_color[0] > transcribing_color[0]
    assert transcribing_color[2] > transcribing_color[0]


@pytest.mark.unit
def test_flow_wave_metrics_make_speech_wave_more_present():
    quiet = indicator._flow_wave_metrics(0.0, height=42)
    speaking = indicator._flow_wave_metrics(0.75, height=42)

    assert speaking["line_width"] >= quiet["line_width"] + 2.0
    assert speaking["amplitude"] >= quiet["amplitude"] * 1.45
    assert speaking["glow_width"] > speaking["line_width"]
    assert speaking["glow_alpha"] >= 0.30
