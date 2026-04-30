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

    def set_status(self, status):
        self.statuses.append(status)


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
    assert german["settings"] == "Einstellungen..."
    assert german["quit"] == "Beenden"
    assert english["recent"] == "Recent"
    assert english["settings"] == "Settings..."
    assert english["quit"] == "Quit"


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
