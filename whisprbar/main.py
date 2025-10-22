#!/usr/bin/env python3
"""
whisprbar/main.py - Application orchestration and main entry point

This module coordinates all components and manages the application lifecycle.
"""

import sys
import os
import signal
import argparse
import threading
import contextlib
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import all whisprbar modules
from whisprbar import __version__
from whisprbar.config import load_config, save_config, cfg
from whisprbar.utils import (
    notify,
    check_for_updates_async,
    debug,
    detect_session_type,
    play_audio_feedback,
    APP_NAME,
)
from whisprbar.audio import (
    start_recording,
    stop_recording,
    update_device_index,
    get_recording_state,
)
from whisprbar.transcription import transcribe_audio, get_transcriber
from whisprbar.hotkeys import (
    start_hotkey_listener,
    stop_hotkey_listener,
    parse_hotkey,
    get_hotkey_manager,
)
from whisprbar.paste import is_wayland_session, PASTE_OPTIONS
from whisprbar.ui import (
    maybe_show_first_run_diagnostics,
    open_diagnostics_window,
    open_settings_window,
    _run_diagnostics_cli,
)
from whisprbar.tray import (
    select_tray_backend,
    start_pystray_tray,
    start_appindicator_tray,
    refresh_menu,
    refresh_tray_indicator,
    shutdown_tray,
    initialize_icons,
)

# Global application state
state: Dict[str, Any] = {
    "recording": False,
    "transcribing": False,
    "client_ready": False,
    "client_warning_shown": False,
    "session_type": "unknown",
    "tray_backend": "auto",
    "wayland_notice_shown": False,
    "hotkey_key": None,
    "hotkey_capture_active": False,
}

# PID file for singleton enforcement
PID_FILE = Path.home() / ".cache" / "whisprbar" / "whisprbar.pid"

# =============================================================================
# Stdin Management for pynput
# =============================================================================

def ensure_stdin_open() -> None:
    """
    Ensure stdin is open for pynput keyboard listener.

    CRITICAL FIX: pynput's X11 keyboard listener requires stdin to be open.
    When launched via desktop entries (Terminal=false), stdin is redirected to /dev/null,
    which breaks hotkey detection. This function reopens stdin from /dev/zero if needed.

    Background:
    - Desktop entries with Terminal=false close stdin before launching the app
    - systemd services also close stdin by default
    - pynput on X11 appears to require stdin to be readable (exact reason unclear)
    - Redirecting stdin from /dev/zero keeps it open without blocking

    This fix allows WhisprBar to work correctly when launched from:
    - Desktop entries (.desktop files)
    - systemd user services
    - Any other launcher that closes stdin
    """
    try:
        # ALWAYS reopen stdin from /dev/zero to be absolutely sure
        # This is the safest approach - better safe than sorry
        null_fd = os.open('/dev/zero', os.O_RDONLY)
        os.dup2(null_fd, 0)  # Replace stdin with /dev/zero
        os.close(null_fd)

        # Recreate stdin file object
        try:
            sys.stdin.close()
        except:
            pass
        sys.stdin = os.fdopen(0, 'r')

        # Print to stderr so it appears even before config is loaded
        print("[STDIN-FIX] Reopened stdin from /dev/zero for pynput hotkey compatibility", file=sys.stderr)
    except Exception as e:
        # If anything fails, print error to stderr
        print(f"[STDIN-FIX] ERROR: Could not reopen stdin: {e}", file=sys.stderr)

# =============================================================================
# Singleton Lock Management
# =============================================================================

def acquire_singleton_lock() -> bool:
    """
    Acquire singleton lock using PID file.

    Returns True if lock acquired successfully, False if another instance is running.
    If stale PID file exists (process not running), removes it and acquires lock.
    """
    # Ensure cache directory exists
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        # Read existing PID
        try:
            existing_pid = int(PID_FILE.read_text().strip())

            # Check if process is still running
            try:
                os.kill(existing_pid, 0)  # Signal 0 just checks if process exists
                # Process exists, another instance is running
                debug(f"WhisprBar is already running (PID {existing_pid})")
                return False
            except OSError:
                # Process doesn't exist, stale PID file
                debug(f"Removing stale PID file (PID {existing_pid} not running)")
                PID_FILE.unlink()
        except (ValueError, IOError) as exc:
            # Corrupted PID file, remove it
            debug(f"Removing corrupted PID file: {exc}")
            PID_FILE.unlink()

    # Write our PID
    PID_FILE.write_text(str(os.getpid()))
    debug(f"Singleton lock acquired (PID {os.getpid()})")
    return True


def release_singleton_lock() -> None:
    """Release singleton lock by removing PID file."""
    try:
        if PID_FILE.exists():
            # Verify it's our PID before removing
            current_pid = int(PID_FILE.read_text().strip())
            if current_pid == os.getpid():
                PID_FILE.unlink()
                debug("Singleton lock released")
    except Exception as exc:
        debug(f"Error releasing singleton lock: {exc}")


# =============================================================================
# Helper Functions
# =============================================================================

def session_status_label() -> str:
    """Get session type label for menu."""
    session_type = state.get("session_type", "unknown")
    if session_type == "wayland":
        return "Wayland"
    elif session_type == "x11":
        return "X11"
    else:
        return "Unknown"


def tray_backend_label() -> str:
    """Get tray backend label for menu."""
    backend = state.get("tray_backend", "auto")
    if backend == "appindicator":
        return "AppIndicator"
    elif backend == "gtk":
        return "PyStray GTK"
    elif backend == "xorg":
        return "PyStray Xorg"
    else:
        return "Auto"


def vad_available() -> bool:
    """Check if VAD is available."""
    try:
        import webrtcvad
        return True
    except ImportError:
        return False


# =============================================================================
# Menu Callback Functions
# =============================================================================

def toggle_recording() -> None:
    """Toggle recording on/off (menu callback)."""
    if state.get("recording"):
        stop_recording()
    else:
        start_recording()


def set_language(language: str) -> None:
    """Change transcription language (menu callback)."""
    if language not in {"de", "en"}:
        return
    cfg["language"] = language
    save_config(cfg)
    notify(f"Language set to {language}.")
    refresh_menu(get_callbacks(), state)


def set_device(name: str) -> None:
    """Change audio input device (menu callback)."""
    cfg["device_name"] = name
    save_config(cfg)
    update_device_index()
    label = name or "System Default"
    notify(f"Input device set to {label}.")
    refresh_menu(get_callbacks(), state)


def toggle_notifications() -> None:
    """Toggle notifications on/off (menu callback)."""
    cfg["notifications_enabled"] = not cfg.get("notifications_enabled", True)
    save_config(cfg)
    notify_state = "on" if cfg["notifications_enabled"] else "off"
    if cfg["notifications_enabled"]:
        notify(f"Notifications {notify_state}.")
    refresh_menu(get_callbacks(), state)


def toggle_auto_paste() -> None:
    """Toggle auto-paste on/off (menu callback)."""
    cfg["auto_paste_enabled"] = not cfg.get("auto_paste_enabled", False)
    save_config(cfg)
    state_txt = "enabled" if cfg["auto_paste_enabled"] else "disabled"
    notify(f"Auto-paste {state_txt}.")

    if cfg.get("auto_paste_enabled"):
        state["wayland_notice_shown"] = False

    if cfg.get("auto_paste_enabled") and is_wayland_session() and not state.get("wayland_notice_shown"):
        notify("Wayland session detected: auto-paste will remain clipboard-only.")
        state["wayland_notice_shown"] = True

    refresh_menu(get_callbacks(), state)


def set_paste_sequence(seq: str) -> None:
    """Change paste sequence (menu callback)."""
    if seq not in PASTE_OPTIONS:
        return
    cfg["paste_sequence"] = seq
    save_config(cfg)
    notify(f"Paste sequence set to {PASTE_OPTIONS[seq]}.")
    refresh_menu(get_callbacks(), state)


def toggle_vad() -> None:
    """Toggle VAD on/off (menu callback)."""
    if not vad_available():
        notify("WebRTC VAD not installed.")
        return
    cfg["use_vad"] = not cfg.get("use_vad", False)
    save_config(cfg)
    state_txt = "enabled" if cfg["use_vad"] else "disabled"
    notify(f"VAD {state_txt}.")
    refresh_menu(get_callbacks(), state)


def open_settings_callback() -> None:
    """Open settings window (menu callback)."""
    def on_save():
        """Callback after settings are saved."""
        refresh_menu(get_callbacks(), state)
        refresh_tray_indicator(state)

    open_settings_window(cfg, state, on_save=on_save)


def open_diagnostics_callback() -> None:
    """Open diagnostics window (menu callback)."""
    open_diagnostics_window(cfg, first_run=False)


def quit_application() -> None:
    """Quit application (menu callback)."""
    shutdown()


def get_callbacks() -> Dict[str, Any]:
    """
    Get all callback functions for tray menu.

    Returns:
        Dictionary of callback functions
    """
    return {
        "toggle_recording": toggle_recording,
        "open_settings": open_settings_callback,
        "open_diagnostics": open_diagnostics_callback,
        "set_language": set_language,
        "set_device": set_device,
        "toggle_notifications": toggle_notifications,
        "toggle_auto_paste": toggle_auto_paste,
        "set_paste_sequence": set_paste_sequence,
        "toggle_vad": toggle_vad,
        "quit": quit_application,
        "session_status_label": session_status_label,
        "tray_backend_label": tray_backend_label,
        "vad_available": vad_available,
    }


# =============================================================================
# OpenAI Client Initialization
# =============================================================================

def prepare_openai_client() -> bool:
    """
    Initialize OpenAI client if API key is available.

    Returns:
        True if client is ready, False otherwise
    """
    import os
    from whisprbar.config import load_env_file_values

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        env_values = load_env_file_values()
        api_key = env_values.get("OPENAI_API_KEY")

    if not api_key:
        state["client_ready"] = False
        debug("OPENAI_API_KEY not configured; transcription disabled until key is configured.")
        if not state.get("client_warning_shown"):
            notify("OPENAI_API_KEY not set. Transcription disabled until configured.")
            state["client_warning_shown"] = True
        return False

    try:
        # Test if we can create a transcriber (will initialize client internally)
        transcriber = get_transcriber()
        state["client_ready"] = True
        state["client_warning_shown"] = False
        return True
    except Exception as exc:
        state["client_ready"] = False
        debug(f"Failed to initialize transcription client: {exc}")
        if not state.get("client_warning_shown"):
            notify("Failed to initialize transcription client.")
            state["client_warning_shown"] = True
        return False


# =============================================================================
# Recording Handlers
# =============================================================================

def on_recording_start() -> None:
    """Handler called when recording starts."""
    state["recording"] = True
    refresh_tray_indicator(state)
    refresh_menu(get_callbacks(), state)
    debug("Recording started")

    # Play audio feedback
    play_audio_feedback("start")


def on_recording_stop() -> None:
    """Handler called when recording stops."""
    state["recording"] = False
    state["transcribing"] = True
    refresh_tray_indicator(state)
    refresh_menu(get_callbacks(), state)
    debug("Recording stopped, starting transcription")

    # Play audio feedback
    play_audio_feedback("stop")

    # Get audio data from recording state
    recording_state = get_recording_state()
    audio_data = recording_state.get("audio_data")

    if audio_data is None:
        debug("No audio data available")
        state["transcribing"] = False
        refresh_tray_indicator(state)
        return

    # Transcribe in background thread
    def transcribe_thread():
        try:
            # Import here to avoid circular dependencies
            from whisprbar.ui import show_live_overlay, update_live_overlay, hide_live_overlay
            from whisprbar.paste import perform_auto_paste as auto_paste
            from whisprbar.utils import write_history
            from whisprbar.audio import apply_vad, apply_noise_reduction, SAMPLE_RATE

            # Show live overlay if enabled
            show_live_overlay(cfg, "Processing audio...")

            # Apply noise reduction first (before VAD)
            audio_nr = apply_noise_reduction(audio_data)

            # Then apply VAD
            processed = apply_vad(audio_nr)

            input_seconds = audio_data.size / SAMPLE_RATE if audio_data.size else 0.0
            output_seconds = processed.size / SAMPLE_RATE if processed.size else 0.0
            debug(f"Audio: {input_seconds:.2f}s → {output_seconds:.2f}s after VAD")

            # Minimum audio length check (prevent hallucinations on very short/empty audio)
            MIN_AUDIO_SECONDS = 1.5
            if processed.size == 0 or output_seconds < MIN_AUDIO_SECONDS:
                # No speech detected or audio too short - notify but don't paste anything
                if processed.size == 0:
                    debug("No speech detected after VAD")
                    notify("No speech detected.")
                else:
                    debug(f"Audio too short after VAD ({output_seconds:.2f}s < {MIN_AUDIO_SECONDS}s)")
                    notify("Recording too short, no speech detected.")
                state["transcribing"] = False
                refresh_tray_indicator(state)
                hide_live_overlay()
                return

            # Audio energy check (prevent hallucinations on noise-only audio)
            # Calculate RMS (Root Mean Square) energy of the audio
            import numpy as np
            audio_energy = np.sqrt(np.mean(processed.astype(np.float32) ** 2))
            min_audio_energy = cfg.get("min_audio_energy", 0.0008)
            debug(f"Audio energy: {audio_energy:.4f} (threshold: {min_audio_energy})")

            if audio_energy < min_audio_energy:
                debug(f"Audio energy too low ({audio_energy:.4f} < {min_audio_energy}), likely just noise")
                notify("No speech detected, only background noise.")
                state["transcribing"] = False
                refresh_tray_indicator(state)
                hide_live_overlay()
                return

            # Update overlay
            update_live_overlay("Transcribing...", "Processing...")

            # Transcribe
            text = transcribe_audio(processed, cfg)

            if text:
                debug(f"Transcription: {text}")
                update_live_overlay(text, "Complete")

                # Write to history
                word_count = len(text.split())
                write_history(text, output_seconds, word_count)

                # Auto-paste if enabled
                if cfg.get("auto_paste_enabled"):
                    from whisprbar.paste import perform_auto_paste as auto_paste
                    auto_paste(text)
                else:
                    notify(f"Transcription: {text[:50]}...")

                # Hide overlay after configured delay (V5-style)
                def delayed_hide():
                    import time
                    duration = max(0.5, float(cfg.get("live_overlay_display_duration", 2.0)))
                    debug(f"[OVERLAY] Sleeping for {duration}s before hiding")
                    time.sleep(duration)
                    debug("[OVERLAY] Calling hide_live_overlay()")
                    hide_live_overlay()
                    debug("[OVERLAY] hide_live_overlay() returned")

                threading.Thread(target=delayed_hide, daemon=True).start()
            else:
                # Empty or failed transcription - notify but don't paste anything
                debug("Transcription empty or failed")
                notify("Transcription failed or empty.")
                hide_live_overlay()

        except Exception as exc:
            debug(f"Transcription error: {exc}")
            notify(f"Transcription error: {exc}")
            from whisprbar.ui import hide_live_overlay
            hide_live_overlay()
        finally:
            state["transcribing"] = False
            refresh_tray_indicator(state)
            refresh_menu(get_callbacks(), state)

    # Start transcription thread
    thread = threading.Thread(target=transcribe_thread, daemon=True)
    thread.start()


# =============================================================================
# Shutdown
# =============================================================================

def shutdown(*_args) -> None:
    """Graceful application shutdown."""
    debug("Shutting down...")

    # Stop recording if active
    if state.get("recording"):
        stop_recording()

    # Stop hotkey manager
    hotkey_manager = get_hotkey_manager()
    hotkey_manager.stop()
    debug("Hotkey manager stopped")

    # Shutdown tray
    shutdown_tray(state)

    # Release singleton lock
    release_singleton_lock()

    sys.exit(0)


def install_signal_handlers() -> None:
    """Install signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)


# =============================================================================
# CLI Argument Parsing
# =============================================================================

def parse_args(argv: List[str]) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        argv: Command-line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - Voice-to-text transcription",
        prog="whisprbar"
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run environment diagnostics and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


# =============================================================================
# Main Entry Point
# =============================================================================

def main() -> None:
    """Main application entry point."""
    # CRITICAL: Ensure stdin is open for pynput before anything else
    ensure_stdin_open()

    # Check for existing instance (singleton enforcement)
    if not acquire_singleton_lock():
        print("WhisprBar is already running.", file=sys.stderr)
        notify(
            "WhisprBar is already running",
            title="WhisprBar",
            force=True
        )
        sys.exit(1)

    # Load configuration
    load_config()
    debug("Config loaded")

    # Detect session type
    debug("Detecting session type...")
    state["session_type"] = detect_session_type()
    debug(f"Session type: {state['session_type']}")

    # Select and set tray backend
    debug("Selecting tray backend...")
    tray_backend = select_tray_backend()
    state["tray_backend"] = tray_backend
    debug(f"Tray backend: {tray_backend}")

    # Check for updates asynchronously
    debug("Checking for updates...")
    check_for_updates_async()
    debug("Update check initiated")

    # Show first-run diagnostics if needed
    debug("Checking first-run diagnostics...")
    maybe_show_first_run_diagnostics(cfg)
    debug("First-run diagnostics completed")

    # Prepare OpenAI client
    client_ready = prepare_openai_client()
    if not client_ready:
        debug("Transcription client not ready; will retry when needed")

    # Get or create hotkey manager
    hotkey_manager = get_hotkey_manager()

    # Set special handlers for ESC during recording and capture mode
    hotkey_manager.set_special_handlers(
        is_recording=lambda: state.get("recording", False),
        on_esc=lambda: stop_recording() if state.get("recording") else None,
        is_capture_active=lambda: state.get("hotkey_capture_active", False)
    )

    # Register all hotkeys from config
    hotkeys_config = cfg.get("hotkeys", {})

    # Register toggle_recording hotkey
    toggle_hotkey_str = hotkeys_config.get("toggle_recording")
    if toggle_hotkey_str:
        try:
            toggle_hotkey = parse_hotkey(toggle_hotkey_str)
            hotkey_manager.register("toggle_recording", toggle_hotkey, toggle_recording)
            debug(f"Registered toggle_recording hotkey: {toggle_hotkey_str}")
            # Store key for legacy UI compatibility
            state["hotkey_key"] = toggle_hotkey[1]  # Store the key token
        except Exception as exc:
            debug(f"Failed to register toggle_recording hotkey '{toggle_hotkey_str}': {exc}")
            # Fallback to F9
            from pynput import keyboard
            state["hotkey_key"] = keyboard.Key.f9
    else:
        debug("No toggle_recording hotkey configured, using F9 default")
        from pynput import keyboard
        state["hotkey_key"] = keyboard.Key.f9

    # Register open_settings hotkey
    open_settings_hotkey_str = hotkeys_config.get("open_settings")
    if open_settings_hotkey_str:
        try:
            open_settings_hotkey = parse_hotkey(open_settings_hotkey_str)
            hotkey_manager.register("open_settings", open_settings_hotkey, open_settings_callback)
            debug(f"Registered open_settings hotkey: {open_settings_hotkey_str}")
        except Exception as exc:
            debug(f"Failed to register open_settings hotkey '{open_settings_hotkey_str}': {exc}")

    # Register show_history hotkey (planned, stub for now)
    show_history_hotkey_str = hotkeys_config.get("show_history")
    if show_history_hotkey_str:
        try:
            show_history_hotkey = parse_hotkey(show_history_hotkey_str)
            # TODO: Implement show_history_callback
            def show_history_stub():
                debug("Show history not yet implemented")
                notify("Show history feature coming soon!")
            hotkey_manager.register("show_history", show_history_hotkey, show_history_stub)
            debug(f"Registered show_history hotkey: {show_history_hotkey_str}")
        except Exception as exc:
            debug(f"Failed to register show_history hotkey '{show_history_hotkey_str}': {exc}")

    # Start the hotkey manager
    hotkey_manager.start()
    debug("Hotkey manager started")

    # Wayland warning
    if is_wayland_session():
        debug("Wayland session detected. Auto-paste limited to clipboard-only mode.")
        print("[INFO] Wayland session detected. Auto-paste limited to clipboard-only mode.")
        if cfg.get("auto_paste_enabled") and not state.get("wayland_notice_shown"):
            notify("Wayland session detected: auto-paste is clipboard-only.")
            if cfg.get("notifications_enabled"):
                state["wayland_notice_shown"] = True

    # Print tray backend info
    print(f"[INFO] Tray backend in use: {tray_backend_label()}")

    # Update audio device index
    update_device_index()

    # Set up recording callbacks
    from whisprbar.audio import set_recording_callbacks
    set_recording_callbacks(on_recording_start, on_recording_stop)

    # Install signal handlers
    install_signal_handlers()

    # Initialize icons
    initialize_icons()

    # Start tray
    callbacks = get_callbacks()

    loop_runner = None
    if tray_backend == "appindicator":
        try:
            loop_runner = start_appindicator_tray(callbacks, state)
        except Exception as exc:
            print(f"[WARN] AppIndicator startup failed: {exc}")
            state["tray_backend"] = "gtk"
            import os
            os.environ["PYSTRAY_BACKEND"] = "gtk"
            loop_runner = start_pystray_tray(callbacks, state)
    else:
        loop_runner = start_pystray_tray(callbacks, state)

    # Run tray event loop
    try:
        loop_runner()
    except KeyboardInterrupt:
        shutdown()


# =============================================================================
# Script Entry Point
# =============================================================================

if __name__ == "__main__":
    cli_args = parse_args(sys.argv[1:])
    if cli_args.diagnose:
        load_config()
        sys.exit(_run_diagnostics_cli(cfg))
    main()
