# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WhisprBar is a Linux tray application for voice-to-text transcription using OpenAI Whisper. It's a single-file Python application (whisprbar.py ~2650 lines) with a shell launcher and installer script. The app uses global hotkeys to record audio, transcribes via OpenAI API, and auto-pastes results into the active window.

## Core Architecture

### Single-File Monolith Structure
All application logic lives in `whisprbar.py`:
- **Tray backend selection (lines 71-89)**: Runtime detection chooses AppIndicator (preferred) or PyStray fallback based on available system libraries
- **Configuration system (lines 176-191, 627-644)**: JSON config at `~/.config/whisprbar.json` merged with environment defaults
- **Audio pipeline**: Recording callback (line 1039) → VAD processing (line 1362) → OpenAI transcription (line 1541)
- **Hotkey system (lines 682-869)**: Global hotkey listener using pynput, supports modifier combinations
- **Auto-paste logic (lines 1170-1336)**: Platform-aware paste detection (X11 xdotool vs Wayland wl-clipboard)
- **Dual tray implementations**: PyStray (line 2507) and AppIndicator (line 2529) with separate menu builders

### Key Dependencies & System Integration
- **GI/GTK imports (lines 32-68)**: System packages from `/usr/lib/python3/dist-packages` injected into sys.path for PyGObject access
- **Tray backend detection**: `PYSTRAY_BACKEND` env var set before pystray import (line 91)
- **Session detection (line 196)**: `XDG_SESSION_TYPE` determines X11 vs Wayland behavior
- **OpenAI client (line 998)**: Lazy initialization from `OPENAI_API_KEY` in `~/.config/whisprbar.env`

### State Management
- `cfg` (line 193): Global dictionary holding runtime settings
- `recording_state` (lines 1045-1046): Threading state for audio capture
- `client` (line 1024): Global OpenAI client instance
- `selected_device_index` (line 990): Cached audio device ID

### VAD (Voice Activity Detection)
When enabled, `apply_vad()` (line 1362) processes audio with webrtcvad and energy-based filtering. Optional dependency (`webrtcvad` in requirements.txt). Configurable via `use_vad`, `vad_energy_ratio`, `vad_bridge_ms` settings.

### Auto-Paste Detection
Function `_detect_auto_paste_sequence_blocking()` (line 1170) tests `xdotool` keypresses and clipboard monitoring to determine the correct paste sequence (`ctrl+v`, `ctrl+shift+v`, `shift+insert`, or fallback to `type`). Cached in config as `paste_sequence`.

## Development Commands

### Setup & Environment
```bash
# Create virtualenv
python3 -m venv .venv

# Install dependencies
. .venv/bin/activate && pip install -r requirements.txt

# Run directly for development (bypasses launcher)
.venv/bin/python whisprbar.py

# Enable debug logging
WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py

# Run diagnostics
.venv/bin/python whisprbar.py --diagnose
```

### Testing & Validation
No automated test suite exists. Manual testing checklist:
- Test recording on X11 and Wayland sessions
- Verify auto-paste with `xdotool` (X11) and clipboard-only mode (Wayland)
- Exercise hotkey binding changes via settings dialog
- Confirm config schema compatibility after changes
- Test with/without VAD enabled
- Validate first-run diagnostics flow

### Installation & Deployment
```bash
# System-wide install (virtualenv + desktop entry)
./install.sh

# Dry-run to check dependencies
./install.sh --dry-run

# Non-interactive install
./install.sh --auto

# Skip system package checks
./install.sh --skip-system

# Launch after install
~/.local/bin/whisprbar

# Update existing installation
git pull && ./install.sh
```

## Configuration Files

- **`~/.config/whisprbar.json`**: Runtime settings (language, device, hotkey, auto-paste mode, VAD params)
- **`~/.config/whisprbar.env`**: Secrets (OPENAI_API_KEY, WHISPRBAR_HOME)
- **`~/.local/share/whisprbar/history.jsonl`**: Transcription log (append-only)
- **`whisprbar-launcher.sh`**: Bootstraps virtualenv and validates environment before launching Python script

## Platform-Specific Behavior

### Tray Backend Selection
1. AppIndicator (preferred): Detected via `gi.repository.AppIndicator3` availability
2. PyStray GTK: Fallback when AppIndicator unavailable but GTK available
3. PyStray Xorg: Used when GTK unavailable on X11 sessions
4. Auto: Default when no backend detected

### Desktop Environment Quirks
- **Cinnamon**: Ignores `ordering-index`, sorts tray icons by launch order. Restart panel with `cinnamon --replace` if ordering breaks.
- **KDE/Plasma**: Sorts tray icons alphabetically; use `aa-` prefix in app name for ordering hacks.
- **GNOME**: Requires `gnome-shell-extension-appindicator` for AppIndicator support. Sorts by spawn time.
- **XFCE**: Enable `xfce4-statusnotifier-plugin` for tray support.

### Session Type Differences
- **X11**: Full auto-paste via `xdotool` keypresses. Window detection for paste sequence selection.
- **Wayland**: Clipboard-only mode (no window control). Auto-paste degrades to copy-to-clipboard. Use `type` fallback for text simulation (less reliable).

## Code Modification Guidelines

### Adding New Config Options
1. Add default value to `DEFAULT_CFG` (line 176)
2. Update settings dialog builder in `open_settings_window()` (line 1786)
3. Add getter/setter functions (pattern: `set_language()` line 1629, `toggle_notifications()` line 1647)
4. Document in `INSTALL.md` or `README.md` if user-facing

### Modifying Hotkey System
- Hotkey parsing: `parse_hotkey()` (line 730)
- Key normalization: `normalize_key_token()` (line 719)
- Capture UI: `capture_hotkey()` (line 1688)
- Update binding: `update_hotkey_binding()` (line 1755)
- Restart listener after changes: `start_hotkey_listener()` (line 820)

### Audio Processing Changes
- Recording callback: `recording_callback()` (line 1039) - runs in audio thread
- VAD processing: `apply_vad()` (line 1362) - processes numpy array
- Transcription: `transcribe_audio()` (line 1541) - async, runs in thread
- History logging: `write_history()` (line 1525)

### Tray Menu Modifications
Two separate menu builders must stay in sync:
- PyStray: `build_menu()` (line 2328) - returns pystray.Menu
- AppIndicator: `build_appindicator_menu()` (line 2393) - returns Gtk.Menu

Use `refresh_menu()` (line 937) to rebuild menus after state changes.

## Versioning & Releases

- Version constant: `APP_VERSION` (line 94) - single source of truth
- Update check: `check_for_updates_async()` (line 279) compares against GitHub releases
- Git tags follow `vX.Y.Z` format matching `APP_VERSION`
- Release workflow: Bump `APP_VERSION` → Update `CHANGELOG.md` → Commit → Tag → Push tag
- Keep `WORKLOG.md` and `CHANGELOG.md` in sync with version bumps

## Diagnostic System

First-run wizard (`maybe_show_first_run_diagnostics()` line 621) checks:
- Session type (X11/Wayland)
- Tray backend availability
- Auto-paste capability (xdotool/wl-clipboard)
- Audio devices via sounddevice
- OpenAI API key presence
- System dependencies (notify-send, zenity)

CLI diagnostics: `python whisprbar.py --diagnose` (implementation at line 595)

Diagnostic results use `DiagnosticResult` dataclass (line 129) with status levels: ok/warn/error.

## Common Patterns

### Debug Logging
```python
debug("message")  # Line 340 - only prints when WHISPRBAR_DEBUG=1
```

### Notifications
```python
notify("message", title="WhisprBar", force=False)  # Line 657
# Respects cfg["notifications_enabled"] unless force=True
```

### Config Updates
```python
cfg["key"] = value
save_config()  # Line 638 - writes to CONFIG_PATH
refresh_menu()  # Rebuild menus with new state
```

### Threading Pattern
```python
threading.Thread(target=func, daemon=True).start()
# Used for: transcription, update checks, auto-paste detection
```

## Known Limitations

- Wayland: No reliable auto-paste (clipboard-only or `type` fallback)
- Single hotkey: Cannot bind multiple hotkeys to different actions
- No undo: Transcription immediately pastes (history log available at `~/.local/share/whisprbar/history.jsonl`)
- VAD sensitivity: May clip quiet speech or retain background noise depending on `vad_energy_ratio`
- Tray ordering: Desktop-dependent, not controllable by app

## File References for Common Tasks

- **Change transcription API/model**: Line 173 (`OPENAI_MODEL`), line 1541 (transcribe call)
- **Modify recording parameters**: Lines 170-172 (`SAMPLE_RATE`, `CHANNELS`, `BLOCK_SIZE`)
- **Add menu item**: Lines 2328 (PyStray) and 2393 (AppIndicator)
- **Change default language**: Line 177 in `DEFAULT_CFG`
- **Adjust paste timing**: Line 174 (`PASTE_DETECT_TIMEOUT`), line 183 (`paste_delay_ms`)
- **Update icon generation**: Line 959 (`build_icon()`)
- **Modify installer logic**: `install.sh` (bash script, ~12K lines)

## Security Notes

- API keys stored in `~/.config/whisprbar.env` (mode 600 recommended)
- No secrets in tracked files or logs
- Audio files cleaned from `/tmp/whisprbar*` after transcription
- History log may contain sensitive transcripts - stored at `~/.local/share/whisprbar/history.jsonl`