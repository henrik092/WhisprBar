"""Unit tests for hotkey registration flow in whisprbar.main."""

from unittest.mock import MagicMock

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


@pytest.mark.unit
def test_main_releases_resources_when_tray_startup_fails(monkeypatch):
    """Tray startup failures should stop hotkeys and release the singleton lock."""
    manager = DummyHotkeyManager()
    manager.set_special_handlers = lambda **_kwargs: None

    monkeypatch.setattr(main, "ensure_stdin_open", lambda: None)
    monkeypatch.setattr(main, "acquire_singleton_lock", lambda: True)
    release_singleton_lock = MagicMock()
    monkeypatch.setattr(main, "release_singleton_lock", release_singleton_lock)
    shutdown_tray = MagicMock()
    monkeypatch.setattr(main, "shutdown_tray", shutdown_tray)
    monkeypatch.setattr(main, "load_config", lambda: config.cfg)
    monkeypatch.setattr(main, "detect_session_type", lambda: "x11")
    monkeypatch.setattr(main, "select_tray_backend", lambda: "gtk")
    monkeypatch.setattr(main, "check_for_updates_async", lambda: None)
    monkeypatch.setattr(main, "maybe_show_first_run_diagnostics", lambda _cfg: None)
    monkeypatch.setattr(main, "prepare_openai_client", lambda: True)
    monkeypatch.setattr(main, "get_hotkey_manager", lambda: manager)
    monkeypatch.setattr(main, "register_configured_hotkeys", lambda _manager, restart_listener=False: None)
    monkeypatch.setattr(main, "update_device_index", lambda: None)
    monkeypatch.setattr(main, "install_signal_handlers", lambda: None)
    monkeypatch.setattr(main, "initialize_icons", lambda: None)
    monkeypatch.setattr(main, "start_pystray_tray", lambda _callbacks, _state: (_ for _ in ()).throw(RuntimeError("tray boom")))
    monkeypatch.setattr(main, "start_appindicator_tray", lambda _callbacks, _state: None)
    monkeypatch.setattr(main, "notify", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "tray_backend_label", lambda: "PyStray GTK")
    monkeypatch.setattr(main, "is_wayland_session", lambda: False)
    monkeypatch.setitem(config.cfg, "transcription_backend", "deepgram")

    from whisprbar import audio
    monkeypatch.setattr(audio, "set_recording_callbacks", lambda *_args, **_kwargs: None)

    try:
        import gi.repository  # type: ignore
    except Exception:
        pass
    else:
        monkeypatch.setattr("gi.repository.GLib.timeout_add", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="tray boom"):
        main.main()

    assert manager.start_calls == 1
    assert manager.stop_calls == 1
    shutdown_tray.assert_called_once()
    release_singleton_lock.assert_called_once()


@pytest.mark.unit
def test_register_configured_hotkeys_show_history_uses_real_callback(mock_config, monkeypatch):
    """show_history hotkey should call the history window callback, not a stub."""
    mock_config["hotkeys"] = {
        "toggle_recording": None,
        "start_recording": None,
        "stop_recording": None,
        "open_settings": None,
        "show_history": "F11",
    }
    mock_config["hotkey"] = "F9"
    config.cfg.clear()
    config.cfg.update(mock_config)

    open_history = MagicMock()
    monkeypatch.setattr(main, "open_history_callback", open_history)

    manager = DummyHotkeyManager()
    main.register_configured_hotkeys(manager, restart_listener=False)

    manager.registered["show_history"]["callback"]()

    open_history.assert_called_once_with()
