"""Configuration management for WhisprBar.

Handles loading, saving, and validating configuration from ~/.config/whisprbar.json
and environment variables from ~/.config/whisprbar.env.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict

# Configuration paths
CONFIG_PATH = Path.home() / ".config" / "whisprbar.json"
DATA_DIR = Path.home() / ".local" / "share" / "whisprbar"
HIST_FILE = DATA_DIR / "history.jsonl"

# Default configuration schema
DEFAULT_CFG = {
    "language": "de",
    "device_name": None,
    # Multiple hotkey support (new in V6.1)
    "hotkeys": {
        "toggle_recording": "F9",
        "start_recording": None,  # Optional dedicated start hotkey
        "stop_recording": None,  # Optional dedicated stop hotkey
        "open_settings": "F10",
        "show_history": None,  # Not assigned by default
        "cancel_recording": None,  # Not assigned (ESC is hardcoded)
    },
    # Legacy single hotkey (for backwards compatibility)
    "hotkey": "F9",
    "notifications_enabled": False,
    "auto_paste_enabled": True,
    "auto_paste_add_newline": True,  # Add newline after each transcription
    "auto_paste_add_space": True,  # Add trailing space after pasted text
    "paste_sequence": "auto",
    "paste_delay_ms": 250,
    "use_vad": True,  # Enabled by default for better quality
    "vad_energy_ratio": 0.05,  # Increased for better pause handling
    "vad_bridge_ms": 300,  # Increased to bridge natural speech pauses
    "vad_min_energy_frames": 2,
    "vad_auto_stop_enabled": False,  # Auto-stop recording after silence
    "vad_auto_stop_silence_seconds": 2.0,  # Silence duration to trigger auto-stop
    "vad_calibration_enabled": False,  # Measure ambient noise before recording
    "vad_energy_floor": 0.0005,  # Minimum energy threshold for VAD frame detection
    "vad_padding_ms": 200,  # Padding added around detected speech segments (ms)
    "vad_min_output_ratio": 0.4,  # Minimum output/input ratio to accept VAD result
    "vad_mode": 1,  # WebRTC VAD aggressiveness mode (0-3, higher = more aggressive)
    "chunking_enabled": True,  # Split long audio into chunks for faster processing
    "chunk_duration_seconds": 30.0,  # Duration of each chunk
    "chunk_overlap_seconds": 2.0,  # Overlap between chunks for smooth merging
    "chunking_threshold_seconds": 60.0,  # Min duration to trigger chunking
    "postprocess_enabled": True,  # Clean up transcription text
    "postprocess_fix_spacing": True,  # Remove double spaces and fix punctuation spacing
    "postprocess_fix_capitalization": True,  # Capitalize sentences and fix common errors
    "postprocess_fix_punctuation": False,  # Advanced punctuation correction (requires model)
    "noise_reduction_enabled": True,  # Reduce background noise before transcription
    "noise_reduction_strength": 0.7,  # Noise reduction strength (0.0-1.0)
    "live_overlay_enabled": False,  # Show live transcription overlay during processing
    "live_overlay_font_size": 14,  # Font size for overlay text
    "live_overlay_opacity": 0.9,  # Overlay window opacity (0.0-1.0)
    "live_overlay_width": 400,  # Overlay window width in pixels
    "live_overlay_height": 150,  # Overlay window height in pixels
    "live_overlay_display_duration": 2.0,  # How long to show overlay after completion (seconds)
    "live_overlay_x": None,  # X position of overlay (None = auto)
    "live_overlay_y": None,  # Y position of overlay (None = auto)
    "transcription_backend": "openai",  # Backend: openai, faster_whisper, streaming
    "faster_whisper_model": "medium",  # Model size: tiny, base, small, medium, large
    "faster_whisper_device": "cpu",  # Device: cpu, cuda, rocm
    "faster_whisper_compute_type": "int8",  # Compute type: int8, float16, float32
    "streaming_model": "tiny",  # sherpa-onnx model: tiny, base, small, medium
    "stop_tail_grace_ms": 500,
    "min_drain_timeout_ms": 100,  # Minimum drain timeout (100-500ms, default: 100ms for fast response)
    "first_run_complete": False,
    "check_updates": True,
    "theme_mode": "auto",  # Theme mode: auto, light, dark
    "theme_preference": "auto",  # User theme preference: auto, light, dark
    "audio_feedback_enabled": True,  # Play sounds on recording start/stop/completion
    "audio_feedback_volume": 0.3,  # Volume for audio feedback (0.0-1.0)
    "min_audio_energy": 0.0008,  # Minimum audio energy to prevent hallucinations (0.0001-0.01)
    "recording_indicator_enabled": True,  # Show animated recording indicator
    "recording_indicator_style": "soundwave",  # Currently only soundwave
    "recording_indicator_position": "top-center",  # Position: top-center, bottom-center, top-left, etc.
    "recording_indicator_scale": 1.0,        # 0.1 - 2.0 (1.0 = 240x30 base)
    "recording_indicator_opacity": 0.85,  # Opacity (0.0-1.0)
    "recording_indicator_x": None,           # Custom X position (for draggable)
    "recording_indicator_y": None,           # Custom Y position (for draggable)
}

# Global config instance (loaded from disk + defaults)
cfg = DEFAULT_CFG.copy()


def get_env_file_path() -> Path:
    """Get path to environment file (.env).

    Respects XDG_CONFIG_HOME if set, otherwise uses ~/.config/
    """
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "whisprbar.env"
    return Path.home() / ".config" / "whisprbar.env"


def load_env_file_values() -> Dict[str, str]:
    """Load environment variables from .env file.

    Returns:
        Dictionary of key=value pairs from the .env file.
        Lines starting with # are comments.
        Format: KEY=value or KEY="value" or KEY='value'
    """
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
        print(f"[WARN] Failed to read env file {env_path}: {exc}", file=sys.stderr)
    return values


def ensure_directories() -> None:
    """Ensure required directories and files exist.

    Creates:
    - ~/.local/share/whisprbar/ (data directory)
    - ~/.local/share/whisprbar/history.jsonl (history file)
    - ~/.config/ (parent for config file)
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HIST_FILE.touch(exist_ok=True)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def reset_config() -> None:
    """Reset config to defaults without breaking module references.

    This function clears cfg and repopulates it with DEFAULT_CFG values,
    preserving the dict object identity so all imported references remain valid.

    WARNING: Only use this for testing. In production, use load_config().
    """
    cfg.clear()
    cfg.update(DEFAULT_CFG.copy())
    if os.getenv("WHISPRBAR_DEBUG"):
        print(f"[DEBUG] Config reset to defaults ({len(cfg)} keys)", file=sys.stderr)


def migrate_legacy_hotkey() -> None:
    """Migrate legacy single hotkey to new hotkeys dictionary.

    If the config has a "hotkey" field but no "hotkeys" field, this migrates
    the single hotkey to the new format. This ensures backwards compatibility
    with configs from earlier versions.
    """
    # If hotkeys dict doesn't exist, create it
    if "hotkeys" not in cfg:
        cfg["hotkeys"] = DEFAULT_CFG["hotkeys"].copy()

    # If legacy hotkey exists and is different from default
    if "hotkey" in cfg:
        legacy_hotkey = cfg["hotkey"]
        if legacy_hotkey and legacy_hotkey != DEFAULT_CFG["hotkey"]:
            # Migrate to toggle_recording
            cfg["hotkeys"]["toggle_recording"] = legacy_hotkey
            if os.getenv("WHISPRBAR_DEBUG"):
                print(f"[DEBUG] Migrated legacy hotkey '{legacy_hotkey}' to toggle_recording", file=sys.stderr)

    # Keep legacy "hotkey" field in sync for backwards compatibility
    cfg["hotkey"] = cfg["hotkeys"]["toggle_recording"]

    # Ensure all default actions exist
    for action, default_value in DEFAULT_CFG["hotkeys"].items():
        if action not in cfg["hotkeys"]:
            cfg["hotkeys"][action] = default_value


def validate_config() -> None:
    """Validate and clamp config values to safe ranges.

    Modifies the global `cfg` dict in-place to ensure values are within
    acceptable bounds. Invalid values are clamped or reset to defaults.
    """
    # Clamp paste_delay_ms to prevent UI freezes
    if "paste_delay_ms" in cfg:
        try:
            delay = int(cfg["paste_delay_ms"])
            cfg["paste_delay_ms"] = max(0, min(5000, delay))
        except (ValueError, TypeError):
            cfg["paste_delay_ms"] = DEFAULT_CFG["paste_delay_ms"]

    # Clamp stop_tail_grace_ms to prevent long hangs
    if "stop_tail_grace_ms" in cfg:
        try:
            grace = int(cfg["stop_tail_grace_ms"])
            cfg["stop_tail_grace_ms"] = max(0, min(2000, grace))
        except (ValueError, TypeError):
            cfg["stop_tail_grace_ms"] = DEFAULT_CFG["stop_tail_grace_ms"]

    # Clamp VAD energy ratio
    if "vad_energy_ratio" in cfg:
        try:
            ratio = float(cfg["vad_energy_ratio"])
            cfg["vad_energy_ratio"] = max(0.002, min(0.3, ratio))
        except (ValueError, TypeError):
            cfg["vad_energy_ratio"] = DEFAULT_CFG["vad_energy_ratio"]

    # Clamp VAD bridge_ms
    if "vad_bridge_ms" in cfg:
        try:
            bridge = int(cfg["vad_bridge_ms"])
            cfg["vad_bridge_ms"] = max(0, min(1000, bridge))
        except (ValueError, TypeError):
            cfg["vad_bridge_ms"] = DEFAULT_CFG["vad_bridge_ms"]

    # Clamp vad_min_energy_frames
    if "vad_min_energy_frames" in cfg:
        try:
            frames = int(cfg["vad_min_energy_frames"])
            cfg["vad_min_energy_frames"] = max(1, min(10, frames))
        except (ValueError, TypeError):
            cfg["vad_min_energy_frames"] = DEFAULT_CFG["vad_min_energy_frames"]

    # Clamp vad_auto_stop_silence_seconds
    if "vad_auto_stop_silence_seconds" in cfg:
        try:
            seconds = float(cfg["vad_auto_stop_silence_seconds"])
            cfg["vad_auto_stop_silence_seconds"] = max(0.5, min(30.0, seconds))
        except (ValueError, TypeError):
            cfg["vad_auto_stop_silence_seconds"] = DEFAULT_CFG["vad_auto_stop_silence_seconds"]

    # Clamp min_drain_timeout_ms
    if "min_drain_timeout_ms" in cfg:
        try:
            timeout = int(cfg["min_drain_timeout_ms"])
            cfg["min_drain_timeout_ms"] = max(100, min(500, timeout))
        except (ValueError, TypeError):
            cfg["min_drain_timeout_ms"] = DEFAULT_CFG["min_drain_timeout_ms"]

    # Clamp audio feedback volume
    if "audio_feedback_volume" in cfg:
        try:
            volume = float(cfg["audio_feedback_volume"])
            cfg["audio_feedback_volume"] = max(0.0, min(1.0, volume))
        except (ValueError, TypeError):
            cfg["audio_feedback_volume"] = DEFAULT_CFG["audio_feedback_volume"]


def load_config() -> dict:
    """Load configuration from disk.

    Reads ~/.config/whisprbar.json and merges with DEFAULT_CFG.
    Updates the global `cfg` dict with loaded values.
    Missing keys use defaults, extra keys are preserved.

    IMPORTANT: This function modifies cfg in-place to preserve references
    across all modules that import cfg. Never reassign config.cfg directly.

    Returns:
        The global cfg dict (for convenience and explicit API)
    """
    ensure_directories()
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                file_cfg = json.load(handle)
            cfg.update(file_cfg)
            migrate_legacy_hotkey()  # Migrate old hotkey format
            validate_config()
            if os.getenv("WHISPRBAR_DEBUG"):
                print(f"[DEBUG] Config loaded: {len(cfg)} keys", file=sys.stderr)
    except (IOError, json.JSONDecodeError) as exc:
        print(f"[WARN] Failed to load config: {exc}", file=sys.stderr)

    return cfg


def save_config() -> None:
    """Save current configuration to disk.

    Writes the global `cfg` dict to ~/.config/whisprbar.json as JSON.
    """
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False, indent=2)
    except (IOError, TypeError) as exc:
        print(f"[WARN] Failed to write config: {exc}", file=sys.stderr)


def save_env_file_value(key: str, value: str) -> None:
    """Save or update a single key=value pair in the .env file.

    Args:
        key: Environment variable name (e.g., "OPENAI_API_KEY")
        value: Value to save (empty string removes the key)
    """
    env_path = get_env_file_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing values
    existing_values = load_env_file_values()

    # Update or remove the value
    if value and value.strip():
        existing_values[key] = value.strip()
    elif key in existing_values:
        del existing_values[key]

    # Write back to file
    try:
        with env_path.open("w", encoding="utf-8") as handle:
            handle.write("# WhisprBar environment variables\n")
            handle.write("# API keys and secrets\n\n")
            for env_key, env_value in existing_values.items():
                # Quote values with spaces
                if " " in env_value:
                    handle.write(f'{env_key}="{env_value}"\n')
                else:
                    handle.write(f'{env_key}={env_value}\n')

        # Set restrictive permissions (600 = rw-------)
        env_path.chmod(0o600)

        if os.getenv("WHISPRBAR_DEBUG"):
            print(f"[DEBUG] Saved {key} to {env_path}", file=sys.stderr)
    except Exception as exc:
        print(f"[WARN] Failed to save {key} to env file: {exc}", file=sys.stderr)


def get_env_value(key: str) -> str:
    """Get a value from the .env file.

    Args:
        key: Environment variable name

    Returns:
        Value from .env file, or empty string if not found
    """
    env_values = load_env_file_values()
    return env_values.get(key, "")
