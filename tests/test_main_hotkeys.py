"""Unit tests for hotkey registration flow in whisprbar.main."""

import pytest

from whisprbar import config, main


class DummyHotkeyManager:
    """Minimal manager stub for register_configured_hotkeys tests."""

    def __init__(self):
        self.registered = {}
        self.unregistered = []
        self.stop_calls = 0
        self.start_calls = 0

    def register(self, action, hotkey, callback):
        self.registered[action] = {"hotkey": hotkey, "callback": callback}

    def unregister(self, action):
        self.unregistered.append(action)

    def stop(self):
        self.stop_calls += 1

    def start(self):
        self.start_calls += 1


@pytest.mark.unit
def test_register_configured_hotkeys_skips_duplicate_bindings(mock_config):
    """Duplicate action bindings should only register the first action."""
    mock_config["hotkeys"] = {
        "toggle_recording": "CTRL+F9",
        "start_recording": "ctrl+f9",  # duplicate of toggle_recording
        "stop_recording": "F10",
        "open_settings": None,
        "show_history": None,
    }
    mock_config["hotkey"] = "CTRL+F9"
    config.cfg.clear()
    config.cfg.update(mock_config)

    manager = DummyHotkeyManager()
    main.register_configured_hotkeys(manager, restart_listener=False)

    assert "toggle_recording" in manager.registered
    assert "stop_recording" in manager.registered
    assert "start_recording" not in manager.registered
    assert main.state["hotkey_key"] == "F9"


@pytest.mark.unit
def test_register_configured_hotkeys_restarts_listener_when_requested(mock_config):
    """restart_listener=True should stop and restart listener exactly once."""
    mock_config["hotkeys"] = {
        "toggle_recording": "F9",
        "start_recording": None,
        "stop_recording": None,
        "open_settings": None,
        "show_history": None,
    }
    mock_config["hotkey"] = "F9"
    config.cfg.clear()
    config.cfg.update(mock_config)

    manager = DummyHotkeyManager()
    main.register_configured_hotkeys(manager, restart_listener=True)

    assert manager.stop_calls == 1
    assert manager.start_calls == 1

