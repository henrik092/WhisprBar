"""Utility functions for WhisprBar.

Provides shared functionality: icons, history logging, update checking,
platform detection, diagnostics, and audio feedback.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw

# Import constants from config module
from .config import DATA_DIR, HIST_FILE, CONFIG_PATH, cfg

# Application constants
APP_NAME = "WhisprBar"
APP_VERSION = "1.0.0"
GITHUB_REPO = os.environ.get("WHISPRBAR_GITHUB_REPO", "henrik092/whisprBar")
GITHUB_RELEASE_URL = os.environ.get(
    "WHISPRBAR_UPDATE_URL",
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
)
UPDATE_COMMAND = os.environ.get("WHISPRBAR_UPDATE_COMMAND", "git pull && ./install.sh")
UPDATE_CHECK_TIMEOUT = float(os.environ.get("WHISPRBAR_UPDATE_TIMEOUT", "5"))

# Diagnostic status constants
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

# Debug mode
DEBUG = bool(os.environ.get("WHISPRBAR_DEBUG")) or sys.stdout.isatty()


@dataclass
class DiagnosticResult:
    """Result from a diagnostic check.

    Attributes:
        key: Unique identifier for this check
        label: Human-readable label
        status: One of STATUS_OK, STATUS_WARN, STATUS_ERROR
        detail: Detailed description of the result
        remedy: Optional suggestion for fixing issues
    """

    key: str
    label: str
    status: str
    detail: str
    remedy: Optional[str] = None


def debug(message: str) -> None:
    """Print debug message if debug mode is enabled.

    Debug mode is enabled when WHISPRBAR_DEBUG=1 or running in a TTY.
    """
    if DEBUG:
        print(f"[DEBUG] {message}")


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


def build_icon(
    size: int = 64,
    accent_color=(255, 255, 255, 255),
    body_color=(0, 0, 0, 220),
    background_color=(64, 64, 64, 180),
    border_color=(255, 255, 255, 230),
) -> Image.Image:
    """Render a microphone icon with customizable colors.

    Creates a circular icon with a microphone glyph. The accent color
    indicates status (white=ready, green=recording, blue=transcribing).

    Args:
        size: Icon size in pixels (default 64)
        accent_color: RGBA tuple for status indicator
        body_color: RGBA tuple for microphone body
        background_color: RGBA tuple for circle background
        border_color: RGBA tuple for circle border

    Returns:
        PIL Image object
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Circular background
    padding = max(2, size // 16)
    bg_bounds = (padding, padding, size - padding, size - padding)
    border_width = max(1, size // 32)
    draw.ellipse(bg_bounds, fill=background_color, outline=border_color, width=border_width)

    # Microphone capsule
    draw.ellipse((22, 10, 42, 36), fill=body_color)
    # Stem and base
    draw.rectangle((30, 36, 34, 50), fill=body_color)
    draw.rectangle((24, 48, 40, 52), fill=body_color)
    # Status accent inside the capsule
    draw.ellipse((26, 14, 38, 32), fill=accent_color)
    return img


def build_notification_icon() -> Image.Image:
    """Build a simple icon for notifications.

    Returns:
        PIL Image object (64x64)
    """
    return build_icon(size=64)


def store_icon(name: str, image: Image.Image) -> Path:
    """Save icon to disk in the data directory.

    Args:
        name: Icon name (without extension)
        image: PIL Image to save

    Returns:
        Path to saved icon file
    """
    from .config import ensure_directories
    ensure_directories()
    path = DATA_DIR / f"{name}.png"
    image.save(path, format="PNG")
    return path


def _notify_backends(title: str, message: str) -> List[List[str]]:
    """Get list of available notification backends.

    Checks for notify-send, zenity, and kdialog in order of preference.

    Args:
        title: Notification title
        message: Notification message

    Returns:
        List of command arrays to try
    """
    commands: List[List[str]] = []
    if command_exists("notify-send"):
        commands.append(["notify-send", title, message])
    if command_exists("zenity"):
        commands.append([
            "zenity",
            "--notification",
            "--window-icon=info",
            "--text",
            f"{title}\n{message}",
        ])
    if command_exists("kdialog"):
        commands.append(["kdialog", "--passivepopup", message, "5", "--title", title])
    return commands


def notify(message: str, title: str = None, *, force: bool = False) -> None:
    """Show desktop notification.

    Tries notify-send, zenity, and kdialog in order. Falls back to stderr
    if no notification backend is available.

    Args:
        message: Notification message
        title: Notification title (defaults to APP_NAME)
        force: If True, ignore notifications_enabled config
    """
    from .config import cfg

    if title is None:
        title = APP_NAME

    if not force and not cfg.get("notifications_enabled", True):
        return

    delivered = False
    for command in _notify_backends(title, message):
        try:
            subprocess.Popen(command)
            delivered = True
            break
        except (subprocess.SubprocessError, OSError) as exc:
            debug(f"Notification backend failed ({command[0]}): {exc}")

    if not delivered:
        print(f"[NOTICE] {title}: {message}", file=sys.stderr)


def write_history(transcript: str, duration: float, word_count: int) -> None:
    """Append transcription to history log.

    Writes a JSONL entry to ~/.local/share/whisprbar/history.jsonl with
    timestamp, language, text, duration, and word count.

    Args:
        transcript: Transcribed text
        duration: Audio duration in seconds
        word_count: Number of words in transcript
    """
    from .config import cfg

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


def fetch_latest_release_tag() -> Optional[str]:
    """Fetch the latest release tag from GitHub.

    Queries the GitHub API for the latest release and extracts the version tag.

    Returns:
        Version string (e.g., "0.1.0") or None if fetch fails
    """
    try:
        req = urllib.request.Request(GITHUB_RELEASE_URL, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
            tag = data.get("tag_name", "")
            # Strip 'v' prefix if present
            return tag.lstrip("v") if tag else None
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        debug(f"Failed to fetch latest release: {exc}")
        return None


def is_newer_version(remote: str, local: str) -> bool:
    """Compare version strings.

    Args:
        remote: Remote version string (e.g., "0.2.0")
        local: Local version string (e.g., "0.1.0")

    Returns:
        True if remote is newer than local
    """
    try:
        remote_parts = tuple(int(x) for x in remote.split("."))
        local_parts = tuple(int(x) for x in local.split("."))
        return remote_parts > local_parts
    except (ValueError, AttributeError):
        return False


def _update_check_worker() -> None:
    """Background worker to check for updates.

    Fetches latest version from GitHub and shows notification if newer
    version is available.
    """
    from .config import cfg

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
        message = f"A newer version ({latest}) is available. Update via: {UPDATE_COMMAND}"
        debug(message)
        print(f"[INFO] {message}")
        # Notification would be called here, but that requires notify() from main
        # For now, just print


def check_for_updates_async() -> None:
    """Start background update check.

    Spawns a daemon thread to check for updates without blocking startup.
    """
    from .config import cfg

    if not cfg.get("check_updates", True):
        return
    threading.Thread(target=_update_check_worker, name="whisprbar-update-check", daemon=True).start()


def collect_diagnostics() -> List[DiagnosticResult]:
    """Collect diagnostic information about the system.

    Checks session type, config/history directories, and basic system
    capabilities. Returns a list of diagnostic results.

    Note: Some checks (audio devices, API key) are done elsewhere and
    can be added to this list by the caller.

    Returns:
        List of DiagnosticResult objects
    """
    from .config import ensure_directories, load_env_file_values, cfg

    ensure_directories()
    results: List[DiagnosticResult] = []
    env_values = load_env_file_values()

    # Session type check
    session = detect_session_type()
    if session == "wayland":
        results.append(
            DiagnosticResult(
                "session",
                "Session",
                STATUS_WARN,
                "Wayland – auto paste copies text only.",
                remedy="Use Ctrl+V manually after transcription or switch to an X11 session for full automation.",
            )
        )
    elif session == "x11":
        results.append(DiagnosticResult("session", "Session", STATUS_OK, "X11 – Auto-paste available"))
    else:
        results.append(
            DiagnosticResult(
                "session",
                "Session",
                STATUS_WARN,
                f"{session.capitalize()} – Unknown session type",
                remedy="Switch to an X11 or Wayland session for full functionality.",
            )
        )

    # Auto-paste capability (basic check)
    if session == "x11":
        has_xdotool = command_exists("xdotool")
        status = STATUS_OK if has_xdotool else STATUS_ERROR
        detail = "xdotool available" if has_xdotool else "xdotool missing"
        remedy = None if has_xdotool else "Install xdotool (e.g. sudo apt install xdotool)."
        results.append(DiagnosticResult("auto_paste", "Auto paste", status, detail, remedy=remedy))
    elif session == "wayland":
        has_wl = command_exists("wl-clipboard")
        detail = "Clipboard-only mode" if has_wl else "wl-clipboard missing"
        remedy = None if has_wl else "Install wl-clipboard (e.g. sudo apt install wl-clipboard)."
        status = STATUS_WARN if has_wl else STATUS_ERROR
        results.append(DiagnosticResult("auto_paste", "Auto paste", status, detail, remedy=remedy))

    # Notifications support
    notify_support = []
    if command_exists("notify-send"):
        notify_support.append("notify-send")
    if command_exists("zenity"):
        notify_support.append("zenity")
    if command_exists("kdialog"):
        notify_support.append("kdialog")

    if notify_support:
        detail = f"Available: {', '.join(notify_support)}"
        status = STATUS_OK
        remedy = None
        if "notify-send" not in notify_support:
            status = STATUS_WARN
            detail += " (using fallback)"
            remedy = "Install libnotify-bin for native notify-send support."
        results.append(DiagnosticResult("notifications", "Notifications", status, detail, remedy=remedy))
    else:
        results.append(
            DiagnosticResult(
                "notifications",
                "Notifications",
                STATUS_WARN,
                "No notification tools found",
                remedy="Install libnotify-bin (notify-send) or zenity for desktop alerts.",
            )
        )

    # API key check
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

    # Config directory
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

    # History storage
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

    return results


def ensure_directories() -> None:
    """Ensure all required directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HIST_FILE.touch(exist_ok=True)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def read_history(limit: int = 10) -> List[Dict[str, any]]:
    """Read recent transcription history.

    Args:
        limit: Maximum number of entries to return (default: 10)

    Returns:
        List of history entries (most recent first)
    """
    if not HIST_FILE.exists():
        return []

    entries = []
    try:
        with HIST_FILE.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        debug(f"Failed to read history: {exc}")
        return []

    # Return most recent first
    return list(reversed(entries[-limit:]))


def clear_history() -> None:
    """Clear all transcription history."""
    try:
        if HIST_FILE.exists():
            HIST_FILE.unlink()
        HIST_FILE.touch()
        debug("History cleared")
    except Exception as exc:
        debug(f"Failed to clear history: {exc}")


def format_history_entry(entry: Dict[str, any], max_length: int = 50) -> str:
    """Format history entry for display in menu.

    Args:
        entry: History entry dictionary
        max_length: Maximum text length before truncation

    Returns:
        Formatted string for menu display
    """
    text = entry.get("text", "").strip()
    if not text:
        return "(empty)"

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "..."

    # Replace newlines with spaces
    text = text.replace("\n", " ").replace("\r", "")

    return text


def play_audio_feedback(sound_type: str = "start") -> None:
    """Play audio feedback for recording events.

    Plays a system sound when recording starts or stops, if enabled in config.

    Args:
        sound_type: Type of sound ("start" or "stop")
    """
    if not cfg.get("audio_feedback_enabled", True):
        return

    volume = max(0.0, min(1.0, float(cfg.get("audio_feedback_volume", 0.3))))

    # Use system sounds via paplay (PulseAudio) or aplay (ALSA)
    # Prefer shorter, more subtle sounds for better UX
    sound_files = {
        "start": [
            "/usr/share/sounds/LinuxMint/stereo/button-toggle-on.ogg",
            "/usr/share/sounds/freedesktop/stereo/onboard-key-feedback.oga",
            "/usr/share/sounds/freedesktop/stereo/message.oga",
            "/usr/share/sounds/freedesktop/stereo/service-login.oga",
            "/usr/share/sounds/ubuntu/stereo/message.ogg",
        ],
        "stop": [
            "/usr/share/sounds/LinuxMint/stereo/button-toggle-off.ogg",
            "/usr/share/sounds/freedesktop/stereo/complete.oga",
            "/usr/share/sounds/freedesktop/stereo/service-logout.oga",
            "/usr/share/sounds/ubuntu/stereo/dialog-information.ogg",
        ],
    }

    # Find first available sound file
    sound_path = None
    for path in sound_files.get(sound_type, []):
        if os.path.exists(path):
            sound_path = path
            break

    if not sound_path:
        debug(f"No system sound file found for {sound_type}")
        return

    # Try paplay first (PulseAudio)
    if command_exists("paplay"):
        try:
            # paplay with volume control
            volume_percent = int(volume * 65536)  # paplay uses 0-65536 range
            subprocess.Popen(
                ["paplay", "--volume", str(volume_percent), sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            debug(f"Audio feedback: {sound_type} (volume: {volume:.1%})")
            return
        except Exception as exc:
            debug(f"paplay failed: {exc}")

    # Fallback to aplay (ALSA) - no volume control
    if command_exists("aplay"):
        try:
            subprocess.Popen(
                ["aplay", "-q", sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            debug(f"Audio feedback: {sound_type} (aplay, no volume control)")
            return
        except Exception as exc:
            debug(f"aplay failed: {exc}")

    debug("No audio playback command available (paplay/aplay)")
