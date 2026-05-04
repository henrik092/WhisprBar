"""Unit tests for tray backend selection and shutdown behavior."""

from types import SimpleNamespace

import pytest

from whisprbar import tray


class DummyPystrayIcon:
    """Simple icon stub with visibility and stop tracking."""

    def __init__(self):
        self.visible = True
        self.stopped = False

    def stop(self):
        self.stopped = True


class DummyLoop:
    """Minimal GLib loop stub."""

    def __init__(self, running=True):
        self.running = running
        self.quit_called = False

    def is_running(self):
        return self.running

    def quit(self):
        self.quit_called = True
        self.running = False


class DummyIndicator:
    """AppIndicator stub that records status changes."""

    def __init__(self):
        self.statuses = []
        self.labels = []
        self.icon_tooltips = []

    def set_status(self, status):
        self.statuses.append(status)

    def set_icon_full(self, icon_path, tooltip):
        self.icon_tooltips.append((icon_path, tooltip))

    def set_label(self, label, guide):
        self.labels.append((label, guide))


class DummyMenuItem:
    """PyStray menu item stub that records labels and handlers."""

    def __init__(self, text, action=None, **kwargs):
        self.text = text
        self.action = action
        self.kwargs = kwargs


class DummyMenu:
    """PyStray menu stub with separator support."""

    SEPARATOR = object()

    def __init__(self, *items):
        self.items = list(items)


class DummyGtkMenu:
    """GTK menu stub that records appended children."""

    def __init__(self):
        self.items = []
        self.show_all_called = False

    def append(self, item):
        self.items.append(item)

    def show_all(self):
        self.show_all_called = True


class DummyGtkMenuItem:
    """GTK menu item stub that records labels and callbacks."""

    def __init__(self, label=None):
        self.label = label
        self.handlers = {}
        self.sensitive = True
        self.submenu = None

    def connect(self, event, handler):
        self.handlers[event] = handler

    def set_sensitive(self, value):
        self.sensitive = value

    def set_submenu(self, menu):
        self.submenu = menu


class DummyGtkCheckMenuItem(DummyGtkMenuItem):
    """GTK check menu item stub."""

    def __init__(self, label=None):
        super().__init__(label=label)
        self.active = False

    def set_active(self, value):
        self.active = value


class ImmediateGLib:
    """GLib stub that executes idle callbacks synchronously."""

    @staticmethod
    def idle_add(callback):
        callback()


@pytest.mark.unit
def test_select_tray_backend_returns_auto_without_pystray(monkeypatch):
    """No backend should be selected if neither AppIndicator nor PyStray exists."""
    monkeypatch.setattr(tray, "APPINDICATOR_AVAILABLE", False)
    monkeypatch.setattr(tray, "pystray", None)
    monkeypatch.delenv("PYSTRAY_BACKEND", raising=False)

    backend = tray.select_tray_backend()

    assert backend == "auto"
    assert "PYSTRAY_BACKEND" not in tray.os.environ


@pytest.mark.unit
def test_get_tray_labels_follow_config_language():
    german = tray.get_tray_labels({"language": "de"})
    english = tray.get_tray_labels({"language": "en"})

    assert german["recent"] == "Verlauf"
    assert german["vad"] == "Spracherkennung (VAD)"
    assert german["settings"] == "Einstellungen..."
    assert german["quit"] == "Beenden"
    assert english["recent"] == "Recent"
    assert english["vad"] == "Voice detection (VAD)"
    assert english["settings"] == "Settings..."
    assert english["quit"] == "Quit"


@pytest.mark.unit
def test_pystray_menu_includes_status_toggle_and_diagnostics(monkeypatch):
    """PyStray menu should expose current status, primary toggle, and diagnostics."""
    dummy_pystray = SimpleNamespace(Menu=DummyMenu, MenuItem=DummyMenuItem)
    toggle_calls = []
    diagnostics_calls = []
    callbacks = {
        "toggle_recording": lambda: toggle_calls.append("toggle"),
        "open_diagnostics": lambda: diagnostics_calls.append("diagnostics"),
        "toggle_vad": lambda: None,
        "open_settings": lambda: None,
        "quit": lambda: None,
    }
    state = {"recording": False, "transcribing": False, "hotkey_key": "ctrl+space"}

    monkeypatch.setattr(tray, "pystray", dummy_pystray)
    monkeypatch.setattr(tray, "cfg", {"language": "en"})
    monkeypatch.setattr(tray, "read_history", lambda limit=10: [])
    monkeypatch.setattr(tray, "key_to_label", lambda key: "Ctrl+Space")

    menu = tray.build_pystray_menu(callbacks, state)
    labels = [item.text for item in menu.items if isinstance(item, DummyMenuItem)]

    assert labels[:2] == ["Ready", "Start recording (Ctrl+Space)"]
    assert "Diagnostics..." in labels
    assert "Recent" in labels
    assert "Voice detection (VAD)" in labels
    assert "Settings..." in labels
    assert "Quit" in labels

    menu.items[1].action(None, None)
    diagnostics_item = next(item for item in menu.items if getattr(item, "text", "") == "Diagnostics...")
    diagnostics_item.action(None, None)

    assert toggle_calls == ["toggle"]
    assert diagnostics_calls == ["diagnostics"]


@pytest.mark.unit
def test_pystray_menu_uses_stop_label_while_recording(monkeypatch):
    """The primary PyStray action should switch to Stop recording when active."""
    dummy_pystray = SimpleNamespace(Menu=DummyMenu, MenuItem=DummyMenuItem)
    callbacks = {
        "toggle_recording": lambda: None,
        "toggle_vad": lambda: None,
        "open_settings": lambda: None,
        "quit": lambda: None,
    }

    monkeypatch.setattr(tray, "pystray", dummy_pystray)
    monkeypatch.setattr(tray, "cfg", {"language": "en"})
    monkeypatch.setattr(tray, "read_history", lambda limit=10: [])

    menu = tray.build_pystray_menu(callbacks, {"recording": True})

    assert menu.items[0].text == "Recording"
    assert menu.items[1].text == "Stop recording"


@pytest.mark.unit
def test_appindicator_refresh_uses_compact_panel_label(monkeypatch, tmp_path):
    """AppIndicator should keep full status in tooltip and compact panel text."""
    indicator = DummyIndicator()
    appindicator = SimpleNamespace(IndicatorStatus=SimpleNamespace(ACTIVE="active"))

    monkeypatch.setattr(tray, "_indicator", indicator)
    monkeypatch.setattr(tray, "_icon_files", {"recording": tmp_path / "recording.png"})
    monkeypatch.setattr(tray, "cfg", {"language": "en"})
    monkeypatch.setattr(tray, "GLib", ImmediateGLib)
    monkeypatch.setattr(tray, "AppIndicator3", appindicator)

    tray.refresh_tray_indicator({"tray_backend": "appindicator", "recording": True})

    assert indicator.icon_tooltips == [(str(tmp_path / "recording.png"), "Recording")]
    assert indicator.labels == [("REC", "WhisprBar")]


@pytest.mark.unit
def test_appindicator_menu_includes_status_toggle_and_diagnostics(monkeypatch):
    """AppIndicator menu should expose the same UX-critical rows as PyStray."""
    gtk = SimpleNamespace(
        Menu=DummyGtkMenu,
        MenuItem=DummyGtkMenuItem,
        CheckMenuItem=DummyGtkCheckMenuItem,
        SeparatorMenuItem=lambda: "separator",
    )
    callbacks = {
        "toggle_recording": lambda: None,
        "open_diagnostics": lambda: None,
        "toggle_vad": lambda: None,
        "open_settings": lambda: None,
        "quit": lambda: None,
    }

    monkeypatch.setattr(tray, "APPINDICATOR_AVAILABLE", True)
    monkeypatch.setattr(tray, "Gtk", gtk)
    monkeypatch.setattr(tray, "cfg", {"language": "en"})
    monkeypatch.setattr(tray, "read_history", lambda limit=10: [])
    monkeypatch.setattr(tray, "key_to_label", lambda key: "Ctrl+Space")

    menu = tray.build_appindicator_menu(
        callbacks,
        {"recording": False, "transcribing": False, "hotkey_key": "ctrl+space"},
    )
    labels = [item.label for item in menu.items if isinstance(item, DummyGtkMenuItem)]

    assert labels[:2] == ["Ready", "Start recording (Ctrl+Space)"]
    assert "Diagnostics..." in labels
    assert "Recent" in labels
    assert "Voice detection (VAD)" in labels
    assert "Settings..." in labels
    assert "Quit" in labels


@pytest.mark.unit
def test_shutdown_tray_hides_and_stops_pystray_icon(monkeypatch):
    """PyStray shutdown should hide the icon and clear module state."""
    icon = DummyPystrayIcon()
    monkeypatch.setattr(tray, "_icon", icon)
    monkeypatch.setattr(tray, "_icon_ready", True)

    tray.shutdown_tray({"tray_backend": "gtk"})

    assert icon.visible is False
    assert icon.stopped is True
    assert tray._icon is None
    assert tray._icon_ready is False


@pytest.mark.unit
def test_shutdown_tray_clears_appindicator_state(monkeypatch):
    """AppIndicator shutdown should mark passive, quit the loop, and clear refs."""
    indicator = DummyIndicator()
    loop = DummyLoop(running=True)
    indicator_status = SimpleNamespace(PASSIVE="passive")
    appindicator = SimpleNamespace(IndicatorStatus=indicator_status)

    monkeypatch.setattr(tray, "_indicator", indicator)
    monkeypatch.setattr(tray, "_gtk_loop", loop)
    monkeypatch.setattr(tray, "AppIndicator3", appindicator)
    monkeypatch.setattr(tray, "_icon_ready", True)

    tray.shutdown_tray({"tray_backend": "appindicator"})

    assert indicator.statuses == ["passive"]
    assert loop.quit_called is True
    assert tray._indicator is None
    assert tray._gtk_loop is None
    assert tray._icon_ready is False
