#!/usr/bin/env python3
"""WhisprBar voice-to-text tray application."""
import argparse
import contextlib
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import numpy as np
import pyperclip
import sounddevice as sd
from PIL import Image, ImageDraw
from openai import OpenAI
from pynput import keyboard

SYSTEM_GI_PATHS = [
    "/usr/lib/python3/dist-packages",
    f"/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/dist-packages",
]
for _path in SYSTEM_GI_PATHS:
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.append(_path)

try:
    import gi
    GI_AVAILABLE = True
except Exception:
    gi = None
    GI_AVAILABLE = False

Gtk = None
GLib = None
AppIndicator3 = None
if GI_AVAILABLE:
    try:
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib
    except Exception:
        Gtk = None
        GLib = None
        GI_AVAILABLE = False

if GI_AVAILABLE:
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3
        APPINDICATOR_AVAILABLE = True
    except Exception:
        AppIndicator3 = None
        APPINDICATOR_AVAILABLE = False
else:
    APPINDICATOR_AVAILABLE = False


def select_tray_backend() -> str:
    if APPINDICATOR_AVAILABLE:
        os.environ["PYSTRAY_BACKEND"] = "appindicator"
        return "appindicator"
    for backend in ("gtk", "xorg"):
        if backend == "gtk" and not GI_AVAILABLE:
            continue
        try:
            if backend == "gtk" and not shutil.which("xprop"):
                raise RuntimeError("GTK backend requires X11 helpers")
            os.environ["PYSTRAY_BACKEND"] = backend
            return backend
        except Exception as exc:
            print(f"[WARN] Tray backend {backend} unavailable: {exc}")
    os.environ.pop("PYSTRAY_BACKEND", None)
    return "auto"


TRAY_BACKEND = select_tray_backend()

import pystray

APP_NAME = "WhisprBar"
APP_VERSION = "0.1.0"
GITHUB_REPO = os.environ.get("WHISPRBAR_GITHUB_REPO", "henrik092/whisprBar")
GITHUB_RELEASE_URL = (
    os.environ.get(
        "WHISPRBAR_UPDATE_URL",
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
    )
)
UPDATE_COMMAND = os.environ.get(
    "WHISPRBAR_UPDATE_COMMAND",
    "git pull && ./install.sh",
)
UPDATE_CHECK_TIMEOUT = float(os.environ.get("WHISPRBAR_UPDATE_TIMEOUT", "5"))
CONFIG_PATH = Path.home() / ".config" / "whisprbar.json"
DATA_DIR = Path.home() / ".local" / "share" / "whisprbar"
HIST_FILE = DATA_DIR / "history.jsonl"

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_ERROR = "error"

CLI_STATUS_LABEL = {
    STATUS_OK: "[ OK ]",
    STATUS_WARN: "[WARN]",
    STATUS_ERROR: "[FAIL]",
}

STATUS_ICON_NAME = {
    STATUS_OK: "emblem-ok-symbolic",
    STATUS_WARN: "dialog-warning",
    STATUS_ERROR: "dialog-error",
}


@dataclass
class DiagnosticResult:
    key: str
    label: str
    status: str
    detail: str
    remedy: Optional[str] = None


def get_env_file_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "whisprbar.env"
    return Path.home() / ".config" / "whisprbar.env"


def load_env_file_values() -> Dict[str, str]:
    env_path = get_env_file_path()
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    try:
        with env_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    values[key] = value
    except Exception as exc:
        debug(f"Failed to read env file {env_path}: {exc}")
    return values


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None

SAMPLE_RATE = 16_000
CHANNELS = 1
BLOCK_SIZE = 1_024
OPENAI_MODEL = os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe")

DEFAULT_CFG = {
    "language": "de",
    "device_name": None,
    "hotkey": "F9",
    "notifications_enabled": False,
    "auto_paste_enabled": True,
    "paste_sequence": "auto",
    "use_vad": False,
    "vad_energy_ratio": 0.02,
    "vad_bridge_ms": 180,
    "vad_min_energy_frames": 2,
    "first_run_complete": False,
    "check_updates": True,
}

cfg = DEFAULT_CFG.copy()


def detect_session_type() -> str:
    session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if session in {"x11", "xorg"}:
        return "x11"
    if session == "wayland":
        return "wayland"
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


state = {
    "recording": False,
    "device_idx": None,
    "stream": None,
    "session_type": detect_session_type(),
    "wayland_notice_shown": False,
    "tray_backend": None,
    "hotkey_capture_active": False,
    "client_ready": False,
    "client_warning_shown": False,
}


def parse_version(value: str) -> Tuple[int, ...]:
    cleaned = value.strip()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts: List[int] = []
    for segment in cleaned.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def fetch_latest_release_tag() -> Optional[str]:
    request = urllib.request.Request(
        GITHUB_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=UPDATE_CHECK_TIMEOUT) as response:
        payload = response.read().decode("utf-8")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse GitHub release payload: {exc}") from exc
    return data.get("tag_name") or data.get("name")


def is_newer_version(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _update_check_worker() -> None:
    if not cfg.get("check_updates", True):
        return
    try:
        latest = fetch_latest_release_tag()
    except Exception as exc:
        debug(f"Update check failed: {exc}")
        return
    if not latest:
        return
    if is_newer_version(latest, APP_VERSION):
        message = (
            f"A newer version ({latest}) is available. Update via: {UPDATE_COMMAND}"
        )
        debug(message)
        print(f"[INFO] {message}")
        notify(message, force=True)


def check_for_updates_async() -> None:
    if not cfg.get("check_updates", True):
        return
    threading.Thread(target=_update_check_worker, name="whisprbar-update-check", daemon=True).start()


def is_wayland_session() -> bool:
    return state.get("session_type") == "wayland"


def session_status_label() -> str:
    session_type = state.get("session_type") or "unknown"
    if session_type == "wayland":
        return "Wayland · Clipboard-only"
    if session_type == "x11":
        return "X11 · Auto-paste"
    return session_type.capitalize()


def tray_backend_label() -> str:
    backend = state.get("tray_backend") or "auto"
    mapping = {
        "appindicator": "AppIndicator",
        "gtk": "GTK StatusIcon",
        "auto": "Auto",
    }
    return mapping.get(backend, backend.capitalize())


icon: Optional[pystray.Icon] = None
hotkey_listener: Optional[keyboard.Listener] = None
capture_listener: Optional[keyboard.Listener] = None
HotkeyBinding = Tuple[frozenset[str], str]
HOTKEY_KEY: HotkeyBinding = (frozenset(), "F9")
controller = keyboard.Controller()
client = None
DEBUG = bool(os.environ.get("WHISPRBAR_DEBUG")) or sys.stdout.isatty()
settings_window = None
diagnostics_window = None
icon_ready = False
indicator = None
gtk_loop: Optional[GLib.MainLoop] = None
icon_files = {}

state["tray_backend"] = TRAY_BACKEND

try:
    import webrtcvad

    VAD_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    webrtcvad = None
    VAD_AVAILABLE = False


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HIST_FILE.touch(exist_ok=True)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def debug(message: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {message}")


def check_runtime_dependencies() -> None:
    warnings = []
    if not shutil.which("xdotool"):
        warnings.append("xdotool (auto paste)")
    try:
        import importlib
        if importlib.util.find_spec("gi") is None:
            raise ImportError
    except Exception:
        warnings.append("python3-gi / appindicator (tray menu)")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if state.get("tray_backend") != "appindicator" and "gnome" in desktop:
        warnings.append("AppIndicator extension (tray control)")
    if warnings:
        message = "Missing: " + ", ".join(warnings)
        print(f"[WARN] {message}", file=sys.stderr)
        notify(message)


def collect_diagnostics() -> List[DiagnosticResult]:
    ensure_directories()
    results: List[DiagnosticResult] = []
    env_values = load_env_file_values()

    session = detect_session_type()
    session_label = session_status_label()
    if session in {"x11", "wayland"}:
        results.append(DiagnosticResult("session", "Session", STATUS_OK, session_label))
    else:
        results.append(
            DiagnosticResult(
                "session",
                "Session",
                STATUS_WARN,
                session_label,
                remedy="Switch to an X11 or Wayland session for full functionality.",
            )
        )

    tray_detail = f"Selected backend: {tray_backend_label()}"
    if APPINDICATOR_AVAILABLE:
        results.append(DiagnosticResult("tray", "Tray backend", STATUS_OK, tray_detail))
    elif GI_AVAILABLE:
        results.append(
            DiagnosticResult(
                "tray",
                "Tray backend",
                STATUS_WARN,
                tray_detail + " (AppIndicator libraries missing)",
                remedy="Install libappindicator / gir1.2-appindicator packages for a more stable tray icon.",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                "tray",
                "Tray backend",
                STATUS_WARN,
                tray_detail + " (GTK bindings unavailable)",
                remedy="Install python3-gi and appindicator libraries to enable the preferred backend.",
            )
        )

    if session == "x11":
        has_xdotool = command_exists("xdotool")
        status = STATUS_OK if has_xdotool else STATUS_ERROR if cfg.get("auto_paste_enabled") else STATUS_WARN
        detail = "xdotool available for auto paste" if has_xdotool else "xdotool missing; auto paste limited"
        remedy = None if has_xdotool else "Install xdotool (e.g. sudo apt install xdotool)."
        results.append(DiagnosticResult("auto_paste", "Auto paste", status, detail, remedy=remedy))
    elif session == "wayland":
        has_wl = command_exists("wl-clipboard")
        detail = "wl-clipboard available for clipboard sync" if has_wl else "wl-clipboard missing; clipboard-only mode may fail"
        remedy = None if has_wl else "Install wl-clipboard (e.g. sudo apt install wl-clipboard)."
        status = STATUS_OK if has_wl else STATUS_WARN
        results.append(DiagnosticResult("auto_paste", "Auto paste", status, detail, remedy=remedy))
    else:
        results.append(
            DiagnosticResult(
                "auto_paste",
                "Auto paste",
                STATUS_WARN,
                "Session type unknown; auto paste may be limited.",
            )
        )

    notify_support = []
    if command_exists("notify-send"):
        notify_support.append("notify-send")
    if command_exists("zenity"):
        notify_support.append("zenity")
    if command_exists("kdialog"):
        notify_support.append("kdialog")
    if notify_support:
        detail = ", ".join(notify_support)
        results.append(DiagnosticResult("notifications", "Notifications", STATUS_OK, f"Available: {detail}"))
    else:
        results.append(
            DiagnosticResult(
                "notifications",
                "Notifications",
                STATUS_WARN,
                "notify-send / zenity not found; GUI warnings may not appear.",
                remedy="Install libnotify-bin (notify-send) or zenity for desktop alerts.",
            )
        )

    env_api_key = os.getenv("OPENAI_API_KEY") or env_values.get("OPENAI_API_KEY", "")
    if env_api_key:
        masked = f"Configured ({len(env_api_key)} characters)"
        results.append(DiagnosticResult("api_key", "OpenAI API key", STATUS_OK, masked))
    else:
        results.append(
            DiagnosticResult(
                "api_key",
                "OpenAI API key",
                STATUS_ERROR,
                "Missing",
                remedy="Add OPENAI_API_KEY to ~/.config/whisprbar.env or export it before starting WhisprBar.",
            )
        )

    config_dir = CONFIG_PATH.parent
    if config_dir.exists() and os.access(config_dir, os.W_OK):
        results.append(DiagnosticResult("config_dir", "Config directory", STATUS_OK, str(config_dir)))
    else:
        results.append(
            DiagnosticResult(
                "config_dir",
                "Config directory",
                STATUS_ERROR,
                f"Not writable: {config_dir}",
                remedy="Adjust permissions so the current user can write to the config directory.",
            )
        )

    history_dir = HIST_FILE.parent
    if history_dir.exists() and os.access(history_dir, os.W_OK):
        results.append(DiagnosticResult("history", "History storage", STATUS_OK, str(HIST_FILE)))
    else:
        results.append(
            DiagnosticResult(
                "history",
                "History storage",
                STATUS_ERROR,
                f"Not writable: {history_dir}",
                remedy="Adjust permissions for ~/.local/share/whisprbar to enable history logging.",
            )
        )

    device_error = None
    devices: List[Dict[str, str]] = []
    try:
        devices = list_input_devices()
    except Exception as exc:
        device_error = str(exc)

    if device_error:
        results.append(
            DiagnosticResult(
                "audio_devices",
                "Audio input",
                STATUS_ERROR,
                f"Failed to query devices: {device_error}",
                remedy="Confirm PortAudio/sounddevice setup and that audio hardware is available.",
            )
        )
    elif not devices:
        results.append(
            DiagnosticResult(
                "audio_devices",
                "Audio input",
                STATUS_WARN,
                "No input devices detected.",
                remedy="Connect a microphone and ensure ALSA/PipeWire devices are available.",
            )
        )
    else:
        selected_name = cfg.get("device_name")
        device_label = selected_name or "System Default"
        detail = f"Detected {len(devices)} devices (active: {device_label})"
        try:
            device_idx = find_device_index_by_name(selected_name)
            sd.check_input_settings(device=device_idx, samplerate=SAMPLE_RATE, channels=CHANNELS)
            results.append(DiagnosticResult("audio_devices", "Audio input", STATUS_OK, detail))
        except Exception as exc:
            results.append(
                DiagnosticResult(
                    "audio_devices",
                    "Audio input",
                    STATUS_WARN,
                    f"{detail}; validation failed: {exc}",
                    remedy="Select a different input device in settings or adjust audio backend.",
                )
            )

    if session == "wayland":
        results.append(
            DiagnosticResult(
                "hotkey",
                "Hotkey support",
                STATUS_WARN,
                "Wayland session detected; global hotkeys may be restricted.",
                remedy="Consider running an X11 session or using a compositor with global shortcut portals.",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                "hotkey", "Hotkey support", STATUS_OK, "Global hotkeys available in this session." )
        )

    return results


def run_diagnostics_cli() -> int:
    results = collect_diagnostics()
    print("WhisprBar diagnostics")
    print("--------------------")
    for result in results:
        status_label = CLI_STATUS_LABEL.get(result.status, "[INFO]")
        print(f"{status_label} {result.label}: {result.detail}")
        if result.remedy:
            print(f"        Fix: {result.remedy}")
    has_errors = any(item.status == STATUS_ERROR for item in results)
    has_warnings = any(item.status == STATUS_WARN for item in results)
    if has_errors:
        print("Diagnostics completed with errors.")
    elif has_warnings:
        print("Diagnostics completed with warnings.")
    else:
        print("All diagnostics passed.")
    return 1 if has_errors else 0


def mark_first_run_complete() -> None:
    if not cfg.get("first_run_complete", False):
        cfg["first_run_complete"] = True
        save_config()


def maybe_show_first_run_diagnostics() -> None:
    if cfg.get("first_run_complete", False):
        return
    open_diagnostics_window(first_run=True)


def load_config() -> None:
    ensure_directories()
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                file_cfg = json.load(handle)
            cfg.update(file_cfg)
    except Exception as exc:
        print(f"[WARN] Failed to load config: {exc}", file=sys.stderr)


def save_config() -> None:
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[WARN] Failed to write config: {exc}", file=sys.stderr)


def notify(message: str, title: str = APP_NAME, *, force: bool = False) -> None:
    if not force and not cfg.get("notifications_enabled", True):
        return
    try:
        subprocess.Popen(["notify-send", title, message])
    except Exception:
        pass


FKEYS = {}
for idx in range(1, 25):
    attr = f"f{idx}"
    key_obj = getattr(keyboard.Key, attr, None)
    if key_obj is not None:
        FKEYS[f"F{idx}"] = key_obj

def _collect_keys(*names: str) -> Set[keyboard.Key]:
    keys: Set[keyboard.Key] = set()
    for name in names:
        key_obj = getattr(keyboard.Key, name, None)
        if key_obj is not None:
            keys.add(key_obj)
    return keys


MODIFIER_MAP = {
    "CTRL": _collect_keys("ctrl", "ctrl_l", "ctrl_r"),
    "ALT": _collect_keys("alt", "alt_l", "alt_r"),
    "SHIFT": _collect_keys("shift", "shift_l", "shift_r"),
    "SUPER": _collect_keys("cmd", "cmd_l", "cmd_r", "super", "super_l", "super_r"),
}

MODIFIER_LOOKUP = {
    key: name
    for name, keys in MODIFIER_MAP.items()
    for key in keys
}

MODIFIER_LABELS = {
    "CTRL": "Ctrl",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "SUPER": "Super",
}

MODIFIER_ORDER = {
    "CTRL": 0,
    "SHIFT": 1,
    "ALT": 2,
    "SUPER": 3,
}


def normalize_key_token(token: str) -> Optional[str]:
    token = (token or "").strip().upper()
    if not token:
        return None
    if token in FKEYS:
        return token
    if len(token) == 1:
        return token
    return None


def parse_hotkey(binding: str):
    binding = (binding or "").strip()
    if not binding:
        return (frozenset(), "F9")
    parts = [part.strip() for part in binding.split("+") if part.strip()]
    if not parts:
        return (frozenset(), "F9")
    key_token = normalize_key_token(parts[-1])
    if not key_token:
        return (frozenset(), "F9")
    modifiers = {
        part.upper()
        for part in parts[:-1]
        if part.upper() in MODIFIER_MAP
    }
    return (frozenset(modifiers), key_token)


def key_to_label(key_obj) -> str:
    if isinstance(key_obj, tuple) and len(key_obj) == 2:
        modifiers, token = key_obj
        parts = [
            MODIFIER_LABELS[m]
            for m in sorted(modifiers, key=lambda x: MODIFIER_ORDER.get(x, 99))
        ]
        if token in FKEYS:
            parts.append(token)
        else:
            parts.append(token.upper())
        return "+".join(parts) if parts else token.upper()
    for name, key in FKEYS.items():
        if key_obj == key:
            return name
    if isinstance(key_obj, keyboard.KeyCode):
        if key_obj.char:
            return key_obj.char.upper()
    if isinstance(key_obj, keyboard.Key):
        return str(key_obj).split(".")[-1].upper()
    return "F9"


def key_to_config_string(key_obj) -> str:
    if isinstance(key_obj, tuple) and len(key_obj) == 2:
        modifiers, token = key_obj
        parts = [mod for mod in sorted(modifiers, key=lambda x: MODIFIER_ORDER.get(x, 99))]
        parts.append(token.upper())
        return "+".join(parts)
    for name, key in FKEYS.items():
        if key_obj == key:
            return name
    if isinstance(key_obj, keyboard.KeyCode) and key_obj.char:
        return key_obj.char.upper()
    return "F9"


def hotkey_to_label(binding: HotkeyBinding) -> str:
    return key_to_label(binding)


def hotkey_to_config(binding: HotkeyBinding) -> str:
    return key_to_config_string(binding)


def event_to_token(key) -> Optional[str]:
    for name, key_obj in FKEYS.items():
        if key == key_obj:
            return name
    if isinstance(key, keyboard.KeyCode) and key.char:
        char = key.char.strip()
        if len(char) == 1:
            return char.upper()
    return None


def modifier_name(key) -> Optional[str]:
    return MODIFIER_LOOKUP.get(key)


def menu_action(func, *args, **kwargs):
    def _handler(icon, item):
        func(*args, **kwargs)
    return _handler


def cfg_equals_checker(key: str, expected):
    def _checked(item):
        return cfg.get(key) == expected
    return _checked


def start_hotkey_listener() -> None:
    global hotkey_listener
    if hotkey_listener:
        hotkey_listener.stop()
        hotkey_listener = None

    active_modifiers: Set[str] = set()
    active_tokens: Set[str] = set()

    def on_press(key):
        if state.get("recording") and key == keyboard.Key.esc:
            stop_recording()
            return
        if state.get("hotkey_capture_active"):
            return
        mod = modifier_name(key)
        if mod:
            active_modifiers.add(mod)
            return
        token = event_to_token(key)
        if not token:
            return
        required_mods, required_token = HOTKEY_KEY
        if token != required_token:
            return
        if token in active_tokens:
            return
        active_tokens.add(token)
        if required_mods.issubset(active_modifiers):
            toggle_recording()

    def on_release(key):
        if state.get("hotkey_capture_active"):
            return
        mod = modifier_name(key)
        if mod:
            active_modifiers.discard(mod)
        token = event_to_token(key)
        if token:
            active_tokens.discard(token)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()
    hotkey_listener = listener


AUDIO_QUEUE: Optional[queue.Queue] = None


def list_input_devices() -> list:
    devices = []
    for idx, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) > 0:
            devices.append({
                "index": idx,
                "name": info.get("name", f"Device {idx}"),
            })
    return devices


def find_device_index_by_name(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    for device in list_input_devices():
        if device["name"].lower() == name.lower():
            return device["index"]
    for device in list_input_devices():
        if name.lower() in device["name"].lower():
            return device["index"]
    return None


icon_images = {}


def refresh_tray_indicator() -> None:
    if state.get("tray_backend") == "appindicator":
        if indicator is None or not icon_files or GLib is None:
            return
        status = "Recording" if state.get("recording") else "Ready"
        icon_key = "recording" if state.get("recording") else "ready"
        icon_path = icon_files.get(icon_key)
        if icon_path:
            def _update_icon():
                indicator.set_icon_full(str(icon_path), status)
                indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
                indicator.set_label(f"{APP_NAME} - {status}", APP_NAME)
                return False
            GLib.idle_add(_update_icon)
        return

    if not icon or not icon_ready:
        return
    status = "Recording" if state.get("recording") else "Ready"
    session_label = session_status_label()
    icon.title = f"{APP_NAME} - {status} [{session_label}] ({key_to_label(HOTKEY_KEY)}: Start/Stop)"
    image_key = "recording" if state.get("recording") else "ready"
    image = icon_images.get(image_key) or icon_images.get("ready")
    if image is not None:
        icon.icon = image


def refresh_menu() -> None:
    if state.get("tray_backend") == "appindicator":
        if indicator is None or GLib is None:
            return

        def _update_menu():
            menu = build_appindicator_menu()
            indicator.set_menu(menu)
            menu.show_all()
            return False

        GLib.idle_add(_update_menu)
        return

    if icon and icon_ready:
        icon.menu = build_menu()
        try:
            icon.update_menu()
        except Exception:
            pass


def build_icon(
    size: int = 64,
    accent_color=(255, 255, 255, 255),
    body_color=(0, 0, 0, 220),
    background_color=(64, 64, 64, 180),
    border_color=(255, 255, 255, 230),
) -> Image.Image:
    """Render a small microphone glyph with an optional circular background."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    padding = max(2, size // 16)
    bg_bounds = (padding, padding, size - padding, size - padding)
    border_width = max(1, size // 32)
    draw.ellipse(bg_bounds, fill=background_color, outline=border_color, width=border_width)

    # Microphone capsule.
    draw.ellipse((22, 10, 42, 36), fill=body_color)
    # Stem and base.
    draw.rectangle((30, 36, 34, 50), fill=body_color)
    draw.rectangle((24, 48, 40, 52), fill=body_color)
    # Status accent inside the capsule.
    draw.ellipse((26, 14, 38, 32), fill=accent_color)
    return img


def store_icon(name: str, image: Image.Image) -> Path:
    ensure_directories()
    path = DATA_DIR / f"{name}.png"
    image.save(path, format="PNG")
    icon_files[name] = path
    return path


def update_device_index() -> None:
    idx = find_device_index_by_name(cfg.get("device_name"))
    state["device_idx"] = idx


def prepare_openai_client() -> bool:
    global client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        env_values = load_env_file_values()
        api_key = env_values.get("OPENAI_API_KEY")
    if not api_key:
        state["client_ready"] = False
        client = None
        print("[WARN] OPENAI_API_KEY not configured; transcription disabled.", file=sys.stderr)
        notify("OPENAI_API_KEY not set. Transcription disabled until configured.")
        return False
    try:
        client = OpenAI(api_key=api_key)
        state["client_ready"] = True
        state["client_warning_shown"] = False
        return True
    except Exception as exc:
        client = None
        state["client_ready"] = False
        print(f"[WARN] Failed to initialise OpenAI client: {exc}", file=sys.stderr)
        notify(f"OpenAI client setup failed: {exc}")
        return False


def recording_callback(indata, frames, time_info, status):  # pragma: no cover - stream callback
    if status and status.input_overflow:
        print(f"[WARN] Audio overflow: {status}", file=sys.stderr)
    if not state.get("recording"):
        return
    if AUDIO_QUEUE is not None:
        AUDIO_QUEUE.put(indata.copy())


def start_recording(*_args) -> None:
    if state.get("recording"):
        return
    update_device_index()
    try:
        global AUDIO_QUEUE
        queue_obj: queue.Queue = queue.Queue()
        AUDIO_QUEUE = queue_obj
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=BLOCK_SIZE,
            callback=recording_callback,
            dtype="float32",
            device=state.get("device_idx"),
        )
        stream.start()
        state["stream"] = stream
        state["recording"] = True
        notify("Recording started.")
        debug("Recording started")
        refresh_tray_indicator()
        refresh_menu()
    except Exception as exc:
        AUDIO_QUEUE = None
        notify(f"Unable to start recording: {exc}")
        print(f"[ERROR] start_recording failed: {exc}", file=sys.stderr)


def stop_recording(*_args) -> None:
    if not state.get("recording"):
        return
    global AUDIO_QUEUE
    queue_obj = AUDIO_QUEUE
    AUDIO_QUEUE = None
    stream = state.get("stream")
    state["recording"] = False
    state["stream"] = None
    refresh_tray_indicator()
    refresh_menu()
    if stream:
        with contextlib.suppress(Exception):
            stream.stop()
            stream.close()
    frames = []
    if queue_obj is not None:
        while not queue_obj.empty():
            frames.append(queue_obj.get())
    if not frames:
        notify("No audio captured.")
        return
    audio = np.concatenate(frames, axis=0)
    duration = audio.shape[0] / SAMPLE_RATE
    debug(f"Captured audio duration: {duration:.2f}s, samples: {audio.shape[0]}")
    threading.Thread(target=transcribe_audio, args=(audio,), daemon=True).start()


def toggle_recording(*_args) -> None:
    if state.get("recording"):
        stop_recording()
    else:
        start_recording()


PASTE_OPTIONS = {
    "auto": "Auto Detect",
    "ctrl_v": "Ctrl+V",
    "ctrl_shift_v": "Ctrl+Shift+V",
    "shift_insert": "Shift+Insert",
    "type": "Type Simulation",
    "clipboard": "Clipboard Only",
}


def press_key(key_obj) -> None:
    controller.press(key_obj)
    controller.release(key_obj)


TERMINAL_KEYWORDS = (
    "terminal",
    "alacritty",
    "konsole",
    "kgx",
    "tilix",
    "gnome-terminal",
    "xfce4-terminal",
    "xterm",
    "st-256color",
    "kitty",
    "wezterm",
    "hyper",
    "terminator",
    "rio",
    "yakuake",
    "tmux",
    "bash",
    "shell",
)


def detect_auto_paste_sequence() -> str:
    if is_wayland_session():
        debug("Wayland session detected, forcing clipboard-only auto paste")
        return "clipboard"
    xdotool = shutil.which("xdotool")
    if not xdotool:
        debug("xdotool unavailable, defaulting to ctrl+V")
        return "ctrl_v"
    try:
        focus = subprocess.run(
            [xdotool, "getactivewindow"], capture_output=True, text=True, check=True
        )
        win_id = focus.stdout.strip().splitlines()[-1].strip()
        if not win_id or win_id.lower() in {"0x0", "0"}:
            return "ctrl_v"
        name_proc = subprocess.run(
            [xdotool, "getwindowname", win_id],
            capture_output=True,
            text=True,
            check=True,
            timeout=1,
        )
        name = name_proc.stdout.strip().lower()

        class_name = ""
        xprop = shutil.which("xprop")
        if xprop:
            try:
                class_proc = subprocess.run(
                    [xprop, "-id", win_id, "WM_CLASS"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=1,
                )
                class_out = class_proc.stdout.lower()
                # WM_CLASS(STRING) = "gnome-terminal", "Gnome-terminal"
                class_name = class_out
            except Exception as exc:
                debug(f"xprop class lookup failed: {exc}")

        debug(f"Focused window: class='{class_name}', name='{name}'")
        for keyword in TERMINAL_KEYWORDS:
            if keyword in class_name or keyword in name:
                return "ctrl_shift_v"
    except Exception as exc:
        debug(f"Window detection failed: {exc}")
    return "ctrl_v"


def simulate_typing(text: str) -> None:
    if not text:
        return
    controller.type(text)


def perform_auto_paste(text: str) -> None:
    sequence = cfg.get("paste_sequence", "auto")
    if sequence == "auto":
        sequence = detect_auto_paste_sequence()
    wayland_session = is_wayland_session()
    if wayland_session:
        sequence = "clipboard"
    debug(f"Auto paste sequence: {sequence}")
    if sequence == "clipboard":
        if wayland_session and not state.get("wayland_notice_shown"):
            notify("Wayland session detected: text copied, press Ctrl+V to paste.")
            state["wayland_notice_shown"] = True
        debug("Clipboard-only paste; skipping key injection")
        return
    if sequence == "type":
        time.sleep(0.3)
        simulate_typing(text)
        return

    time.sleep(0.3)

    xdotool = shutil.which("xdotool")
    if xdotool:
        mapping = {
            "ctrl_v": "ctrl+v",
            "ctrl_shift_v": "ctrl+Shift+v",
            "shift_insert": "shift+Insert",
        }
        target = mapping.get(sequence)
        if target:
            try:
                subprocess.run([xdotool, "key", target], check=True)
                debug(f"xdotool sent: {target}")
                return
            except Exception as exc:
                debug(f"xdotool failed ({exc}), falling back to pynput")

    if sequence == "ctrl_shift_v":
        with controller.pressed(keyboard.Key.ctrl):
            with controller.pressed(keyboard.Key.shift):
                press_key("v")
    elif sequence == "shift_insert":
        with controller.pressed(keyboard.Key.shift):
            press_key(keyboard.Key.insert)
    else:
        with controller.pressed(keyboard.Key.ctrl):
            press_key("v")


def _drop_short_runs(mask: np.ndarray, min_len: int) -> np.ndarray:
    if min_len <= 1:
        return mask
    cleaned = mask.copy()
    indices = np.flatnonzero(cleaned)
    if indices.size == 0:
        return cleaned
    start = indices[0]
    prev = indices[0]
    count = 1
    for val in indices[1:]:
        if val == prev + 1:
            prev = val
            count += 1
            continue
        if count < min_len:
            cleaned[start : prev + 1] = False
        start = val
        prev = val
        count = 1
    if count < min_len:
        cleaned[start : prev + 1] = False
    return cleaned


def apply_vad(audio: np.ndarray) -> np.ndarray:
    mono = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not cfg.get("use_vad") or not VAD_AVAILABLE:
        return mono

    pcm = np.clip(mono, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    frame_ms = 30
    frame_length = int(SAMPLE_RATE * frame_ms / 1000)
    if frame_length <= 0:
        return mono

    total_frames = len(pcm16) // frame_length
    if total_frames == 0:
        return mono

    usable_samples = total_frames * frame_length
    trimmed_pcm = pcm16[:usable_samples]
    remainder = pcm16[usable_samples:]
    if remainder.ndim > 1:
        remainder = remainder.reshape(-1)
    frames = trimmed_pcm.reshape(total_frames, frame_length)

    vad_mode = int(cfg.get("vad_mode", 1))
    vad_mode = max(0, min(3, vad_mode))
    try:
        vad = webrtcvad.Vad(vad_mode)
    except Exception as exc:
        debug(f"Invalid VAD mode {vad_mode} ({exc}); falling back to default")
        vad = webrtcvad.Vad(1)

    speech_mask = np.zeros(total_frames, dtype=bool)
    for idx, frame in enumerate(frames):
        try:
            speech_mask[idx] = vad.is_speech(frame.tobytes(), SAMPLE_RATE)
        except Exception as exc:
            debug(f"VAD frame failed ({exc}); disabling")
            return mono

    frame_float = frames.astype(np.float32) / 32767.0
    # Use RMS energy as a safety net for quiet speech that the VAD might miss.
    rms = np.sqrt(np.mean(np.square(frame_float), axis=1))
    max_rms = float(rms.max()) if rms.size else 0.0
    energy_floor = float(cfg.get("vad_energy_floor", 0.0005))
    energy_ratio_cfg = float(cfg.get("vad_energy_ratio", 0.05))
    energy_ratio = max(0.005, min(energy_ratio_cfg, 0.3))
    energy_threshold = max(energy_floor, max_rms * energy_ratio)
    nonzero_rms = rms[rms > energy_floor]
    if nonzero_rms.size:
        percentile = float(np.percentile(nonzero_rms, 75))
        energy_threshold = min(energy_threshold, max(energy_floor, percentile))
    energy_mask = rms >= energy_threshold if rms.size else np.zeros_like(speech_mask)

    soft_ratio = max(0.002, energy_ratio * 0.5)
    soft_threshold = max(energy_floor * 1.5, max_rms * soft_ratio)
    soft_mask = rms >= soft_threshold if rms.size else np.zeros_like(speech_mask)
    min_energy_frames = max(1, int(cfg.get("vad_min_energy_frames", 3)))
    if soft_mask.any():
        soft_mask = _drop_short_runs(soft_mask, min_energy_frames)

    combined_mask = speech_mask | energy_mask | soft_mask
    if not combined_mask.any():
        debug("VAD+energy found no speech; returning original audio")
        return mono

    extra_frames = int(np.count_nonzero(energy_mask & ~speech_mask))
    if extra_frames:
        debug(
            "Energy boost added %d frames to VAD (threshold %.4f)"
            % (extra_frames, energy_threshold)
        )

    soft_extra = int(np.count_nonzero(soft_mask & ~(speech_mask | energy_mask)))
    if soft_extra:
        debug(
            "Soft energy added %d frames to VAD (threshold %.4f)"
            % (soft_extra, soft_threshold)
        )

    bridge_ms = int(cfg.get("vad_bridge_ms", 120))
    bridge_ms = max(0, bridge_ms)
    bridge_frames = int(round(bridge_ms / frame_ms)) if bridge_ms else 0
    if bridge_frames > 0:
        # Convolve with a flat kernel so short gaps between voiced frames stay intact.
        kernel = np.ones(bridge_frames * 2 + 1, dtype=int)
        combined_mask = np.convolve(combined_mask.astype(int), kernel, mode="same") > 0

    if min_energy_frames > 1:
        combined_mask = _drop_short_runs(combined_mask, min_energy_frames)

    voiced_indices = np.flatnonzero(combined_mask)
    padding_ms = int(cfg.get("vad_padding_ms", 200))
    padding_ms = max(0, padding_ms)
    padding_frames = max(1, int(round(padding_ms / frame_ms)))

    remainder_flat = remainder.reshape(-1)
    remainder_rms = (
        float(
            np.sqrt(np.mean(np.square(remainder_flat.astype(np.float32) / 32767.0)))
        )
        if remainder_flat.size
        else 0.0
    )

    segments: List[Tuple[int, int]] = []
    segment_start = int(voiced_indices[0])
    prev_idx = int(voiced_indices[0])
    for raw_idx in voiced_indices[1:]:
        idx = int(raw_idx)
        if idx - prev_idx > 1:
            segments.append((segment_start, prev_idx))
            segment_start = idx
        prev_idx = idx
    segments.append((segment_start, prev_idx))

    segment_buffers: List[np.ndarray] = []
    tail_appended = False
    segment_durations: List[float] = []

    for seg_start, seg_end in segments:
        start_idx = max(0, seg_start - padding_frames)
        end_idx = min(total_frames, seg_end + padding_frames + 1)

        segment_frames = frames[start_idx:end_idx]
        if segment_frames.size == 0:
            continue

        segment_int = segment_frames.reshape(-1)
        if (
            not tail_appended
            and remainder_flat.size
            and end_idx >= total_frames
            and remainder_rms >= energy_floor
        ):
            segment_int = np.concatenate((segment_int, remainder_flat))
            tail_appended = True

        segment_buffers.append(segment_int)
        segment_durations.append(len(segment_int) / SAMPLE_RATE)

    if not segment_buffers:
        return mono

    processed_int = np.concatenate(segment_buffers)

    if len(segment_durations) > 1:
        durations_txt = ", ".join(f"{seconds:.2f}s" for seconds in segment_durations)
        debug(f"VAD kept {len(segment_durations)} segments: {durations_txt}")

    processed_pcm = processed_int.astype(np.float32) / 32767.0

    retained_ratio = processed_pcm.size / mono.size if mono.size else 1.0
    min_ratio = float(cfg.get("vad_min_output_ratio", 0.4))
    if retained_ratio < min_ratio:
        debug(
            "VAD output ratio %.2f below %.2f; using original audio"
            % (retained_ratio, min_ratio)
        )
        return mono

    return processed_pcm


def write_history(transcript: str, duration: float, word_count: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "language": cfg.get("language"),
        "text": transcript,
        "duration_seconds": round(duration, 3),
        "word_count": word_count,
    }
    try:
        with HIST_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[WARN] Failed to write history: {exc}", file=sys.stderr)


def transcribe_audio(audio: np.ndarray) -> None:
    if client is None or not state.get("client_ready"):
        if not state.get("client_warning_shown"):
            notify("OpenAI client not configured. Set OPENAI_API_KEY and restart.")
            print(
                "[WARN] Skipping transcription because the OpenAI client is not configured.",
                file=sys.stderr,
            )
            state["client_warning_shown"] = True
        return

    duration = audio.shape[0] / SAMPLE_RATE
    notify("Processing audio...")
    debug(f"Transcribing {duration:.2f}s of audio")
    processed = apply_vad(audio)
    input_samples = audio.shape[0] if audio.ndim >= 1 else audio.size
    input_seconds = input_samples / SAMPLE_RATE if input_samples else 0.0
    output_seconds = processed.size / SAMPLE_RATE if processed.size else 0.0
    saved_seconds = max(0.0, input_seconds - output_seconds)
    ratio = (output_seconds / input_seconds) if input_seconds else 1.0
    mode_label = "VAD" if cfg.get("use_vad") and VAD_AVAILABLE else "raw"
    debug(
        "%s throughput: input %.2fs → output %.2fs (saved %.2fs, ratio %.2f)"
        % (mode_label.upper(), input_seconds, output_seconds, saved_seconds, ratio)
    )
    if processed.size < int(SAMPLE_RATE * 0.25):
        debug("Transcription skipped: insufficient speech after VAD")
        notify("No speech detected, skipping transcription.")
        return
    pcm = np.clip(processed, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with wave.open(str(tmp_path), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm16.tobytes())
        with tmp_path.open("rb") as handle:
            response = client.audio.transcriptions.create(
                model=OPENAI_MODEL,
                file=handle,
                language=cfg.get("language") or "de",
                temperature=0.0,
            )
        transcript = response.text.strip()
        debug(f"Received transcript length: {len(transcript)}")
    except Exception as exc:
        notify(f"Transcription failed: {exc}")
        print(f"[ERROR] Transcription failed: {exc}", file=sys.stderr)
        return
    finally:
        with contextlib.suppress(Exception):
            tmp_path.unlink()
    if not transcript:
        notify("No transcript returned.")
        return
    word_count = len(transcript.split())
    debug(f"Word count: {word_count}")
    transcript_with_space = transcript + " "
    try:
        pyperclip.copy(transcript_with_space)
    except pyperclip.PyperclipException as exc:
        notify(f"Clipboard unavailable: {exc}")
        print(f"[WARN] Clipboard unavailable: {exc}", file=sys.stderr)
    if cfg.get("auto_paste_enabled"):
        try:
            perform_auto_paste(transcript_with_space)
        except Exception as exc:
            notify(f"Auto-paste failed: {exc}")
            print(f"[WARN] Auto-paste failed: {exc}", file=sys.stderr)
    write_history(transcript, duration, word_count)
    summary = transcript if len(transcript) <= 80 else transcript[:77] + "..."
    notify(f"Transcript copied ({duration:.1f}s, {word_count} words): {summary}")
    print(f"[TRANSCRIPT] ({duration:.2f}s, {word_count} words) {transcript}")


def set_language(language: str) -> None:
    if language not in {"de", "en"}:
        return
    cfg["language"] = language
    save_config()
    notify(f"Language set to {language}.")
    refresh_menu()


def set_device(name: str) -> None:
    cfg["device_name"] = name
    save_config()
    update_device_index()
    label = name or "System Default"
    notify(f"Input device set to {label}.")
    refresh_menu()


def toggle_notifications(*_args) -> None:
    cfg["notifications_enabled"] = not cfg.get("notifications_enabled", True)
    save_config()
    notify_state = "on" if cfg["notifications_enabled"] else "off"
    if cfg["notifications_enabled"]:
        notify(f"Notifications {notify_state}.")
    refresh_menu()


def toggle_auto_paste(*_args) -> None:
    cfg["auto_paste_enabled"] = not cfg.get("auto_paste_enabled", False)
    save_config()
    state_txt = "enabled" if cfg["auto_paste_enabled"] else "disabled"
    notify(f"Auto-paste {state_txt}.")
    if cfg.get("auto_paste_enabled"):
        state["wayland_notice_shown"] = False
    if cfg.get("auto_paste_enabled") and is_wayland_session() and not state.get("wayland_notice_shown"):
        notify("Wayland session detected: auto-paste will remain clipboard-only.")
    refresh_menu()


def set_paste_sequence(seq: str) -> None:
    if seq not in PASTE_OPTIONS:
        return
    cfg["paste_sequence"] = seq
    save_config()
    notify(f"Paste sequence set to {PASTE_OPTIONS[seq]}.")
    refresh_menu()


def toggle_vad(*_args) -> None:
    if not VAD_AVAILABLE:
        notify("WebRTC VAD not installed.")
        return
    cfg["use_vad"] = not cfg.get("use_vad", False)
    save_config()
    state_txt = "enabled" if cfg["use_vad"] else "disabled"
    notify(f"VAD {state_txt}.")
    refresh_menu()


def capture_hotkey(
    on_complete: Optional[Callable[[str, str], None]] = None,
    notify_user: bool = True,
    *_args,
) -> None:
    """Capture the next keypress globally and store it as hotkey."""
    global capture_listener

    if capture_listener:
        with contextlib.suppress(Exception):
            capture_listener.stop()
        capture_listener = None

    if notify_user:
        notify("Press a key for the new hotkey...")

    capture_modifiers: Set[str] = set()
    capture_done = {"value": False}
    state["hotkey_capture_active"] = True

    def finalize_hotkey(token: Optional[str]) -> None:
        if capture_done["value"] or not token:
            return
        capture_done["value"] = True
        update_hotkey_binding(set(capture_modifiers), token, notify_change=notify_user)
        state["hotkey_capture_active"] = False

        if on_complete:
            config_value = cfg.get("hotkey", "")
            label = hotkey_to_label(HOTKEY_KEY)

            def _fire_callback() -> bool:
                on_complete(config_value, label)
                return False

            if GLib is not None:
                GLib.idle_add(_fire_callback)
            else:
                on_complete(config_value, label)

        global capture_listener
        with contextlib.suppress(Exception):
            if capture_listener:
                capture_listener.stop()
        capture_listener = None

    def _on_press(key):
        mod = modifier_name(key)
        if mod:
            capture_modifiers.add(mod)
            return
        token = event_to_token(key)
        if token:
            finalize_hotkey(token)

    def _on_release(key):
        mod = modifier_name(key)
        if mod:
            capture_modifiers.discard(mod)
        if capture_done["value"]:
            state["hotkey_capture_active"] = False

    capture_listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    capture_listener.daemon = True
    capture_listener.start()


def update_hotkey_binding(modifiers: Set[str], token: str, notify_change: bool = True) -> None:
    global HOTKEY_KEY
    normalized_token = normalize_key_token(token) or "F9"
    valid_mods = {mod for mod in modifiers if mod in MODIFIER_MAP}
    HOTKEY_KEY = (frozenset(valid_mods), normalized_token)
    cfg["hotkey"] = hotkey_to_config(HOTKEY_KEY)
    save_config()
    if notify_change:
        notify(f"Hotkey set to {hotkey_to_label(HOTKEY_KEY)}.")
    start_hotkey_listener()
    refresh_menu()


def open_history(*_args) -> None:
    ensure_directories()
    try:
        subprocess.Popen(["xdg-open", str(HIST_FILE)])
    except Exception as exc:
        notify(f"Failed to open history: {exc}")


def open_config(*_args) -> None:
    ensure_directories()
    if not CONFIG_PATH.exists():
        save_config()
    try:
        subprocess.Popen(["xdg-open", str(CONFIG_PATH)])
    except Exception as exc:
        notify(f"Failed to open config: {exc}")


def open_settings_window(*_args) -> None:
    global settings_window
    try:
        from gi.repository import Gtk, GLib
    except Exception as exc:
        notify("GTK unavailable: opening config file instead.")
        print(f"[WARN] Settings window unavailable: {exc}", file=sys.stderr)
        open_config()
        return

    if settings_window is not None:
        GLib.idle_add(lambda: settings_window.present() or False)
        return

    def _present_settings() -> bool:
        global settings_window
        if settings_window is not None:
            settings_window.present()
            return False

        devices = list_input_devices()
        device_map = {"__default__": None}

        window = Gtk.Window(title=f"{APP_NAME} Settings")
        window.set_default_size(420, 360)
        window.set_position(Gtk.WindowPosition.CENTER)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_border_width(12)
        window.add(content)

        header = Gtk.Label(label=f"Session: {session_status_label()}")
        header.set_xalign(0.0)
        content.pack_start(header, False, False, 0)

        backend_label = Gtk.Label(label=f"Tray backend: {tray_backend_label()}")
        backend_label.set_xalign(0.0)
        content.pack_start(backend_label, False, False, 0)

        def make_row(
            label_text: str,
            widget: Gtk.Widget,
            tooltip: Optional[str] = None,
            expand: bool = False,
            defaults_text: Optional[str] = None,
        ) -> Gtk.Box:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            lbl = Gtk.Label(label=label_text)
            lbl.set_xalign(0.0)
            label_box.pack_start(lbl, False, False, 0)
            if tooltip:
                try:
                    info_icon = Gtk.Image.new_from_icon_name("dialog-information", Gtk.IconSize.SMALL_TOOLBAR)
                except Exception:
                    info_icon = Gtk.Label(label="i")
                info_icon.set_tooltip_text(tooltip)
                label_box.pack_start(info_icon, False, False, 0)
            if defaults_text:
                defaults_lbl = Gtk.Label(label=defaults_text)
                defaults_lbl.get_style_context().add_class("dim-label")
                defaults_lbl.set_xalign(0.0)
                label_box.pack_start(defaults_lbl, False, False, 0)
            row.pack_start(label_box, True, True, 0)
            row.pack_start(widget, expand, expand, 0)
            return row

        language_combo = Gtk.ComboBoxText()
        language_combo.append("de", "Deutsch (de)")
        language_combo.append("en", "English (en)")
        active_lang = cfg.get("language", "de")
        if active_lang not in {"de", "en"}:
            active_lang = "de"
        language_combo.set_active_id(active_lang)
        content.pack_start(make_row("Language", language_combo), False, False, 0)

        device_combo = Gtk.ComboBoxText()
        device_combo.append("__default__", "System Default")
        active_device_id = "__default__"
        saved_name = cfg.get("device_name")
        for device in devices:
            device_id = str(device.get("index"))
            device_name = device.get("name") or f"Device {device_id}"
            device_map[device_id] = device_name
            device_combo.append(device_id, device_name)
            if saved_name and device_name.lower() == saved_name.lower():
                active_device_id = device_id
        device_combo.set_active_id(active_device_id)
        content.pack_start(make_row("Input Device", device_combo), False, False, 0)

        paste_combo = Gtk.ComboBoxText()
        for key, label in PASTE_OPTIONS.items():
            paste_combo.append(key, label)
        paste_combo.set_active_id(cfg.get("paste_sequence", "auto"))
        if is_wayland_session():
            paste_combo.set_sensitive(False)
        paste_tooltip = "Select the key sequence used when auto paste runs. 'Auto' chooses based on the active window."
        content.pack_start(make_row("Paste Mode", paste_combo, tooltip=paste_tooltip), False, False, 0)

        hotkey_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hotkey_value = Gtk.Label(label=key_to_label(HOTKEY_KEY))
        hotkey_value.set_xalign(0.0)
        hotkey_box.pack_start(hotkey_value, False, False, 0)

        change_hotkey_button = Gtk.Button(label="Change...")
        reset_hotkey_button = Gtk.Button(label="Reset")
        hotkey_box.pack_start(change_hotkey_button, False, False, 0)
        hotkey_box.pack_start(reset_hotkey_button, False, False, 0)
        hotkey_tooltip = "Global shortcut to start/stop recording (supports modifiers like Ctrl+Alt+F9)."
        content.pack_start(make_row("Hotkey", hotkey_box, tooltip=hotkey_tooltip), False, False, 0)

        capture_state = {"active": False}

        def finish_hotkey_capture(_config_str: str, label: str) -> None:
            capture_state["active"] = False
            hotkey_value.set_text(label)
            change_hotkey_button.set_label("Change...")
            change_hotkey_button.set_sensitive(True)
            reset_hotkey_button.set_sensitive(True)

        def begin_hotkey_capture(_button) -> None:
            if capture_state["active"]:
                return
            capture_state["active"] = True
            hotkey_value.set_text("Press new key...")
            change_hotkey_button.set_label("Listening...")
            change_hotkey_button.set_sensitive(False)
            reset_hotkey_button.set_sensitive(False)
            try:
                capture_hotkey(on_complete=finish_hotkey_capture, notify_user=False)
            except Exception as exc:
                capture_state["active"] = False
                state["hotkey_capture_active"] = False
                hotkey_value.set_text(key_to_label(HOTKEY_KEY))
                change_hotkey_button.set_label("Change...")
                change_hotkey_button.set_sensitive(True)
                reset_hotkey_button.set_sensitive(True)
                debug(f"Hotkey capture failed: {exc}")

        def reset_hotkey(_button) -> None:
            capture_state["active"] = False
            update_hotkey_binding(set(), "F9")
            hotkey_value.set_text(key_to_label(HOTKEY_KEY))
            change_hotkey_button.set_label("Change...")
            change_hotkey_button.set_sensitive(True)
            reset_hotkey_button.set_sensitive(True)

        change_hotkey_button.connect("clicked", begin_hotkey_capture)
        reset_hotkey_button.connect("clicked", reset_hotkey)

        def build_switch(label_text: str, active: bool, tooltip: Optional[str] = None) -> Gtk.Box:
            switch = Gtk.Switch()
            switch.set_active(active)
            if tooltip:
                switch.set_tooltip_text(tooltip)
            row = make_row(label_text, switch, tooltip=tooltip)
            return row, switch

        notify_row, notify_switch = build_switch(
            "Notifications",
            cfg.get("notifications_enabled", True),
        )
        content.pack_start(notify_row, False, False, 0)

        auto_tooltip = "Paste transcripts automatically after copying them to the clipboard."
        if is_wayland_session():
            auto_tooltip += " Wayland restricts auto paste to clipboard-only."
        auto_row, auto_switch = build_switch(
            "Auto Paste",
            cfg.get("auto_paste_enabled", False),
            auto_tooltip,
        )
        content.pack_start(auto_row, False, False, 0)

        vad_label = "Voice Activity Detection"
        if VAD_AVAILABLE:
            vad_tooltip = "Trim silence around speech to reduce processing time and API usage."
        else:
            vad_tooltip = "Install the 'webrtcvad' package to enable silence trimming."
        vad_row, vad_switch = build_switch(
            vad_label,
            cfg.get("use_vad", False) and VAD_AVAILABLE,
            vad_tooltip,
        )
        vad_switch.set_sensitive(VAD_AVAILABLE)
        content.pack_start(vad_row, False, False, 0)

        vad_controls: List[Gtk.Widget] = []

        vad_sensitivity = float(cfg.get("vad_energy_ratio", 0.02) or 0.02)
        vad_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.01,
            0.2,
            0.005,
        )
        vad_scale.set_digits(3)
        vad_scale.set_value(max(0.01, min(0.2, vad_sensitivity)))
        vad_scale.set_draw_value(True)
        vad_scale.set_value_pos(Gtk.PositionType.RIGHT)
        vad_scale.set_hexpand(True)
        vad_scale.set_tooltip_text(
            "Slide left to keep more quiet speech; slide right to trim silence more aggressively. Recommended baseline: 0.02."
        )
        vad_controls.append(vad_scale)
        sensitivity_row = make_row(
            "VAD Sensitivity",
            vad_scale,
            tooltip="Slide left to keep more quiet speech; slide right to trim silence more aggressively.",
            expand=True,
            defaults_text="(Default 0.02)",
        )
        content.pack_start(sensitivity_row, False, False, 0)

        bridge_default = int(cfg.get("vad_bridge_ms", 180) or 180)
        bridge_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.0,
            400.0,
            10.0,
        )
        bridge_scale.set_digits(0)
        bridge_scale.set_value(max(0.0, min(400.0, float(bridge_default))))
        bridge_scale.set_draw_value(True)
        bridge_scale.set_value_pos(Gtk.PositionType.RIGHT)
        bridge_scale.set_hexpand(True)
        bridge_scale.set_tooltip_text(
            "Slide left to split after shorter pauses; slide right to keep longer gaps in the same segment. Recommended baseline: 180 ms."
        )
        vad_controls.append(bridge_scale)
        bridge_row = make_row(
            "Pause Bridging (ms)",
            bridge_scale,
            tooltip="Slide left to split after shorter pauses; slide right to keep longer gaps in the same segment.",
            expand=True,
            defaults_text="(Default 180)",
        )
        content.pack_start(bridge_row, False, False, 0)

        min_frames_default = int(cfg.get("vad_min_energy_frames", 2) or 2)
        frames_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            1.0,
            8.0,
            1.0,
        )
        frames_scale.set_digits(0)
        frames_scale.set_value(max(1.0, min(8.0, float(min_frames_default))))
        frames_scale.set_draw_value(True)
        frames_scale.set_value_pos(Gtk.PositionType.RIGHT)
        frames_scale.set_hexpand(True)
        frames_scale.set_tooltip_text(
            "Slide left to allow very short bursts; slide right to require longer low-level speech. Recommended baseline: 2 frames."
        )
        vad_controls.append(frames_scale)
        frames_row = make_row(
            "Noise Guard (frames)",
            frames_scale,
            tooltip="Slide left to allow very short bursts; slide right to require longer low-level speech.",
            expand=True,
            defaults_text="(Default 2)",
        )
        content.pack_start(frames_row, False, False, 0)

        def sync_vad_controls(*_args) -> None:
            active = vad_switch.get_active() and VAD_AVAILABLE
            for control in vad_controls:
                control.set_sensitive(active)

        vad_switch.connect("notify::active", sync_vad_controls)
        sync_vad_controls()

        if is_wayland_session():
            wayland_hint = Gtk.Label(
                label="Wayland detected: auto paste uses the clipboard only."
            )
            wayland_hint.set_xalign(0.0)
            wayland_hint.get_style_context().add_class("dim-label")
            content.pack_start(wayland_hint, False, False, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)

        cancel_button = Gtk.Button(label="Cancel")
        save_button = Gtk.Button(label="Save")
        button_box.pack_start(cancel_button, False, False, 0)
        button_box.pack_start(save_button, False, False, 0)
        content.pack_end(button_box, False, False, 0)

        def close_window(*_args) -> None:
            global settings_window, capture_listener
            if settings_window is None:
                return
            window_ref = settings_window
            settings_window = None
            window_ref.destroy()
            capture_state["active"] = False
            state["hotkey_capture_active"] = False
            if capture_listener:
                with contextlib.suppress(Exception):
                    capture_listener.stop()
            capture_listener = None

        def on_cancel(_button) -> None:
            close_window()

        def on_save(_button) -> None:
            language = language_combo.get_active_id() or "de"
            cfg["language"] = language

            device_id = device_combo.get_active_id() or "__default__"
            cfg["device_name"] = device_map.get(device_id)

            cfg["paste_sequence"] = paste_combo.get_active_id() or "auto"

            cfg["notifications_enabled"] = notify_switch.get_active()
            cfg["auto_paste_enabled"] = auto_switch.get_active()
            cfg["use_vad"] = vad_switch.get_active() if VAD_AVAILABLE else False
            cfg["vad_energy_ratio"] = round(float(vad_scale.get_value()), 3)
            cfg["vad_bridge_ms"] = int(round(bridge_scale.get_value()))
            cfg["vad_min_energy_frames"] = int(round(frames_scale.get_value()))

            if cfg.get("auto_paste_enabled"):
                state["wayland_notice_shown"] = False

            save_config()
            update_device_index()
            refresh_menu()
            refresh_tray_indicator()
            if cfg.get("auto_paste_enabled") and is_wayland_session():
                notify("Wayland session: auto-paste remains clipboard-only.")
            notify("Settings saved.")
            close_window()

        cancel_button.connect("clicked", on_cancel)
        save_button.connect("clicked", on_save)
        window.connect("destroy", lambda *_: close_window())

        window.show_all()
        settings_window = window
        return False

    GLib.idle_add(_present_settings)


def open_diagnostics_window(first_run: bool = False) -> None:
    global diagnostics_window

    if Gtk is None:
        print("Diagnostics window requires GTK; falling back to CLI output.")
        run_diagnostics_cli()
        if first_run:
            mark_first_run_complete()
        return

    if diagnostics_window is not None:
        if GLib is not None:
            GLib.idle_add(lambda: diagnostics_window.present() or False)
        else:
            diagnostics_window.present()
        return

    def _present() -> bool:
        global diagnostics_window
        if diagnostics_window is not None:
            diagnostics_window.present()
            return False

        window = Gtk.Window(title="WhisprBar Diagnostics")
        window.set_default_size(540, 420)
        try:
            window.set_position(Gtk.WindowPosition.CENTER)
        except Exception:
            pass

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_border_width(12)
        window.add(content)

        title_label = Gtk.Label()
        if GLib is not None:
            title_label.set_markup("<b>Environment diagnostics</b>")
        else:
            title_label.set_text("Environment diagnostics")
        title_label.set_xalign(0.0)
        content.pack_start(title_label, False, False, 0)

        summary_label = Gtk.Label()
        summary_label.set_xalign(0.0)
        summary_label.set_line_wrap(True)
        summary_label.set_max_width_chars(70)
        content.pack_start(summary_label, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        try:
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        except Exception:
            pass
        content.pack_start(scroller, True, True, 0)

        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        results_box.set_hexpand(True)
        scroller.add(results_box)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.set_halign(Gtk.Align.END)
        content.pack_end(button_box, False, False, 0)

        rerun_button = Gtk.Button(label="Run again")
        close_label = "Done" if first_run else "Close"
        close_button = Gtk.Button(label=close_label)
        button_box.pack_start(rerun_button, False, False, 0)
        button_box.pack_start(close_button, False, False, 0)

        def populate() -> None:
            for child in list(results_box.get_children()):
                results_box.remove(child)

            results = collect_diagnostics()
            errors = sum(1 for item in results if item.status == STATUS_ERROR)
            warnings = sum(1 for item in results if item.status == STATUS_WARN)
            if errors:
                summary_label.set_text(f"{errors} error(s), {warnings} warning(s) detected.")
            elif warnings:
                summary_label.set_text(f"No errors detected. {warnings} warning(s) to review.")
            else:
                summary_label.set_text("All checks passed.")

            for res in results:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.set_hexpand(True)

                icon_name = STATUS_ICON_NAME.get(res.status, "dialog-information")
                try:
                    icon_widget = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
                except Exception:
                    icon_widget = Gtk.Label(label=CLI_STATUS_LABEL.get(res.status, res.status.upper()))
                icon_widget.set_valign(Gtk.Align.START)
                row.pack_start(icon_widget, False, False, 0)

                text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                text_box.set_hexpand(True)

                label_text = res.label
                if GLib is not None:
                    safe_label = GLib.markup_escape_text(label_text)
                    title = Gtk.Label()
                    title.set_markup(f"<b>{safe_label}</b>")
                else:
                    title = Gtk.Label(label=label_text)
                title.set_xalign(0.0)
                text_box.pack_start(title, False, False, 0)

                detail = Gtk.Label(label=res.detail)
                detail.set_xalign(0.0)
                detail.set_line_wrap(True)
                detail.set_max_width_chars(90)
                text_box.pack_start(detail, False, False, 0)

                if res.remedy:
                    remedy_text = f"Fix: {res.remedy}"
                    if GLib is not None:
                        safe_fix = GLib.markup_escape_text(remedy_text)
                        remedy = Gtk.Label()
                        remedy.set_markup(f"<span size='small'>{safe_fix}</span>")
                    else:
                        remedy = Gtk.Label(label=remedy_text)
                    remedy.set_xalign(0.0)
                    remedy.set_line_wrap(True)
                    remedy.set_max_width_chars(90)
                    try:
                        remedy.get_style_context().add_class("dim-label")
                    except Exception:
                        pass
                    text_box.pack_start(remedy, False, False, 0)

                row.pack_start(text_box, True, True, 0)
                results_box.pack_start(row, False, False, 0)

            results_box.show_all()

        populate()

        rerun_button.connect("clicked", lambda *_: populate())
        close_button.connect("clicked", lambda *_: window.destroy())

        def on_destroy(*_args) -> None:
            global diagnostics_window
            diagnostics_window = None
            if first_run:
                mark_first_run_complete()

        window.connect("destroy", on_destroy)

        diagnostics_window = window
        window.show_all()
        return False

    if GLib is not None:
        GLib.idle_add(_present)
    else:
        _present()


def build_menu() -> pystray.Menu:
    devices = list_input_devices()
    device_items = [
        pystray.MenuItem(
            dev["name"],
            menu_action(set_device, dev["name"]),
            checked=cfg_equals_checker("device_name", dev["name"]),
        )
        for dev in devices
    ] or [pystray.MenuItem("No input devices", None, enabled=False)]

    language_menu = pystray.Menu(
        pystray.MenuItem("Deutsch", menu_action(set_language, "de"), checked=cfg_equals_checker("language", "de")),
        pystray.MenuItem("English", menu_action(set_language, "en"), checked=cfg_equals_checker("language", "en")),
    )

    paste_menu = pystray.Menu(
        *[
            pystray.MenuItem(
                label,
                menu_action(set_paste_sequence, key),
                checked=cfg_equals_checker("paste_sequence", key),
            )
            for key, label in PASTE_OPTIONS.items()
        ]
    )

    return pystray.Menu(
        pystray.MenuItem(
            lambda: "Stop Recording" if state.get("recording") else "Start Recording",
            lambda *_: toggle_recording(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda: f"Session: {session_status_label()}", lambda *_: None, enabled=False),
        pystray.MenuItem(lambda: f"Tray: {tray_backend_label()}", lambda *_: None, enabled=False),
        pystray.MenuItem("Settings...", lambda *_: open_settings_window()),
        pystray.MenuItem("Diagnostics...", lambda *_: open_diagnostics_window()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Language", language_menu),
        pystray.MenuItem("Input Device", pystray.Menu(*device_items)),
        pystray.MenuItem(
            "Notifications",
            lambda *_: toggle_notifications(),
            checked=lambda _: cfg.get("notifications_enabled", True),
        ),
        pystray.MenuItem(
            "Auto Paste",
            lambda *_: toggle_auto_paste(),
            checked=lambda _: cfg.get("auto_paste_enabled", False),
        ),
        pystray.MenuItem("Paste Mode", paste_menu),
        pystray.MenuItem(
            "Voice Activity Detection",
            lambda *_: toggle_vad(),
            checked=lambda _: cfg.get("use_vad", False),
            enabled=VAD_AVAILABLE,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"Hotkey ({key_to_label(HOTKEY_KEY)})", lambda *_: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda *_: shutdown()),
    )


def build_appindicator_menu() -> "Gtk.Menu":
    if not APPINDICATOR_AVAILABLE:
        raise RuntimeError("AppIndicator backend unavailable")

    menu = Gtk.Menu()

    start_item = Gtk.MenuItem(label="Stop Recording" if state.get("recording") else "Start Recording")
    start_item.connect("activate", lambda *_: toggle_recording())
    menu.append(start_item)

    menu.append(Gtk.SeparatorMenuItem())

    session_item = Gtk.MenuItem(label=f"Session: {session_status_label()}")
    session_item.set_sensitive(False)
    menu.append(session_item)

    tray_item = Gtk.MenuItem(label=f"Tray: {tray_backend_label()}")
    tray_item.set_sensitive(False)
    menu.append(tray_item)

    hotkey_item = Gtk.MenuItem(label=f"Hotkey: {key_to_label(HOTKEY_KEY)}")
    hotkey_item.set_sensitive(False)
    menu.append(hotkey_item)

    diagnostics_item = Gtk.MenuItem(label="Diagnostics...")
    diagnostics_item.connect("activate", lambda *_: open_diagnostics_window())
    menu.append(diagnostics_item)

    menu.append(Gtk.SeparatorMenuItem())

    language_menu = Gtk.Menu()
    language_items = []
    for code, label in (("de", "Deutsch"), ("en", "English")):
        if not language_items:
            item = Gtk.RadioMenuItem.new_with_label(None, label)
        else:
            item = Gtk.RadioMenuItem.new_with_label(language_items[0].get_group(), label)
        item.set_active(cfg.get("language") == code)
        item.connect("toggled", lambda widget, lang=code: widget.get_active() and set_language(lang))
        language_menu.append(item)
        language_items.append(item)

    language_item = Gtk.MenuItem(label="Language")
    language_item.set_submenu(language_menu)

    device_menu = Gtk.Menu()
    device_items = []
    default_label = "System Default"
    default_item = Gtk.RadioMenuItem.new_with_label(None, default_label)
    default_item.set_active(cfg.get("device_name") in {None, ""})
    default_item.connect("toggled", lambda widget: widget.get_active() and set_device(None))
    device_menu.append(default_item)
    device_items.append(default_item)
    for dev in list_input_devices():
        name = dev.get("name") or f"Device {dev.get('index')}"
        item = Gtk.RadioMenuItem.new_with_label(device_items[0].get_group(), name)
        item.set_active((cfg.get("device_name") or "").lower() == name.lower())
        item.connect("toggled", lambda widget, dev_name=name: widget.get_active() and set_device(dev_name))
        device_menu.append(item)
        device_items.append(item)

    device_item = Gtk.MenuItem(label="Input Device")
    device_item.set_submenu(device_menu)

    notifications_item = Gtk.CheckMenuItem(label="Notifications")
    notifications_item.set_active(cfg.get("notifications_enabled", True))
    notifications_item.connect("toggled", lambda *_: toggle_notifications())

    auto_paste_item = Gtk.CheckMenuItem(label="Auto Paste")
    auto_paste_item.set_active(cfg.get("auto_paste_enabled", False))
    auto_paste_item.connect("toggled", lambda *_: toggle_auto_paste())

    paste_menu = Gtk.Menu()
    paste_items = []
    for key, label in PASTE_OPTIONS.items():
        if not paste_items:
            item = Gtk.RadioMenuItem.new_with_label(None, label)
        else:
            item = Gtk.RadioMenuItem.new_with_label(paste_items[0].get_group(), label)
        item.set_active(cfg.get("paste_sequence", "auto") == key)
        item.set_sensitive(not (is_wayland_session() and key != "clipboard"))
        item.connect("toggled", lambda widget, seq=key: widget.get_active() and set_paste_sequence(seq))
        paste_menu.append(item)
        paste_items.append(item)

    paste_item = Gtk.MenuItem(label="Paste Mode")
    paste_item.set_submenu(paste_menu)

    vad_item = Gtk.CheckMenuItem(label="Voice Activity Detection")
    vad_item.set_active(cfg.get("use_vad", False) and VAD_AVAILABLE)
    vad_item.set_sensitive(VAD_AVAILABLE)
    vad_item.connect("toggled", lambda *_: toggle_vad())

    menu.append(language_item)
    menu.append(device_item)
    menu.append(notifications_item)
    menu.append(auto_paste_item)
    menu.append(paste_item)
    menu.append(vad_item)

    menu.append(Gtk.SeparatorMenuItem())

    settings_item = Gtk.MenuItem(label="Settings...")
    settings_item.connect("activate", lambda *_: open_settings_window())
    menu.append(settings_item)

    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", lambda *_: shutdown())
    menu.append(quit_item)

    return menu


def start_pystray_tray() -> Callable[[], None]:
    global icon, icon_ready
    icon_ready = False
    tray_menu = build_menu()
    icon = pystray.Icon(APP_NAME, icon_images["ready"], menu=tray_menu)
    state["tray_backend"] = os.environ.get("PYSTRAY_BACKEND", state.get("tray_backend") or "auto")

    if not hasattr(icon, "_menu_handle"):
        icon._menu_handle = None  # type: ignore[attr-defined]

    def _setup(_icon):
        global icon_ready
        icon_ready = True
        refresh_tray_indicator()
        refresh_menu()

    def _run_loop() -> None:
        icon.run(setup=_setup)

    return _run_loop


def start_appindicator_tray() -> Callable[[], None]:
    if not APPINDICATOR_AVAILABLE:
        raise RuntimeError("AppIndicator backend unavailable")
    ensure_directories()
    if not icon_files:
        raise RuntimeError("Icon files missing")
    if Gtk is not None:
        try:
            Gtk.init([])
        except Exception:
            pass
    global indicator, gtk_loop
    indicator_id = f"aa-{APP_NAME.lower()}"
    indicator = AppIndicator3.Indicator.new(indicator_id, str(icon_files["ready"]), AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
    indicator.set_icon_full(str(icon_files["ready"]), "Ready")
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    try:
        indicator.set_property("ordering-index", 0)
    except Exception as exc:
        debug(f"Ordering hint unsupported: {exc}")
    menu = build_appindicator_menu()
    menu.show_all()
    indicator.set_menu(menu)
    indicator.set_label(f"{APP_NAME} - Ready", APP_NAME)
    gtk_loop = GLib.MainLoop()

    def _run_loop() -> None:
        gtk_loop.run()

    return _run_loop

def shutdown(*_args) -> None:
    stop_recording()
    if hotkey_listener:
        with contextlib.suppress(Exception):
            hotkey_listener.stop()
    if capture_listener:
        with contextlib.suppress(Exception):
            capture_listener.stop()
    if settings_window:
        with contextlib.suppress(Exception):
            settings_window.destroy()
    global icon_ready
    if state.get("tray_backend") == "appindicator":
        global indicator, gtk_loop
        if indicator is not None:
            with contextlib.suppress(Exception):
                indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
        if gtk_loop is not None and gtk_loop.is_running():
            gtk_loop.quit()
        indicator = None
    else:
        if icon and icon_ready:
            icon.stop()
    icon_ready = False


def install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WhisprBar")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run environment diagnostics and exit",
    )
    return parser.parse_args(argv)


def main() -> None:
    global HOTKEY_KEY, icon
    load_config()
    check_runtime_dependencies()
    maybe_show_first_run_diagnostics()
    client_ready = prepare_openai_client()
    if not client_ready:
        debug("OpenAI client not initialised; transcription disabled until key is configured.")
    check_for_updates_async()
    HOTKEY_KEY = parse_hotkey(cfg.get("hotkey"))
    if is_wayland_session():
        debug("Wayland session detected. Auto-paste limited to clipboard-only mode.")
        print("[INFO] Wayland session detected. Auto-paste limited to clipboard-only mode.")
        if cfg.get("auto_paste_enabled") and not state.get("wayland_notice_shown"):
            notify("Wayland session detected: auto-paste is clipboard-only.")
            if cfg.get("notifications_enabled"):
                state["wayland_notice_shown"] = True
    print(f"[INFO] Tray backend in use: {tray_backend_label()}")
    update_device_index()
    start_hotkey_listener()
    install_signal_handlers()
    icon_images["ready"] = build_icon(accent_color=(255, 255, 255, 255))
    icon_images["recording"] = build_icon(accent_color=(220, 32, 32, 255))
    store_icon("ready", icon_images["ready"])
    store_icon("recording", icon_images["recording"])

    loop_runner: Callable[[], None]
    if state.get("tray_backend") == "appindicator" and APPINDICATOR_AVAILABLE:
        try:
            loop_runner = start_appindicator_tray()
        except Exception as exc:
            print(f"[WARN] AppIndicator startup failed: {exc}")
            state["tray_backend"] = "gtk"
            os.environ["PYSTRAY_BACKEND"] = "gtk"
            loop_runner = start_pystray_tray()
    else:
        loop_runner = start_pystray_tray()

    try:
        loop_runner()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    cli_args = parse_args(sys.argv[1:])
    if cli_args.diagnose:
        load_config()
        sys.exit(run_diagnostics_cli())
    main()
