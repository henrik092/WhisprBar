"""Unit tests for runtime hotkey resolution helpers."""

import pytest

from whisprbar.hotkey_actions import HOTKEY_ACTION_ORDER
from whisprbar.hotkey_runtime import (
    build_runtime_hotkey_config,
    resolve_runtime_hotkeys,
)


@pytest.mark.unit
def test_build_runtime_hotkey_config_uses_legacy_toggle_fallback():
    """toggle_recording should fall back to legacy hotkey if unset."""
    runtime_cfg = build_runtime_hotkey_config(
        {
            "toggle_recording": None,
            "start_recording": "F10",
            "stop_recording": None,
            "open_settings": "F11",
            "show_history": None,
        },
        legacy_hotkey="CTRL+F9",
    )

    assert runtime_cfg["toggle_recording"] == "CTRL+F9"
    assert runtime_cfg["start_recording"] == "F10"


@pytest.mark.unit
def test_resolve_runtime_hotkeys_skips_duplicates_and_reports_errors():
    """Resolution should deduplicate bindings and keep parse errors."""
    resolved = resolve_runtime_hotkeys(
        {
            "toggle_recording": "CTRL+F9",
            "start_recording": "ctrl+f9",  # duplicate
            "stop_recording": "F10",
            "open_settings": "+++",  # parse -> defaults to F9, still valid
            "show_history": None,
        },
        HOTKEY_ACTION_ORDER,
    )

    registered_actions = [action for action, _, _ in resolved.registrations]
    assert "toggle_recording" in registered_actions
    assert "stop_recording" in registered_actions
    assert "start_recording" not in registered_actions
    assert any(item[0] == "start_recording" for item in resolved.skipped_duplicates)
    assert resolved.parse_errors == []


@pytest.mark.unit
def test_resolve_runtime_hotkeys_reports_conflicts():
    """Conflict map should expose duplicate configured shortcuts."""
    resolved = resolve_runtime_hotkeys(
        {
            "toggle_recording": "F9",
            "start_recording": "f9",
            "stop_recording": None,
            "open_settings": None,
            "show_history": None,
        },
        HOTKEY_ACTION_ORDER,
    )

    assert "F9" in resolved.conflicts
    assert set(resolved.conflicts["F9"]) == {"toggle_recording", "start_recording"}

