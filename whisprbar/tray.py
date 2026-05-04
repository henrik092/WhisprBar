#!/usr/bin/env python3
"""
whisprbar/tray.py - System tray integration

Handles system tray icon and menu using multiple backends:
- AppIndicator3 (preferred on Ubuntu/GNOME)
- PyStray GTK (fallback with GTK support)
- PyStray Xorg (fallback on X11)
"""

import os
import shutil
import contextlib
import threading
from typing import Optional, Callable, Dict, Any
from pathlib import Path

try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import Gtk, GLib, AppIndicator3
    APPINDICATOR_AVAILABLE = True
    GI_AVAILABLE = True
except (ImportError, ValueError):
    Gtk = GLib = AppIndicator3 = None
    APPINDICATOR_AVAILABLE = False
    GI_AVAILABLE = False

try:
    import pystray
except Exception:
    pystray = None

from whisprbar.utils import (
    build_icon,
    ensure_directories,
    APP_NAME,
    debug,
    read_history,
    clear_history,
    format_history_entry
)
from whisprbar.config import cfg
from whisprbar.hotkeys import key_to_label
from whisprbar.i18n import t

# Module state
_icon: Optional[Any] = None  # pystray.Icon
_indicator: Optional[Any] = None  # AppIndicator3.Indicator
_gtk_loop: Optional[Any] = None  # GLib.MainLoop
_icon_ready: bool = False
_icon_ready_lock = threading.Lock()
_icon_images: Dict[str, Any] = {}  # PIL Images for PyStray
_icon_files: Dict[str, Path] = {}  # File paths for AppIndicator

# =============================================================================
# Backend Selection
# =============================================================================

def select_tray_backend() -> str:
    """
    Auto-detect and select the best available tray backend.

    Returns:
        Backend name: "appindicator", "gtk", "xorg", or "auto"
    """
    if APPINDICATOR_AVAILABLE:
        os.environ["PYSTRAY_BACKEND"] = "appindicator"
        return "appindicator"

    if pystray is None:
        debug("No PyStray backend available")
        os.environ.pop("PYSTRAY_BACKEND", None)
        return "auto"

    for backend in ("gtk", "xorg"):
        if backend == "gtk" and not GI_AVAILABLE:
            continue
        try:
            if backend == "gtk" and not shutil.which("xprop"):
                raise RuntimeError("GTK backend requires X11 helpers")
            os.environ["PYSTRAY_BACKEND"] = backend
            return backend
        except Exception as exc:
            debug(f"Tray backend {backend} unavailable: {exc}")

    os.environ.pop("PYSTRAY_BACKEND", None)
    return "auto"


def get_tray_backend() -> str:
    """Get the currently active tray backend from environment."""
    return os.environ.get("PYSTRAY_BACKEND", "auto")


# =============================================================================
# Icon Generation and Storage
# =============================================================================

def _store_icon(name: str, image) -> Path:
    """
    Save icon image to disk and return path.

    Args:
        name: Icon name (e.g., "ready", "recording", "transcribing")
        image: PIL Image object

    Returns:
        Path to saved icon file
    """
    ensure_directories()
    icons_dir = Path.home() / ".local" / "share" / "whisprbar" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    path = icons_dir / f"{name}.png"
    image.save(str(path), "PNG")
    return path


def initialize_icons() -> None:
    """Generate and store all icon states for both PyStray and AppIndicator."""
    global _icon_images, _icon_files

    ready_img = build_icon(state="ready")
    _icon_images["ready"] = ready_img
    _icon_files["ready"] = _store_icon("ready", ready_img)

    recording_img = build_icon(state="recording")
    _icon_images["recording"] = recording_img
    _icon_files["recording"] = _store_icon("recording", recording_img)

    transcribing_img = build_icon(state="transcribing")
    _icon_images["transcribing"] = transcribing_img
    _icon_files["transcribing"] = _store_icon("transcribing", transcribing_img)


# =============================================================================
# Menu Helpers
# =============================================================================

def menu_action(func: Callable, *args, **kwargs) -> Callable:
    """
    Create a menu action handler for PyStray.

    Args:
        func: Function to call when menu item is clicked
        *args, **kwargs: Arguments to pass to function

    Returns:
        Handler function for PyStray menu
    """
    def _handler(icon, item):
        func(*args, **kwargs)
    return _handler


def cfg_equals_checker(key: str, expected) -> Callable:
    """
    Create a checked state checker for PyStray menu items.

    Args:
        key: Config key to check
        expected: Expected value for checked state

    Returns:
        Checker function for PyStray menu
    """
    def _checked(item):
        return cfg.get(key) == expected
    return _checked


# =============================================================================
# Menu Builders
# =============================================================================

def get_tray_labels(config: Dict[str, Any] | None = None) -> Dict[str, str]:
    """Return localized tray labels for the configured UI language."""
    config = config or cfg
    return {
        "recent": t("tray.recent", config),
        "clear_history": t("tray.clear_history", config),
        "no_recent": t("tray.no_recent", config),
        "vad": t("tray.vad", config),
        "settings": t("tray.settings", config),
        "quit": t("tray.quit", config),
        "ready": t("tray.ready", config),
        "recording": t("tray.recording", config),
        "transcribing": t("tray.transcribing", config),
        "start_stop": t("tray.start_stop", config),
        "start_recording": t("tray.start_recording", config),
        "stop_recording": t("tray.stop_recording", config),
        "diagnostics": t("tray.diagnostics", config),
    }


def _tray_status_key(state: Dict[str, Any]) -> str:
    """Return the current tray state key."""
    if state.get("recording"):
        return "recording"
    if state.get("transcribing"):
        return "transcribing"
    return "ready"


def _recording_action_label(labels: Dict[str, str], state: Dict[str, Any]) -> str:
    """Return the primary tray recording action label."""
    label = labels["stop_recording"] if state.get("recording") else labels["start_recording"]
    hotkey_key = state.get("hotkey_key")
    if hotkey_key:
        label = f"{label} ({key_to_label(hotkey_key)})"
    return label


def _compact_appindicator_label(status_key: str) -> str:
    """Return compact panel text for AppIndicator."""
    if status_key == "recording":
        return "REC"
    if status_key == "transcribing":
        return "..."
    return ""


def build_pystray_menu(callbacks: Dict[str, Callable], state: Dict[str, Any]) -> "pystray.Menu":
    """
    Build simplified menu for PyStray backend.

    Args:
        callbacks: Dictionary of callback functions:
            - toggle_auto_paste
            - open_settings
            - copy_to_clipboard
            - clear_history
            - quit
        state: Application state dictionary

    Returns:
        PyStray Menu object
    """
    if pystray is None:
        raise RuntimeError("PyStray not available")

    labels = get_tray_labels(cfg)
    status_key = _tray_status_key(state)

    # Build recent transcriptions submenu
    history_entries = read_history(limit=10)
    recent_items = []

    if history_entries:
        for entry in history_entries:
            text = entry.get("text", "")
            display_text = format_history_entry(entry, max_length=50)
            recent_items.append(
                pystray.MenuItem(
                    display_text,
                    lambda _, t=text: callbacks["copy_to_clipboard"](t)
                )
            )
        recent_items.append(pystray.Menu.SEPARATOR)
        recent_items.append(
            pystray.MenuItem(
                labels["clear_history"],
                lambda *_: callbacks["clear_history"]()
            )
        )
    else:
        recent_items.append(
            pystray.MenuItem(labels["no_recent"], None, enabled=False)
        )

    toggle_recording = callbacks.get("toggle_recording")
    menu_items = [
        pystray.MenuItem(labels[status_key], None, enabled=False),
        pystray.MenuItem(
            _recording_action_label(labels, state),
            (lambda *_: toggle_recording()) if toggle_recording else None,
            enabled=toggle_recording is not None,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(labels["recent"], pystray.Menu(*recent_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            labels["vad"],
            lambda *_: callbacks["toggle_vad"](),
            checked=lambda _: cfg.get("use_vad", False),
            enabled=callbacks.get("vad_available", lambda: True)(),
        ),
        pystray.Menu.SEPARATOR,
    ]
    if callbacks.get("open_diagnostics"):
        menu_items.extend(
            [
                pystray.MenuItem(labels["diagnostics"], lambda *_: callbacks["open_diagnostics"]()),
            ]
        )
    menu_items.extend(
        [
            pystray.MenuItem(labels["settings"], lambda *_: callbacks["open_settings"]()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(labels["quit"], lambda *_: callbacks["quit"]()),
        ]
    )
    return pystray.Menu(*menu_items)


def build_appindicator_menu(callbacks: Dict[str, Callable], state: Dict[str, Any]) -> "Gtk.Menu":
    """
    Build simplified menu for AppIndicator backend.

    Args:
        callbacks: Dictionary of callback functions (same as build_pystray_menu)
        state: Application state dictionary

    Returns:
        Gtk.Menu object
    """
    if not APPINDICATOR_AVAILABLE:
        raise RuntimeError("AppIndicator backend unavailable")

    labels = get_tray_labels(cfg)
    status_key = _tray_status_key(state)
    menu = Gtk.Menu()

    status_item = Gtk.MenuItem(label=labels[status_key])
    status_item.set_sensitive(False)
    menu.append(status_item)

    toggle_recording = callbacks.get("toggle_recording")
    recording_item = Gtk.MenuItem(label=_recording_action_label(labels, state))
    recording_item.set_sensitive(toggle_recording is not None)
    if toggle_recording:
        recording_item.connect("activate", lambda *_: toggle_recording())
    menu.append(recording_item)

    menu.append(Gtk.SeparatorMenuItem())

    # Recent transcriptions submenu
    recent_menu_item = Gtk.MenuItem(label=labels["recent"])
    recent_submenu = Gtk.Menu()

    history_entries = read_history(limit=10)
    if history_entries:
        for entry in history_entries:
            text = entry.get("text", "")
            display_text = format_history_entry(entry, max_length=50)
            history_item = Gtk.MenuItem(label=display_text)
            history_item.connect(
                "activate",
                lambda _, t=text: callbacks["copy_to_clipboard"](t)
            )
            recent_submenu.append(history_item)

        recent_submenu.append(Gtk.SeparatorMenuItem())

        clear_item = Gtk.MenuItem(label=labels["clear_history"])
        clear_item.connect("activate", lambda *_: callbacks["clear_history"]())
        recent_submenu.append(clear_item)
    else:
        empty_item = Gtk.MenuItem(label=labels["no_recent"])
        empty_item.set_sensitive(False)
        recent_submenu.append(empty_item)

    recent_menu_item.set_submenu(recent_submenu)
    menu.append(recent_menu_item)

    menu.append(Gtk.SeparatorMenuItem())

    # VAD toggle
    vad_item = Gtk.CheckMenuItem(label=labels["vad"])
    vad_item.set_active(cfg.get("use_vad", False))
    vad_item.set_sensitive(callbacks.get("vad_available", lambda: True)())
    vad_item.connect("activate", lambda *_: callbacks["toggle_vad"]())
    menu.append(vad_item)

    menu.append(Gtk.SeparatorMenuItem())

    if callbacks.get("open_diagnostics"):
        diagnostics_item = Gtk.MenuItem(label=labels["diagnostics"])
        diagnostics_item.connect("activate", lambda *_: callbacks["open_diagnostics"]())
        menu.append(diagnostics_item)

    # Settings
    settings_item = Gtk.MenuItem(label=labels["settings"])
    settings_item.connect("activate", lambda *_: callbacks["open_settings"]())
    menu.append(settings_item)

    menu.append(Gtk.SeparatorMenuItem())

    # Quit
    quit_item = Gtk.MenuItem(label=labels["quit"])
    quit_item.connect("activate", lambda *_: callbacks["quit"]())
    menu.append(quit_item)

    return menu


# =============================================================================
# Tray Refresh
# =============================================================================

def refresh_tray_indicator(state: Dict[str, Any]) -> None:
    """
    Update tray icon and label based on current state.

    Args:
        state: Application state dictionary
    """
    global _icon, _indicator, _icon_ready, _icon_images, _icon_files

    if state.get("tray_backend") == "appindicator":
        if _indicator is None or not _icon_files or GLib is None:
            return

        icon_key = _tray_status_key(state)
        status = get_tray_labels(cfg)[icon_key]

        icon_path = _icon_files.get(icon_key)
        if icon_path:
            def _update_icon():
                _indicator.set_icon_full(str(icon_path), status)
                _indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
                _indicator.set_label(_compact_appindicator_label(icon_key), APP_NAME)
                return False
            GLib.idle_add(_update_icon)
        return

    # PyStray backend - thread-safe check
    with _icon_ready_lock:
        if not _icon or not _icon_ready:
            return

    image_key = _tray_status_key(state)
    status = get_tray_labels(cfg)[image_key]

    from whisprbar.hotkeys import key_to_label
    hotkey_key = state.get("hotkey_key")
    session_label = state.get("session_type", "unknown")
    _icon.title = (
        f"{APP_NAME} - {status} [{session_label}] "
        f"({key_to_label(hotkey_key)}: {get_tray_labels(cfg)['start_stop']})"
    )
    image = _icon_images.get(image_key) or _icon_images.get("ready")
    if image is not None:
        _icon.icon = image


def refresh_menu(callbacks: Dict[str, Callable], state: Dict[str, Any]) -> None:
    """
    Rebuild and update tray menu.

    Args:
        callbacks: Dictionary of callback functions
        state: Application state dictionary
    """
    global _icon, _indicator, _icon_ready

    if state.get("tray_backend") == "appindicator":
        if _indicator is None or GLib is None:
            return

        def _update_menu():
            menu = build_appindicator_menu(callbacks, state)
            _indicator.set_menu(menu)
            menu.show_all()
            return False

        GLib.idle_add(_update_menu)
        return

    # PyStray backend - thread-safe check
    with _icon_ready_lock:
        icon_is_ready = _icon_ready and _icon is not None

    if icon_is_ready:
        _icon.menu = build_pystray_menu(callbacks, state)
        try:
            _icon.update_menu()
        except Exception:
            pass


# =============================================================================
# Tray Startup
# =============================================================================

def start_pystray_tray(callbacks: Dict[str, Callable], state: Dict[str, Any]) -> Callable[[], None]:
    """
    Initialize and return PyStray tray runner.

    Args:
        callbacks: Dictionary of callback functions
        state: Application state dictionary

    Returns:
        Function that runs the PyStray event loop
    """
    global _icon, _icon_ready, _icon_images

    if pystray is None:
        raise RuntimeError("PyStray not available")

    if not _icon_images:
        initialize_icons()

    _icon_ready = False
    tray_menu = build_pystray_menu(callbacks, state)
    _icon = pystray.Icon(APP_NAME, _icon_images["ready"], menu=tray_menu)
    state["tray_backend"] = os.environ.get("PYSTRAY_BACKEND", state.get("tray_backend") or "auto")

    if not hasattr(_icon, "_menu_handle"):
        _icon._menu_handle = None  # type: ignore[attr-defined]

    def _setup(icon):
        global _icon_ready
        with _icon_ready_lock:
            _icon_ready = True
        refresh_tray_indicator(state)
        refresh_menu(callbacks, state)

    def _run_loop() -> None:
        _icon.run(setup=_setup)

    return _run_loop


def start_appindicator_tray(callbacks: Dict[str, Callable], state: Dict[str, Any]) -> Callable[[], None]:
    """
    Initialize and return AppIndicator tray runner.

    Args:
        callbacks: Dictionary of callback functions
        state: Application state dictionary

    Returns:
        Function that runs the GTK main loop
    """
    global _indicator, _gtk_loop, _icon_files

    if not APPINDICATOR_AVAILABLE:
        raise RuntimeError("AppIndicator backend unavailable")

    ensure_directories()

    if not _icon_files:
        initialize_icons()

    if not _icon_files:
        raise RuntimeError("Icon files missing")

    if Gtk is not None:
        try:
            Gtk.init([])
        except Exception:
            pass

    indicator_id = f"aa-{APP_NAME.lower()}"
    _indicator = AppIndicator3.Indicator.new(
        indicator_id,
        str(_icon_files["ready"]),
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS
    )
    _indicator.set_icon_full(str(_icon_files["ready"]), get_tray_labels(cfg)["ready"])
    _indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

    try:
        _indicator.set_property("ordering-index", 0)
    except Exception as exc:
        debug(f"Ordering hint unsupported: {exc}")

    menu = build_appindicator_menu(callbacks, state)
    menu.show_all()
    _indicator.set_menu(menu)
    _indicator.set_label(_compact_appindicator_label("ready"), APP_NAME)

    _gtk_loop = GLib.MainLoop()

    def _run_loop() -> None:
        _gtk_loop.run()

    return _run_loop


# =============================================================================
# Shutdown
# =============================================================================

def shutdown_tray(state: Dict[str, Any]) -> None:
    """
    Clean up and shutdown tray icon.

    Args:
        state: Application state dictionary
    """
    global _icon, _indicator, _gtk_loop, _icon_ready

    if state.get("tray_backend") == "appindicator":
        if _indicator is not None:
            with contextlib.suppress(Exception):
                _indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
        if _gtk_loop is not None and _gtk_loop.is_running():
            _gtk_loop.quit()
        _indicator = None
        _gtk_loop = None
    else:
        with _icon_ready_lock:
            if _icon and _icon_ready:
                with contextlib.suppress(Exception):
                    _icon.visible = False
                with contextlib.suppress(Exception):
                    _icon.stop()
            _icon = None

    with _icon_ready_lock:
        _icon_ready = False


# =============================================================================
# Utility Functions
# =============================================================================

def get_icon_ready() -> bool:
    """Check if tray icon is ready."""
    return _icon_ready


def set_icon_ready(ready: bool) -> None:
    """Set tray icon ready state."""
    global _icon_ready
    _icon_ready = ready
