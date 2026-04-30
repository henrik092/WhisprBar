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
