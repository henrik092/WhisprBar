"""Platform detection utilities for WhisprBar.

Provides session type detection (X11/Wayland) and command availability checks.
These functions are extracted from utils.py for use by the platform package.
"""

import os
import shutil


def command_exists(name: str) -> bool:
    """Check if a system command is available.

    Args:
        name: Command name (e.g., "xdotool", "notify-send")

    Returns:
        True if command is found in PATH, False otherwise
    """
    return shutil.which(name) is not None


def detect_session_type() -> str:
    """Detect the current session type (X11, Wayland, or unknown).

    Checks XDG_SESSION_TYPE environment variable, falling back to
    WAYLAND_DISPLAY and DISPLAY.

    Returns:
        "x11", "wayland", or "unknown"
    """
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
