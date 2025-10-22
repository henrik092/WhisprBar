# CLAUDE.md - WhisprBar V6 Developer Guide

This guide provides comprehensive information for developers (human or AI) working with WhisprBar V6.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Module Reference](#module-reference)
4. [Development Commands](#development-commands)
5. [Common Tasks](#common-tasks)
6. [Configuration System](#configuration-system)
7. [Platform-Specific Behavior](#platform-specific-behavior)
8. [Code Modification Guidelines](#code-modification-guidelines)
9. [Testing Strategy](#testing-strategy)
10. [Documentation Maintenance](#documentation-maintenance)

---

## Project Overview

**WhisprBar** is a Linux system tray application for voice-to-text transcription using multiple backends (OpenAI Whisper API, faster-whisper local, sherpa-onnx streaming). It uses global hotkeys to record audio, transcribes via selected backend, and auto-pastes results into the active window.

**Version:** V6 (Modular)
**Language:** Python 3
**Platform:** Linux (X11 and Wayland)
**Architecture:** Modular Python package

### What's New in V6

V6 is a complete architectural rewrite of the V5 monolith (4017 lines):
- **Modular Design:** 9 focused modules instead of single file
- **Maintainability:** Each module 200-800 lines with clear responsibilities
- **Testability:** Isolated components, easier to test
- **Extensibility:** Clean interfaces for adding features
- **Professional Quality:** PEP 8 compliant, type hints, comprehensive docs

**100% backwards compatible** - same features, same config, same installation.

---

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        User Space                            │
│  (Hotkey Press → Recording → Transcription → Auto-Paste)    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     main.py (Orchestrator)                   │
│  • CLI argument handling                                     │
│  • Application lifecycle                                     │
│  • Module coordination                                       │
│  • Signal handling (SIGTERM, SIGINT)                         │
└─────────────────────────────────────────────────────────────┘
       ↓           ↓          ↓          ↓          ↓
┌──────────┐ ┌─────────┐ ┌────────┐ ┌──────┐ ┌────────┐
│  tray.py │ │ ui.py   │ │hotkeys │ │paste │ │ utils  │
│          │ │         │ │  .py   │ │ .py  │ │  .py   │
│ System   │ │Settings │ │Global  │ │Auto- │ │Icons   │
│ Tray     │ │Dialog   │ │Hotkey  │ │Paste │ │History │
│ Icon     │ │Overlay  │ │Listener│ │Logic │ │Updates │
└──────────┘ └─────────┘ └────────┘ └──────┘ └────────┘
       ↓           ↓                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      audio.py                                │
│  • Recording (sounddevice)                                   │
│  • VAD (voice activity detection)                            │
│  • Noise reduction                                           │
│  • Audio chunking                                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   transcription.py                           │
│  • Transcriber (ABC)                                         │
│  • OpenAITranscriber                                         │
│  • FasterWhisperTranscriber                                  │
│  • SherpaTranscriber                                         │
│  • Postprocessing pipeline                                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      config.py                               │
│  • Configuration load/save                                   │
│  • Environment variables                                     │
│  • Defaults management                                       │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
WhisperBar/                           # Repository root
├── whisprbar/                        # Main Python package
│   ├── __init__.py                   # Package initialization, version
│   ├── main.py                       # Entry point, app orchestration
│   ├── config.py                     # Configuration system
│   ├── utils.py                      # Shared utilities
│   ├── audio.py                      # Audio capture & processing
│   ├── transcription.py              # Transcription backends
│   ├── hotkeys.py                    # Global hotkey handling
│   ├── paste.py                      # Auto-paste logic
│   ├── ui.py                         # GUI components
│   └── tray.py                       # System tray integration
│
├── whisprbar.py                      # Legacy wrapper (backwards compat)
├── whisprbar-launcher.sh             # Shell launcher (venv + env)
├── whisprbar.desktop                 # Desktop entry
├── install.sh                        # System installation script
├── requirements.txt                  # Python dependencies
│
├── README.md                         # User-facing documentation
├── CHANGELOG.md                      # Version history
├── WORKLOG.md                        # Development log
├── CLAUDE.md                         # This file
├── AGENTS.md                         # Repository guide
├── ROADMAP_REFACTORING.md            # Refactoring plan
│
├── LICENSE                           # MIT License
├── .gitignore                        # Git ignore rules
├── docs/                             # Images, screenshots
│
└── Alte version v5/                  # V5 monolith (archive, read-only)
```

---

## Module Reference

### 1. `whisprbar/config.py` (~200 lines)

**Purpose:** Configuration management

**Key Components:**

**Constants:**
- `DEFAULT_CFG` - Default configuration dictionary
- `CONFIG_PATH` - Path to `~/.config/whisprbar.json`
- `ENV_FILE_PATH` - Path to `~/.config/whisprbar.env`
- `HISTORY_PATH` - Path to `~/.local/share/whisprbar/history.jsonl`

**Functions:**
- `load_config() -> dict` - Load config from disk, merge with defaults
- `save_config(cfg: dict) -> None` - Save config to disk
- `get_env_file_path() -> Path` - Locate environment file
- `load_env_file_values() -> dict` - Parse .env file for secrets

**Config Schema:**
```python
{
    "language": "de",                      # Transcription language
    "device_name": None,                   # Audio device (None = default)
    "hotkey": "F9",                        # Recording hotkey
    "notifications_enabled": False,        # System notifications
    "auto_paste_enabled": True,            # Auto-paste after transcription
    "paste_sequence": "auto",              # Paste method (auto/ctrl+v/type)
    "paste_delay_ms": 250,                 # Delay before paste
    "use_vad": True,                       # Voice activity detection
    "vad_energy_ratio": 0.05,              # VAD sensitivity
    "vad_bridge_ms": 300,                  # Bridge pauses in speech
    "vad_auto_stop_enabled": False,        # Auto-stop after silence
    "vad_auto_stop_silence_seconds": 2.0,  # Silence duration for auto-stop
    "chunking_enabled": True,              # Chunk long audio
    "chunk_duration_seconds": 30.0,        # Chunk size
    "postprocess_enabled": True,           # Clean up text
    "noise_reduction_enabled": True,       # Reduce background noise
    "min_audio_energy": 0.0008,            # Hallucination prevention threshold (0.0001-0.01)
    "transcription_backend": "openai",     # Backend (openai/faster-whisper/sherpa)
    "faster_whisper_model": "large",       # Model size for faster-whisper
    "live_overlay_enabled": False,         # Show live transcription
    ...
}
```

**Dependencies:**
- Standard library only (json, pathlib, os)

---

### 2. `whisprbar/utils.py` (~400 lines)

**Purpose:** Shared utilities (icons, history, updates, platform detection, diagnostics)

**Key Components:**

**Icon Generation:**
- `build_icon(state: str) -> PIL.Image` - Generate tray icon (ready/recording/transcribing)
- `build_notification_icon() -> PIL.Image` - Icon for notifications

**History Logging:**
- `write_history(text: str, audio_seconds: float) -> None` - Append to history.jsonl

**Update Checking:**
- `check_for_updates_async(callback: Callable) -> None` - Check GitHub for updates

**Platform Detection:**
- `command_exists(name: str) -> bool` - Check if system command available
- `get_session_type() -> str` - Detect X11 or Wayland

**Diagnostics:**
- `DiagnosticResult` - Dataclass for diagnostic results
- `check_session_type() -> DiagnosticResult`
- `check_tray_backend() -> DiagnosticResult`
- `check_auto_paste() -> DiagnosticResult`
- `check_audio_devices() -> DiagnosticResult`
- `check_openai_key() -> DiagnosticResult`
- `check_system_dependencies() -> DiagnosticResult`

**Dependencies:**
- PIL (icons)
- pathlib, json (history)
- urllib, threading (updates)
- subprocess (platform detection)

---

### 3. `whisprbar/audio.py` (~600 lines)

**Purpose:** Audio capture and processing

**Key Components:**

**Constants:**
- `SAMPLE_RATE = 16000` - Audio sample rate
- `CHANNELS = 1` - Mono audio
- `BLOCK_SIZE = 1024` - Audio buffer size

**Recording:**
- `start_recording() -> None` - Begin audio capture
- `stop_recording() -> np.ndarray` - Stop capture, return audio data
- `recording_callback(indata, frames, time, status)` - Sounddevice callback

**Processing:**
- `apply_vad(audio_data: np.ndarray, cfg: dict) -> np.ndarray` - Voice activity detection
- `apply_noise_reduction(audio_data: np.ndarray, cfg: dict) -> np.ndarray` - Remove noise
- `split_audio_into_chunks(audio, duration, overlap) -> List[np.ndarray]` - Split for parallel processing

**VAD Auto-Stop:**
- `vad_auto_stop_monitor(cfg: dict) -> None` - Thread that monitors silence during recording

**State:**
- `recording_state` - Dict with recording state (thread-safe via locks)
- `selected_device_index` - Cached audio device ID

**Dependencies:**
- numpy, sounddevice (audio)
- webrtcvad (VAD)
- noisereduce (noise reduction)
- config.py (settings)

**Threading:**
- Recording runs in sounddevice thread
- VAD auto-stop monitor in separate thread

---

### 4. `whisprbar/transcription.py` (~800 lines)

**Purpose:** All transcription backends and text postprocessing

**Key Components:**

**Abstract Base:**
```python
class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        pass
```

**Backends:**
- `OpenAITranscriber` - OpenAI Whisper API
- `FasterWhisperTranscriber` - Local faster-whisper (CPU/GPU)
- `SherpaTranscriber` - Streaming sherpa-onnx

**Factory:**
- `get_transcriber(backend: str, cfg: dict) -> Transcriber` - Create transcriber instance

**Main Functions:**
- `transcribe_audio(audio: np.ndarray, cfg: dict) -> str` - Main orchestration
- `transcribe_audio_chunked(audio, cfg) -> str` - Parallel chunking for long audio
- `transcribe_chunk(chunk, transcriber) -> str` - Transcribe single chunk
- `merge_chunk_transcripts(chunks: List[str]) -> str` - Merge with overlap deduplication

**Postprocessing:**
- `postprocess_transcript(text: str, cfg: dict) -> str` - Main pipeline
- `postprocess_fix_spacing(text: str) -> str` - Remove double spaces, fix punctuation spacing
- `postprocess_fix_capitalization(text: str, lang: str) -> str` - Capitalize sentences, fix "i"→"I"

**Dependencies:**
- openai (OpenAI API)
- faster_whisper (local transcription)
- sherpa_onnx (streaming)
- numpy, threading
- audio.py (chunking)
- config.py (backend selection)

**State:**
- `_transcriber_cache` - Cached transcriber instances (singleton per backend)

---

### 5. `whisprbar/hotkeys.py` (~300 lines)

**Purpose:** Global hotkey management

**Key Components:**

**Parsing:**
- `parse_hotkey(hotkey_str: str) -> tuple` - Parse "Ctrl+Shift+F9" → (modifiers, key)
- `normalize_key_token(key: str) -> str` - Standardize key names

**Listener:**
- `start_hotkey_listener(hotkey: str, callback: Callable) -> None` - Start global listener
- `stop_hotkey_listener() -> None` - Stop listener

**Interactive Capture:**
- `capture_hotkey(on_captured: Callable) -> None` - GTK dialog to capture new hotkey
- `update_hotkey_binding(new_hotkey: str, cfg: dict) -> None` - Update and restart listener

**Dependencies:**
- pynput.keyboard (global hotkey listening)
- gi.repository (GTK dialog)
- config.py (save new hotkey)

**State:**
- `_hotkey_listener` - Active pynput listener instance

**Threading:**
- Hotkey listener runs in separate thread (pynput manages this)

---

### 6. `whisprbar/paste.py` (~350 lines)

**Purpose:** Auto-paste detection and execution

**Key Components:**

**Detection:**
- `detect_auto_paste_sequence() -> str` - Detect best paste method for current system
  - Returns: "ctrl+v", "ctrl+shift+v", "shift+insert", "type", or "clipboard"

**Execution:**
- `auto_paste(text: str, cfg: dict) -> None` - Execute paste with configured method

**Platform Variants:**
- **X11:** Uses `xdotool` for keypresses
  - `ctrl+v` - Standard paste
  - `ctrl+shift+v` - Paste without formatting
  - `shift+insert` - Alternative paste
  - `type` - Type text character by character
- **Wayland:** Clipboard-only or `wtype` fallback
  - No window control available
  - Copy to clipboard, user pastes manually

**Dependencies:**
- pyperclip (clipboard operations)
- subprocess (xdotool, wl-clipboard, wtype)
- utils.py (session type detection)
- config.py (paste settings)

**Timing:**
- `PASTE_DETECT_TIMEOUT = 10.0` - Timeout for detection test
- Configurable delay via `paste_delay_ms`

---

### 7. `whisprbar/ui.py` (~700 lines)

**Purpose:** All GUI components (settings dialog, live overlay, diagnostics)

**Key Components:**

**Settings Dialog:**
- `open_settings_window(cfg: dict, on_save: Callable) -> None` - Main settings window
  - Language selection
  - Audio device selection
  - Hotkey binding
  - Transcription backend selection
  - VAD settings (sliders for sensitivity, auto-stop, end recording buffer)
  - Chunking settings
  - Postprocessing options
  - Noise reduction
  - Live overlay configuration
  - Notifications toggle
  - **Dynamic Visibility**: Sub-options automatically hidden when parent feature disabled
  - **Units Display**: All sliders show values with units (ms, s, %, px)
  - **Smooth Sliding**: No marks/"hooks" on sliders for fluid adjustment

**Live Overlay:**
- `show_live_overlay(cfg: dict) -> None` - Show transcription overlay window
- `update_live_overlay(text: str) -> None` - Update overlay text in real-time
- `hide_live_overlay() -> None` - Close overlay window
  - Frameless, fully transparent window with RGBA compositing
  - Rounded corners (12px radius) with smooth transparency
  - Bottom-right corner positioning
  - Auto-hides after completion

**Diagnostics:**
- `maybe_show_first_run_diagnostics(cfg: dict) -> None` - First-run wizard
  - Checks session type, tray backend, auto-paste, audio, API key, system deps
  - Shows results with color-coded status (OK/WARN/ERROR)

**Dependencies:**
- gi.repository (Gtk, GLib) - All GUI
- config.py (settings)
- utils.py (diagnostics)

**State:**
- `_live_overlay_window` - Current overlay window instance
- `_settings_window` - Current settings window instance

**Threading:**
- UI runs in GTK main thread
- Use `GLib.idle_add()` for updates from other threads

---

### 8. `whisprbar/tray.py` (~500 lines)

**Purpose:** System tray integration (multiple backends)

**Key Components:**

**Backend Selection:**
- `select_tray_backend() -> str` - Auto-detect best backend
  - Returns: "appindicator", "gtk", "xorg", or "auto"
  - Priority: AppIndicator > PyStray GTK > PyStray Xorg

**Menu Building:**
- `build_menu_data(cfg: dict, callbacks: dict) -> dict` - Generate unified menu structure
- `build_pystray_menu(menu_data: dict) -> pystray.Menu` - PyStray menu
- `build_appindicator_menu(menu_data: dict) -> Gtk.Menu` - AppIndicator menu

**Tray Runners:**
- `run_tray_pystray(cfg: dict, callbacks: dict) -> None` - Run PyStray backend
- `run_tray_appindicator(cfg: dict, callbacks: dict) -> None` - Run AppIndicator backend

**Menu Refresh:**
- `refresh_menu() -> None` - Rebuild menu after state change (e.g., backend switch)

**Dependencies:**
- pystray, PIL (PyStray backend)
- gi.repository (AppIndicator3, Gtk) - AppIndicator backend
- utils.py (icons)
- config.py (state)

**Backends:**
1. **AppIndicator3** (preferred)
   - Best integration on Ubuntu/GNOME
   - Requires `gir1.2-appindicator3-0.1`
2. **PyStray GTK**
   - Fallback when AppIndicator unavailable
   - Requires GTK + xprop
3. **PyStray Xorg**
   - Fallback on X11 without GTK

**Desktop Environment Notes:**
- Cinnamon: Sorts by launch order (restart panel if needed)
- KDE/Plasma: Sorts alphabetically
- GNOME: Sorts by spawn time (with AppIndicator extension)

---

### 9. `whisprbar/main.py` (~400 lines)

**Purpose:** Application orchestration and lifecycle

**Key Components:**

**Entry Point:**
- `main() -> None` - Main entry point
  - Parses CLI arguments
  - Initializes config
  - Runs diagnostics (first run)
  - Starts hotkey listener
  - Runs tray
  - Handles signals

**CLI Arguments:**
- `--diagnose` - Run diagnostics and exit
- `--version` - Show version and exit

**Signal Handling:**
- SIGTERM, SIGINT - Graceful shutdown

**Orchestration:**
Coordinates all modules:
1. Load config (`config.load_config()`)
2. Check for updates (`utils.check_for_updates_async()`)
3. Run diagnostics if first run (`ui.maybe_show_first_run_diagnostics()`)
4. Start hotkey listener (`hotkeys.start_hotkey_listener()`)
5. On hotkey press:
   - Start recording (`audio.start_recording()`)
   - Show live overlay (`ui.show_live_overlay()`)
6. On hotkey release:
   - Stop recording (`audio.stop_recording()`)
   - Apply VAD/noise reduction (`audio.apply_vad()`, `audio.apply_noise_reduction()`)
   - Transcribe (`transcription.transcribe_audio()`)
   - Postprocess (`transcription.postprocess_transcript()`)
   - Auto-paste (`paste.auto_paste()`)
   - Write history (`utils.write_history()`)
   - Hide overlay (`ui.hide_live_overlay()`)
7. Run tray (`tray.run_tray_*()`)

**State Management:**
- Global config (`cfg`)
- Transcriber instances
- Recording state
- Eventually: `WhisprBarApp` class to encapsulate state

**Dependencies:**
- All other modules

---

### 10. `whisprbar.py` (~10 lines)

**Purpose:** Legacy wrapper for backwards compatibility

```python
#!/usr/bin/env python3
"""WhisprBar - Voice-to-text tray application."""
from whisprbar.main import main

if __name__ == "__main__":
    main()
```

Ensures existing installations (`~/.local/bin/whisprbar`) continue to work.

---

## Development Commands

### Setup & Environment

```bash
# Clone repository
git clone https://github.com/henrik092/whisprBar.git WhisperBar
cd WhisperBar

# Create virtual environment
python3 -m venv .venv

# Activate venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install system dependencies (Ubuntu/Debian)
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
                 gir1.2-appindicator3-0.1 xdotool libnotify-bin \
                 portaudio19-dev
```

### Running

```bash
# Run directly (development)
.venv/bin/python whisprbar.py

# Run with launcher (production-like)
./whisprbar-launcher.sh

# Run with debug logging
WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py

# Run diagnostics
.venv/bin/python whisprbar.py --diagnose

# Check version
.venv/bin/python whisprbar.py --version
```

### Installation

```bash
# Install system-wide
./install.sh

# Dry-run (check dependencies only)
./install.sh --dry-run

# Non-interactive install
./install.sh --auto

# Skip system package checks
./install.sh --skip-system

# Launch after install
~/.local/bin/whisprbar
```

### Testing

```bash
# Import test (verify module structure)
python3 -c "from whisprbar import config, audio, transcription"

# Config test
python3 -c "from whisprbar.config import load_config; print(load_config())"

# Audio device list
python3 -m sounddevice

# Hotkey test
WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py
# Press F9, check console output

# Full feature test
# 1. Start app
# 2. Press hotkey
# 3. Speak
# 4. Release hotkey
# 5. Verify text pasted
```

### Module Development

```bash
# Edit a module
vim whisprbar/audio.py

# Test import after changes
python3 -c "from whisprbar.audio import start_recording"

# Run full app to test integration
.venv/bin/python whisprbar.py
```

---

## Common Tasks

### Change Transcription API/Model

**OpenAI API:**
- `whisprbar/transcription.py:OpenAITranscriber.transcribe()`
- Model constant: `OPENAI_MODEL = "whisper-1"`

**faster-whisper:**
- `whisprbar/transcription.py:FasterWhisperTranscriber`
- Model selection via config: `faster_whisper_model`

### Modify Recording Parameters

- `whisprbar/audio.py` - Constants at top
  - `SAMPLE_RATE = 16000`
  - `CHANNELS = 1`
  - `BLOCK_SIZE = 1024`

### Add Menu Item

1. `whisprbar/tray.py:build_menu_data()` - Add to menu structure
2. Add callback function
3. Pass callback in `main.py` when calling `run_tray_*()`

### Change Default Language

- `whisprbar/config.py:DEFAULT_CFG["language"]`

### Adjust Paste Timing

- `whisprbar/paste.py:PASTE_DETECT_TIMEOUT` - Detection timeout
- `whisprbar/config.py:DEFAULT_CFG["paste_delay_ms"]` - Delay before paste

### Adjust Hallucination Prevention

**Problem:** Whisper hallucinations on empty/short audio ("Können wir?", "こんにちは", "Thank you for watching")

**Solution:** Audio energy threshold prevents transcription when audio is too quiet (likely noise-only)

**Configuration:**
- Settings Dialog (F10) → "Hallucination Prevention" slider
- Config key: `min_audio_energy` (default: 0.0008, range: 0.0001-0.01)

**Tuning:**
- **Too many hallucinations** → Increase threshold (e.g., 0.002-0.005)
- **Normal speech blocked** → Decrease threshold (e.g., 0.0003-0.0006)
- **Default (0.0008)** works for most cases

**Technical Details:**
- Calculates RMS (Root Mean Square) energy after VAD
- Blocks transcription if `audio_energy < min_audio_energy`
- Also enforces minimum audio length (1.5s after VAD)
- See `whisprbar/main.py:346-359` for implementation

### Update Icon Generation

- `whisprbar/utils.py:build_icon(state)` - Tray icon
- `whisprbar/utils.py:build_notification_icon()` - Notification icon

### Add New Config Option

1. `whisprbar/config.py:DEFAULT_CFG` - Add default value
2. `whisprbar/ui.py:open_settings_window()` - Add UI control
3. Use in relevant module (e.g., `audio.py`, `transcription.py`)
4. Document in this file

### Add New Transcription Backend

1. Create class in `whisprbar/transcription.py`:
```python
class MyBackendTranscriber(Transcriber):
    def transcribe(self, audio: np.ndarray) -> str:
        # Implementation
        pass
```

2. Update `get_transcriber()` factory
3. Add backend option to settings UI (`ui.py`)
4. Update config schema

---

## Configuration System

### Config Files

**`~/.config/whisprbar.json`** - User settings (JSON)
- Loaded on startup
- Merged with defaults from `DEFAULT_CFG`
- Updated when settings change

**`~/.config/whisprbar.env`** - Secrets (KEY=VALUE format)
- `OPENAI_API_KEY` - OpenAI API key
- `WHISPRBAR_HOME` - Custom home directory (optional)
- Mode 600 recommended

**`~/.local/share/whisprbar/history.jsonl`** - Transcription log
- Append-only JSONL
- Each line: `{"timestamp": "...", "text": "...", "duration": ...}`

### Config Schema

See `whisprbar/config.py:DEFAULT_CFG` for full schema and defaults.

**Key Settings:**
- `language` - Transcription language (ISO code)
- `device_name` - Audio device (None = system default)
- `hotkey` - Recording hotkey (e.g., "F9", "Ctrl+Shift+R")
- `transcription_backend` - Backend selection ("openai", "faster-whisper", "sherpa")
- `use_vad` - Enable voice activity detection
- `stop_tail_grace_ms` - Continue recording after hotkey release (100-2000ms, default: 500ms)
- `chunking_enabled` - Enable parallel chunking for long audio
- `postprocess_enabled` - Enable text postprocessing
- `noise_reduction_enabled` - Enable noise reduction
- `min_audio_energy` - Minimum audio energy threshold to prevent hallucinations (0.0001-0.01, default: 0.0008)

### Environment Variables

**`WHISPRBAR_DEBUG=1`** - Enable debug logging
**`WHISPRBAR_HOME`** - Override home directory for config/history
**`PYSTRAY_BACKEND`** - Force tray backend (set automatically by `select_tray_backend()`)

---

## Platform-Specific Behavior

### Tray Backend Selection

1. **AppIndicator** (preferred)
   - Detected via `gi.repository.AppIndicator3`
   - Best on Ubuntu, GNOME, Cinnamon
   - Install: `gir1.2-appindicator3-0.1`

2. **PyStray GTK**
   - Fallback when AppIndicator unavailable
   - Requires GTK + xprop
   - Works on most desktops

3. **PyStray Xorg**
   - Fallback on X11 without GTK
   - Basic functionality

### Session Type (X11 vs Wayland)

**Detected via:** `XDG_SESSION_TYPE` environment variable

**X11:**
- Full auto-paste via `xdotool` keypresses
- Window detection for paste sequence
- Best user experience

**Wayland:**
- Clipboard-only mode (no window control)
- Auto-paste degrades to copy-to-clipboard
- Optional: `wtype` for text input simulation (less reliable)

### Desktop Environment Quirks

**Cinnamon:**
- Ignores `ordering-index` in tray
- Sorts icons by launch order
- Fix: Restart panel (`cinnamon --replace`)

**KDE/Plasma:**
- Sorts tray icons alphabetically
- Hack: Use `aa-` prefix in app name

**GNOME:**
- Requires `gnome-shell-extension-appindicator`
- Sorts by spawn time

**XFCE:**
- Enable `xfce4-statusnotifier-plugin` for tray

---

## Code Modification Guidelines

### Style Guidelines

**PEP 8 Compliance:**
- 4-space indentation
- `snake_case` for functions and variables
- `UPPER_CASE` for constants
- `PascalCase` for classes
- Max line length: 100 characters (flexible for readability)

**Type Hints:**
- Use on public functions
- Example: `def load_config() -> dict:`
- Not required on private functions (but helpful)

**Docstrings:**
- Use for complex functions
- Format: Google style or NumPy style
```python
def transcribe_audio(audio: np.ndarray, cfg: dict) -> str:
    """Transcribe audio using selected backend.

    Args:
        audio: Audio data as numpy array
        cfg: Configuration dictionary

    Returns:
        Transcribed text string
    """
```

### Module Boundaries

**Keep modules focused:**
- Audio logic → `audio.py`
- Transcription → `transcription.py`
- UI → `ui.py`
- Never mix concerns

**Imports:**
- Avoid circular imports
- Use absolute imports: `from whisprbar.config import load_config`
- Group imports: stdlib, third-party, local

### Threading

**Current threads:**
1. Main thread (GTK/Tray)
2. Audio recording thread (sounddevice)
3. Hotkey listener thread (pynput)
4. VAD auto-stop monitor thread
5. Transcription thread (async)

**Thread-safe state access:**
- Use locks for shared state
- Prefer message passing over shared state
- GTK updates: Use `GLib.idle_add()` from other threads

### Error Handling

**Graceful degradation:**
- If VAD unavailable → skip VAD
- If noise reduction fails → use raw audio
- If API call fails → show error notification

**User-friendly errors:**
- Catch exceptions at module boundaries
- Show helpful error messages
- Log details with `debug()`

---

## Testing Strategy

### Manual Testing Checklist

After code changes, test:

**Basic Flow:**
- [ ] App starts without errors
- [ ] Tray icon appears
- [ ] Hotkey triggers recording
- [ ] Recording indicator shows
- [ ] Stop recording works
- [ ] Transcription completes
- [ ] Text auto-pastes correctly

**Settings:**
- [ ] Open settings dialog
- [ ] Change language → saves correctly
- [ ] Change hotkey → new hotkey works
- [ ] Change backend → transcription uses new backend
- [ ] Toggle options → reflected in behavior

**Edge Cases:**
- [ ] No internet → faster-whisper works (if installed)
- [ ] Wrong audio device → error message shown
- [ ] Empty recording → no crash
- [ ] Very long recording (>5 min) → chunking works

### Module Testing

**Import test after changes:**
```bash
python3 -c "from whisprbar.audio import start_recording"
```

**Config test:**
```bash
python3 -c "from whisprbar.config import load_config; print(load_config())"
```

**Icon test:**
```bash
python3 -c "from whisprbar.utils import build_icon; build_icon('ready').show()"
```

### Future: Unit Tests

Foundation for pytest:
```python
# tests/test_config.py
def test_load_config():
    cfg = load_config()
    assert "language" in cfg
    assert cfg["use_vad"] == True
```

---

## Documentation Maintenance

**IMPORTANT:** Keep documentation in sync with code changes.

### When to Update Docs

**After adding features:**
- Update CHANGELOG.md (`[Unreleased]` section)
- Update WORKLOG.md (dated entry)
- Update this file (CLAUDE.md) if architecture changed
- Update README.md if user-facing

**After refactoring:**
- Update this file with new module structure
- Update line references → function references
- Update ROADMAP_REFACTORING.md status

**After bug fixes:**
- Update WORKLOG.md
- Update CHANGELOG.md if user-impacting

### Documentation Files

**CLAUDE.md** (this file)
- Architecture and development guide
- Update after structural changes

**AGENTS.md**
- Repository guide for AI agents
- Update after file structure changes

**README.md**
- User-facing quick start
- Update after feature additions

**CHANGELOG.md**
- Version history (Keep a Changelog format)
- Update before each release

**WORKLOG.md**
- Development log (chronological)
- Update after each significant change

**ROADMAP_REFACTORING.md**
- Refactoring plan and progress
- Update as phases complete

---

## Known Limitations

**Wayland:**
- No reliable auto-paste (clipboard-only)
- No window detection for paste sequence

**Single Hotkey:**
- Can only bind one global hotkey
- Cannot have separate hotkeys for different actions

**No Undo:**
- Transcription immediately pastes
- History log available for recovery

**VAD Sensitivity:**
- May clip quiet speech or retain noise
- Tunable via `vad_energy_ratio`

**Tray Ordering:**
- Desktop-dependent
- Not controllable by app

---

## Security Notes

**API Keys:**
- Store in `~/.config/whisprbar.env` (mode 600)
- Never commit to git (.gitignore configured)

**Secrets:**
- No secrets in tracked files
- No secrets in logs (debug mode safe)

**Audio Files:**
- Cleaned from `/tmp/whisprbar*` after transcription
- Not persisted unless explicitly saved

**History Log:**
- May contain sensitive transcripts
- Stored at `~/.local/share/whisprbar/history.jsonl`
- User should manage retention policy

---

## Contributing

**Development Workflow:**
1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes to relevant modules
3. Test thoroughly (see Testing Strategy)
4. Update documentation (WORKLOG.md, CHANGELOG.md)
5. Commit with clear message (conventional commits preferred)
6. Push and create PR

**Commit Message Format:**
```
<type>: <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

**Code Review Checklist:**
- [ ] PEP 8 compliant
- [ ] Type hints on public functions
- [ ] Docstrings on complex functions
- [ ] No code duplication
- [ ] Tests pass
- [ ] Documentation updated

---

## Versioning

**Semantic Versioning:** `MAJOR.MINOR.PATCH`

- **MAJOR:** Breaking changes (config schema, API)
- **MINOR:** New features (backwards compatible)
- **PATCH:** Bug fixes

**Version Management:**
- Source of truth: `whisprbar/__init__.py:__version__`
- Update before release
- Tag in git: `git tag v1.0.0`
- Update CHANGELOG.md

---

## Support & Troubleshooting

**Enable debug logging:**
```bash
WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py
```

**Check dependencies:**
```bash
.venv/bin/python whisprbar.py --diagnose
```

**Validate audio hardware:**
```bash
python3 -m sounddevice
arecord -l
```

**Check GTK/AppIndicator:**
```bash
python3 -c "import gi; gi.require_version('AppIndicator3', '0.1'); from gi.repository import AppIndicator3; print('OK')"
```

**Verify API key:**
```bash
cat ~/.config/whisprbar.env
```

**Check temp files:**
```bash
ls -la /tmp/whisprbar*
```

**Reset config:**
```bash
mv ~/.config/whisprbar.json ~/.config/whisprbar.json.backup
# Restart app, new default config will be created
```

---

**Last Updated:** 2025-10-04
**Maintained by:** Claude Code
**Version:** V6 (Modular Architecture)
