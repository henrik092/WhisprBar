"""Auto-paste functionality for WhisprBar.

Handles automatic pasting of transcribed text using platform-specific methods:
- X11: xdotool or pynput keypresses (Ctrl+V, Ctrl+Shift+V, Shift+Insert)
- Wayland: Clipboard-only (requires manual paste)
- Cross-platform: Type simulation using pynput
"""

import os
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Any

import pyperclip
from pynput import keyboard

from .config import cfg
from .utils import debug, detect_session_type, notify

# Paste sequence options
PASTE_OPTIONS = {
    "auto": "Auto Detect",
    "ctrl_v": "Ctrl+V",
    "ctrl_shift_v": "Ctrl+Shift+V",
    "shift_insert": "Shift+Insert",
    "type": "Type Simulation",
    "clipboard": "Clipboard Only",
}

# Terminal keywords for auto-detection
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

# Timeout for window detection
PASTE_DETECT_TIMEOUT = float(os.environ.get("WHISPRBAR_PASTE_DETECT_TIMEOUT", "0.35"))

# Auto-paste detection cache
_AUTO_PASTE_CACHE: Dict[str, Any] = {"sequence": "ctrl_v", "timestamp": 0.0}

# Keyboard controller for simulating key presses
_controller = keyboard.Controller()


def is_wayland_session() -> bool:
    """Check if current session is Wayland.

    Returns:
        True if Wayland session, False otherwise
    """
    return detect_session_type() == "wayland"


def press_key(key_obj) -> None:
    """Press and release a key.

    Args:
        key_obj: keyboard.Key or string character
    """
    _controller.press(key_obj)
    _controller.release(key_obj)


def get_paste_delay_seconds() -> float:
    """Get configured paste delay in seconds.

    Returns:
        Delay in seconds (0-5 seconds, clamped)
    """
    try:
        delay_ms = int(cfg.get("paste_delay_ms", 0) or 0)
    except (ValueError, TypeError):
        delay_ms = 0
    # Safety: cap at 5 seconds
    return max(0, min(5000, delay_ms)) / 1000.0


def _run_paste_command(args: List[str]) -> subprocess.CompletedProcess:
    """Run a command for paste detection with timeout.

    Args:
        args: Command arguments

    Returns:
        CompletedProcess result
    """
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=PASTE_DETECT_TIMEOUT,
        check=False,
    )


def _detect_auto_paste_sequence_blocking(xdotool: str) -> str:
    """Detect appropriate paste sequence for active window.

    Uses xdotool to identify the active window and determine if it's a
    terminal (which needs Ctrl+Shift+V) or regular app (Ctrl+V).

    Args:
        xdotool: Path to xdotool executable

    Returns:
        Paste sequence ("ctrl_v" or "ctrl_shift_v")
    """
    # Get active window ID
    try:
        focus = _run_paste_command([xdotool, "getactivewindow"])
    except subprocess.TimeoutExpired:
        debug("xdotool getactivewindow timed out")
        return "ctrl_v"
    except (subprocess.SubprocessError, OSError) as exc:
        debug(f"xdotool getactivewindow failed: {exc}")
        return "ctrl_v"

    if focus.returncode != 0:
        debug(f"xdotool getactivewindow exited with {focus.returncode}")
        return "ctrl_v"

    # Extract window ID
    try:
        win_id = focus.stdout.strip().splitlines()[-1].strip()
    except Exception:
        win_id = ""

    if not win_id or win_id.lower() in {"0x0", "0"}:
        return "ctrl_v"

    # Get window name
    try:
        name_proc = _run_paste_command([xdotool, "getwindowname", win_id])
    except subprocess.TimeoutExpired:
        debug("xdotool getwindowname timed out")
        name_proc = None
    except (subprocess.SubprocessError, OSError) as exc:
        debug(f"xdotool getwindowname failed: {exc}")
        name_proc = None

    name = (
        (name_proc.stdout if name_proc else "").strip().lower() if name_proc else ""
    )

    # Get window class using xprop
    class_name = ""
    xprop = shutil.which("xprop")
    if xprop:
        try:
            class_proc = _run_paste_command([xprop, "-id", win_id, "WM_CLASS"])
        except subprocess.TimeoutExpired:
            debug("xprop WM_CLASS timed out")
            class_proc = None
        except Exception as exc:
            debug(f"xprop class lookup failed: {exc}")
            class_proc = None

        if class_proc and class_proc.returncode == 0:
            class_name = class_proc.stdout.lower()

    debug(f"Focused window: class='{class_name}', name='{name}'")

    # Check if window is a terminal
    for keyword in TERMINAL_KEYWORDS:
        if keyword in class_name or keyword in name:
            debug(f"Terminal detected (keyword: {keyword}), using Ctrl+Shift+V")
            return "ctrl_shift_v"

    return "ctrl_v"


def detect_auto_paste_sequence() -> str:
    """Detect appropriate paste sequence for current environment.

    Checks session type (Wayland vs X11) and active window to determine
    the best paste method. Results are cached for performance.

    Returns:
        Paste sequence key (from PASTE_OPTIONS)
    """
    # Wayland always uses clipboard-only
    if is_wayland_session():
        debug("Wayland session detected, forcing clipboard-only auto paste")
        return "clipboard"

    # Check if xdotool is available
    xdotool = shutil.which("xdotool")
    if not xdotool:
        debug("xdotool unavailable, defaulting to ctrl+V")
        return "ctrl_v"

    # Run detection in thread with timeout
    result: Dict[str, str] = {}

    def _worker():
        result["sequence"] = _detect_auto_paste_sequence_blocking(xdotool)

    thread = threading.Thread(
        target=_worker, name="whisprbar-window-detect", daemon=True
    )
    thread.start()
    thread.join(timeout=PASTE_DETECT_TIMEOUT * 2)

    if thread.is_alive():
        debug("Window detection timed out; falling back to cached sequence")
        return _AUTO_PASTE_CACHE.get("sequence", "ctrl_v")

    # Update cache and return
    sequence = result.get("sequence") or "ctrl_v"
    _AUTO_PASTE_CACHE["sequence"] = sequence
    _AUTO_PASTE_CACHE["timestamp"] = time.time()
    debug(f"Detected paste sequence: {sequence}")
    return sequence


def simulate_typing(text: str, delay_ms: float = 10.0) -> None:
    """Simulate typing text character by character.

    Uses pynput to type the text. This is slower but works in most contexts.
    Adds small delays between characters to prevent apps from missing input.

    Args:
        text: Text to type
        delay_ms: Delay between characters in milliseconds (default: 10ms)
    """
    if not text:
        return

    debug(f"Simulating typing: {len(text)} characters with {delay_ms}ms delay")

    # Type character by character with small delays
    delay_seconds = delay_ms / 1000.0
    for char in text:
        _controller.type(char)
        if delay_seconds > 0:
            time.sleep(delay_seconds)


def perform_auto_paste(text: str) -> None:
    """Perform auto-paste of transcribed text.

    Chooses paste method based on configuration and environment:
    1. If paste_sequence is "auto", detects best method
    2. On Wayland, always uses clipboard-only
    3. On X11, tries xdotool first, falls back to pynput
    4. For "type" sequence, simulates typing

    Args:
        text: Text to paste
    """
    # Add space after text if configured (for continuous text flow)
    if cfg.get("auto_paste_add_space", True):
        text = text + " "

    # Copy text to clipboard first
    try:
        pyperclip.copy(text)
        debug(f"Copied {len(text)} chars to clipboard")
    except Exception as exc:
        debug(f"Failed to copy to clipboard: {exc}")
        notify(f"Failed to copy text to clipboard: {exc}")
        return

    # Get configured paste sequence
    sequence = cfg.get("paste_sequence", "auto")
    if sequence == "auto":
        sequence = detect_auto_paste_sequence()

    # Force clipboard-only on Wayland
    wayland_session = is_wayland_session()
    if wayland_session:
        sequence = "clipboard"

    debug(f"Auto paste sequence: {sequence}")

    # Handle clipboard-only mode
    if sequence == "clipboard":
        if wayland_session:
            notify("Text copied to clipboard. Press Ctrl+V to paste.", force=True)
        debug("Clipboard-only paste; skipping key injection")
        return

    # Handle type simulation
    if sequence == "type":
        delay = get_paste_delay_seconds()
        if delay:
            time.sleep(delay)
        simulate_typing(text)
        return

    # Apply configured delay before pasting
    delay = get_paste_delay_seconds()
    if delay:
        debug(f"Waiting {delay}s before paste")
        time.sleep(delay)

    # Try xdotool first (more reliable on X11)
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
                subprocess.run([xdotool, "key", target], check=True, timeout=2.0)
                debug(f"xdotool sent: {target}")
                return
            except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired) as exc:
                debug(f"xdotool failed ({exc}), falling back to pynput")

    # Fallback to pynput keyboard simulation
    if sequence == "ctrl_shift_v":
        with _controller.pressed(keyboard.Key.ctrl):
            with _controller.pressed(keyboard.Key.shift):
                press_key("v")
    elif sequence == "shift_insert":
        with _controller.pressed(keyboard.Key.shift):
            press_key(keyboard.Key.insert)
    else:
        # Default: Ctrl+V
        with _controller.pressed(keyboard.Key.ctrl):
            press_key("v")

    debug("Paste complete")


def get_paste_sequence_label(sequence: str) -> str:
    """Get human-readable label for paste sequence.

    Args:
        sequence: Paste sequence key

    Returns:
        Human-readable label
    """
    return PASTE_OPTIONS.get(sequence, sequence)
