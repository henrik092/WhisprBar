"""Unit tests for UI hotkey helper functions."""

import pytest

from whisprbar.ui_hotkeys import (
    build_hotkey_conflict_message,
    build_pending_hotkeys,
    get_hotkey_conflicts_for_actions,
)


@pytest.mark.unit
def test_build_pending_hotkeys_adds_missing_actions():
    """Editable actions should always exist in pending state."""
    pending = build_pending_hotkeys(
        {"toggle_recording": "F9"},
        {
            "toggle_recording": "Toggle",
            "start_recording": "Start",
        },
    )

    assert pending["toggle_recording"] == "F9"
    assert "start_recording" in pending
    assert pending["start_recording"] is None


@pytest.mark.unit
def test_get_hotkey_conflicts_for_actions_scopes_to_editable_actions():
    """Conflicts should only include keys from editable actions."""
    conflicts = get_hotkey_conflicts_for_actions(
        {
            "toggle_recording": "CTRL+F9",
            "start_recording": "ctrl+f9",
            "show_history": "CTRL+F9",  # ignored (not editable here)
        },
        {
            "toggle_recording": "Toggle",
            "start_recording": "Start",
        },
    )

    assert "CTRL+F9" in conflicts
    assert set(conflicts["CTRL+F9"]) == {"toggle_recording", "start_recording"}


@pytest.mark.unit
def test_build_hotkey_conflict_message_formats_readable_label():
    """Conflict message should include readable key label and action names."""
    message = build_hotkey_conflict_message(
        {"CTRL+F9": ["toggle_recording", "start_recording"]},
        {
            "toggle_recording": "Aufnahme umschalten",
            "start_recording": "Aufnahme starten",
        },
    )

    assert message is not None
    assert "Ctrl+F9" in message
    assert "Aufnahme umschalten" in message
    assert "Aufnahme starten" in message


@pytest.mark.unit
def test_build_hotkey_conflict_message_none_when_no_conflicts():
    """No conflicts should yield no user message."""
    message = build_hotkey_conflict_message(
        {},
        {"toggle_recording": "Aufnahme umschalten"},
    )
    assert message is None

