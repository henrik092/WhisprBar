# WhisprBar

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/henrik092/whisprBar/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](https://www.linux.org/)

**WhisprBar** is a Linux system tray application for voice-to-text transcription. Record audio with a global hotkey, transcribe using multiple AI backends, and automatically paste the result into any application.

**New to WhisprBar?** Check out the [Quick Start Guide](QUICK_START_GUIDE.md) for a 5-minute setup!

![WhisprBar Demo](docs/demo.gif)

> If you find WhisprBar useful, please give it a star on GitHub! ⭐

---

## Features

### Core Functionality
- **Global Hotkey Recording**: Press F9 (configurable) to record, release to transcribe
- **Multiple Transcription Backends**:
  - **OpenAI Whisper API** - Cloud-based, fast, accurate
  - **faster-whisper** - Local CPU/GPU, offline, private
  - **sherpa-onnx** - Streaming transcription (experimental)
- **Auto-Paste**: Automatically pastes transcription into active window (X11) or clipboard (Wayland)
- **Voice Activity Detection (VAD)**: Filters silence and background noise
- **Noise Reduction**: Improves transcription quality in noisy environments
- **Live Overlay**: Real-time transcription preview window

### Advanced Features
- **Audio Chunking**: Parallel processing for long recordings (>30s)
- **Text Postprocessing**: Automatic spacing and capitalization fixes
- **Multi-Language Support**: Configure transcription language (de, en, etc.)
- **Audio Device Selection**: Choose input device from settings
- **History Logging**: All transcriptions saved to `~/.local/share/whisprbar/history.jsonl`
- **Update Checker**: Automatic notification of new releases

### User Interface
- **System Tray Integration**: AppIndicator (Ubuntu/GNOME) or PyStray fallback
- **Settings Dialog**: Configure all options via GUI
- **First-Run Diagnostics**: Automatic environment validation
- **Hotkey Capture**: Visual interface to set custom hotkeys
- **Notification Support**: Desktop notifications for status updates

---

## What's New in V6

WhisprBar V6 is a **complete architectural rewrite** that transforms the previous 4,017-line monolithic codebase into a professional, modular Python package with 11 focused modules.

### Key Improvements

✅ **100% Feature Parity**: All V5 features preserved and functional
✅ **Modular Architecture**: 11 focused modules (200-800 lines each)
✅ **Better Maintainability**: Clear separation of concerns
✅ **Improved Documentation**: 33KB developer guide + inline docs
✅ **Type Hints**: Better IDE support and code clarity
✅ **Zero Breaking Changes**: V5 configs work without modification

See [CHANGELOG.md](CHANGELOG.md) for complete details.

---

## Quick Start

### Prerequisites

**Linux Only** - WhisprBar is designed for Linux desktop environments (X11 or Wayland).

**System Requirements**:
- Python 3.8 or higher
- Audio input device (microphone)
- OpenAI API key (for OpenAI backend) OR locally installed faster-whisper/sherpa-onnx

### Installation

1. **Clone Repository**:
   ```bash
   git clone https://github.com/henrik092/whisprBar.git WhisperBar
   cd WhisperBar
   ```

2. **Run Installer**:
   ```bash
   ./install.sh
   ```

   The installer will:
   - Check and install system dependencies
   - Create Python virtual environment
   - Install Python packages
   - Configure OpenAI API key (if using OpenAI backend)
   - Install launcher to `~/.local/bin/whisprbar`
   - Create desktop entry

3. **Launch Application**:
   ```bash
   ~/.local/bin/whisprbar
   ```

   Or search for "WhisprBar" in your application menu.

### Configuration

#### OpenAI API Key (Required for OpenAI Backend)

Edit `~/.config/whisprbar.env`:

```bash
OPENAI_API_KEY=sk-proj-...
```

Set file permissions for security:
```bash
chmod 600 ~/.config/whisprbar.env
```

#### Alternative: Local Transcription (No API Key Required)

Install faster-whisper for offline transcription:

```bash
.venv/bin/pip install faster-whisper
```

Then in settings, change transcription backend to "faster-whisper".

---

## Usage

### Basic Workflow

1. **Start WhisprBar**: Launch from application menu or terminal
2. **Check Tray Icon**: Look for WhisprBar icon in system tray
3. **Press Hotkey**: Press and hold F9 (default)
4. **Speak**: Record your audio
5. **Release Hotkey**: Transcription begins automatically
6. **Result**: Text is pasted into active window (or copied to clipboard on Wayland)

### Settings

Right-click the tray icon and select **Settings** to configure:

- **Language**: Transcription language (de, en, etc.)
- **Hotkey**: Change recording hotkey
- **Audio Device**: Select input device
- **Transcription Backend**: OpenAI, faster-whisper, or sherpa-onnx
- **VAD Settings**: Voice activity detection sensitivity and auto-stop
- **Chunking**: Enable parallel processing for long audio
- **Postprocessing**: Text cleanup options
- **Noise Reduction**: Enable/disable noise filtering
- **Live Overlay**: Show real-time transcription preview
- **Auto-Paste**: Configure paste behavior
- **Notifications**: Toggle desktop notifications

### Hotkeys

Default: **F9** (press to start recording, release to stop)

Supported keys:
- F-keys: F1-F12, F13-F20
- Modifiers: Ctrl, Shift, Alt, Super (can be combined)
- Examples: `F9`, `Ctrl+Shift+R`, `Alt+F12`

Change hotkey via Settings dialog or tray menu.

### Auto-Paste Modes

**X11** (Full Functionality):
- `Ctrl+V` - Standard paste
- `Ctrl+Shift+V` - Paste without formatting
- `Shift+Insert` - Alternative paste
- `type` - Type character by character
- `auto` - Detect best method (default)

**Wayland** (Limited):
- `clipboard` - Copy to clipboard only (user must paste manually)

Note: Wayland's security model prevents automated window control, so auto-paste is clipboard-only.

---

## Architecture

WhisprBar V6 uses a modular architecture with clear separation of concerns:

```
whisprbar/                       # Python package
├── __init__.py                  # Version and exports
├── config.py                    # Configuration management
├── utils.py                     # Shared utilities (icons, diagnostics, etc.)
├── audio.py                     # Audio recording and processing
├── transcription.py             # All transcription backends
├── hotkeys.py                   # Global hotkey handling
├── paste.py                     # Auto-paste functionality
├── ui.py                        # GUI components (settings, overlay, diagnostics)
├── tray.py                      # System tray integration
└── main.py                      # Application orchestration

whisprbar.py                     # Legacy entry point (backwards compat)
whisprbar-launcher.sh            # Shell launcher script
install.sh                       # Installation script
```

### Module Responsibilities

| Module | Lines | Responsibility |
|--------|-------|----------------|
| `config.py` | 202 | Load/save configuration, environment variables |
| `utils.py` | 487 | Icons, history, updates, platform detection, diagnostics |
| `audio.py` | 687 | Recording, VAD, noise reduction, chunking |
| `transcription.py` | 1,129 | All backends, postprocessing, text cleanup |
| `hotkeys.py` | 482 | Hotkey parsing, listener, capture interface |
| `paste.py` | 336 | Paste detection, execution (X11/Wayland) |
| `ui.py` | 1,247 | Settings dialog, overlay, diagnostics wizard |
| `tray.py` | 629 | Tray backends (AppIndicator/PyStray), menus |
| `main.py` | 536 | Application lifecycle, orchestration, callbacks |

**Total**: 5,768 lines (vs 4,017 in V5 monolith)

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.

---

## Platform Support

### Operating Systems

| OS | Status | Notes |
|----|--------|-------|
| Ubuntu 22.04+ | ✅ Fully Supported | Recommended platform |
| Debian 11+ | ✅ Fully Supported | |
| Fedora 38+ | ✅ Fully Supported | |
| Arch Linux | ✅ Fully Supported | |
| Other Linux | ⚠️ Untested | Should work with dependencies |
| macOS | ❌ Not Supported | Linux only |
| Windows | ❌ Not Supported | Linux only |

### Desktop Environments

| DE | Tray | Auto-Paste | Notes |
|----|------|------------|-------|
| GNOME | ✅ | ✅ (X11) / ⚠️ (Wayland) | Requires AppIndicator extension |
| KDE Plasma | ✅ | ✅ | Full support |
| Cinnamon | ✅ | ✅ | Panel restart may be needed for icon order |
| XFCE | ✅ | ✅ | Requires statusnotifier plugin |
| MATE | ✅ | ✅ | Full support |
| i3/Sway | ⚠️ | ⚠️ | Limited tray support |

### Display Servers

| Server | Status | Auto-Paste | Notes |
|--------|--------|------------|-------|
| X11 | ✅ Full Support | ✅ xdotool | Best experience |
| Wayland | ⚠️ Limited | ⚠️ Clipboard only | Security limitation |

---

## Configuration Files

### `~/.config/whisprbar.json`

Main configuration file (JSON format):

```json
{
  "language": "de",
  "device_name": null,
  "hotkey": "F9",
  "notifications_enabled": false,
  "auto_paste_enabled": true,
  "paste_sequence": "auto",
  "paste_delay_ms": 250,
  "use_vad": true,
  "vad_energy_ratio": 0.05,
  "vad_bridge_ms": 300,
  "vad_auto_stop_enabled": false,
  "vad_auto_stop_silence_seconds": 2.0,
  "chunking_enabled": true,
  "chunk_duration_seconds": 30.0,
  "postprocess_enabled": true,
  "noise_reduction_enabled": true,
  "transcription_backend": "openai",
  "faster_whisper_model": "large",
  "live_overlay_enabled": false
}
```

### `~/.config/whisprbar.env`

Environment variables and secrets (KEY=VALUE format):

```bash
OPENAI_API_KEY=sk-proj-...
WHISPRBAR_HOME=/path/to/custom/home  # Optional
```

**Security**: Set mode 600 to restrict access:
```bash
chmod 600 ~/.config/whisprbar.env
```

### `~/.local/share/whisprbar/history.jsonl`

Transcription history (JSONL format, append-only):

```json
{"timestamp": "2025-10-15T12:34:56", "text": "Hello world", "duration": 2.5}
```

---

## Troubleshooting

### Diagnostics

Run built-in diagnostics to check configuration:

```bash
~/.local/bin/whisprbar --diagnose
```

This checks:
- Session type (X11 vs Wayland)
- Tray backend availability
- Auto-paste capability
- Audio devices
- OpenAI API key configuration
- System dependencies

### Enable Debug Logging

```bash
WHISPRBAR_DEBUG=1 ~/.local/bin/whisprbar
```

Debug output is printed to console.

### Common Issues

#### 1. Tray Icon Not Appearing

**GNOME**: Install AppIndicator extension:
```bash
sudo apt install gnome-shell-extension-appindicator
```

**XFCE**: Enable statusnotifier plugin:
```bash
xfce4-panel --add=statusnotifier
```

**Cinnamon**: Restart panel:
```bash
cinnamon --replace &
```

#### 2. Hotkey Not Working

- Check that no other application uses the same hotkey
- Try a different hotkey via Settings
- On Wayland, some global hotkeys may be restricted

#### 3. Transcription Fails

**OpenAI Backend**:
- Verify API key in `~/.config/whisprbar.env`
- Check internet connection
- Ensure API key has credits

**faster-whisper**:
- Install backend: `.venv/bin/pip install faster-whisper`
- Select "faster-whisper" in Settings

#### 4. Auto-Paste Not Working

**X11**:
- Install xdotool: `sudo apt install xdotool`
- Try different paste sequence in Settings

**Wayland**:
- Auto-paste is clipboard-only (paste manually with Ctrl+V)
- Install wl-clipboard: `sudo apt install wl-clipboard`

#### 5. No Audio Recorded

- Check microphone permissions
- Test with: `arecord -l` (list devices)
- Select correct device in Settings
- Check system audio settings

#### 6. Poor Transcription Quality

- Enable noise reduction in Settings
- Adjust VAD sensitivity
- Use faster-whisper "large" model for better accuracy
- Speak clearly and reduce background noise

### Reset Configuration

To reset to defaults:

```bash
# Backup current config
mv ~/.config/whisprbar.json ~/.config/whisprbar.json.backup

# Restart app (will create new default config)
~/.local/bin/whisprbar
```

---

## Development

### Setup Development Environment

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

### Run from Source

```bash
# Run directly
.venv/bin/python whisprbar.py

# With debug logging
WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py

# Run diagnostics
.venv/bin/python whisprbar.py --diagnose

# Check version
.venv/bin/python whisprbar.py --version
```

### Project Structure

See [CLAUDE.md](CLAUDE.md) for comprehensive developer documentation including:
- Module architecture and responsibilities
- Development commands
- Common tasks
- Code modification guidelines
- Testing strategy

### Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style guidelines (PEP 8)
- Pull request process
- Testing requirements
- Bug reporting guidelines

---

## Dependencies

### Python Packages

```
openai >= 1.0.0           # OpenAI Whisper API
faster-whisper >= 0.9.0   # Local transcription (optional)
sherpa-onnx >= 1.9.0      # Streaming transcription (optional)
pynput >= 1.7.6           # Hotkey handling
sounddevice >= 0.4.6      # Audio capture
numpy >= 1.24.0           # Audio processing
webrtcvad >= 2.0.10       # Voice activity detection
noisereduce >= 3.0.0      # Noise reduction
pystray >= 0.19.0         # Tray icon (fallback)
Pillow >= 10.0.0          # Icon generation
pyperclip >= 1.8.2        # Clipboard access
```

### System Packages (Ubuntu/Debian)

```bash
sudo apt install python3 python3-venv python3-pip \
                 python3-gi python3-gi-cairo \
                 gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
                 xdotool libnotify-bin portaudio19-dev
```

**Optional (Wayland)**:
```bash
sudo apt install wl-clipboard wtype
```

---

## Security

### API Key Storage

- API keys stored in `~/.config/whisprbar.env` (separate from config)
- **Recommended**: Set mode 600: `chmod 600 ~/.config/whisprbar.env`
- Never committed to git (.gitignore configured)
- Not logged even in debug mode

### Audio Data

- Audio stored in memory during recording
- No persistent audio files (deleted after transcription)
- History log may contain sensitive transcriptions
- History location: `~/.local/share/whisprbar/history.jsonl`

### Permissions

WhisprBar requires:
- Microphone access (audio recording)
- Clipboard access (auto-paste)
- Keyboard access (global hotkey)
- Network access (OpenAI API - optional)

---

## Known Limitations

### Wayland Limitations

**Problem**: Wayland's security model prevents window control
**Impact**: Auto-paste is clipboard-only (no direct text insertion)
**Workaround**: User must manually paste with Ctrl+V
**Status**: Cannot be fixed (Wayland design limitation)

### Other Limitations

- **Single Hotkey**: Only one global hotkey supported
- **VAD Sensitivity**: May require tuning for different environments
- **Tray Icon Ordering**: Desktop-dependent, not controllable
- **No macOS/Windows Support**: Linux-only application

---

## Performance

### Resource Usage

| Metric | Value |
|--------|-------|
| Idle RAM | ~80 MB |
| Recording RAM | ~100 MB |
| Transcribing RAM | ~150-500 MB (backend-dependent) |
| Startup Time | ~3-5 seconds (cold start) |
| Hotkey Latency | <100 ms |

### Transcription Speed

- **OpenAI API**: ~2-5 seconds (network-dependent)
- **faster-whisper**: ~5-15 seconds (model-dependent)
- **sherpa-onnx**: ~1-3 seconds (streaming)

---

## FAQ

### Q: Does WhisprBar work on Windows/macOS?
**A**: No, WhisprBar is Linux-only. The system integration (tray, hotkeys, auto-paste) relies on Linux-specific technologies.

### Q: Can I use WhisprBar offline?
**A**: Yes, install faster-whisper for local transcription:
```bash
.venv/bin/pip install faster-whisper
```
Then select "faster-whisper" backend in Settings.

### Q: Is my audio data sent to the cloud?
**A**: Only if you use the OpenAI backend. With faster-whisper or sherpa-onnx, all processing is local.

### Q: How accurate is the transcription?
**A**: Accuracy depends on:
- Audio quality (clear speech, low noise)
- Backend (OpenAI is generally most accurate)
- Model size (faster-whisper "large" > "medium" > "small")
- Language (some languages better supported than others)

### Q: Can I transcribe multiple languages?
**A**: Yes, change language in Settings. OpenAI Whisper supports 90+ languages.

### Q: Why doesn't auto-paste work on Wayland?
**A**: Wayland's security model prevents applications from controlling other windows. This is a design limitation, not a bug. Text is copied to clipboard instead.

### Q: How do I backup my configuration?
**A**: Copy these files:
```bash
~/.config/whisprbar.json
~/.config/whisprbar.env
~/.local/share/whisprbar/history.jsonl
```

### Q: Can I use multiple hotkeys for different actions?
**A**: Currently no. Only one global hotkey is supported. This may be added in a future version.

---

## License

WhisprBar is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2024 Henrik W (henrikw092@gmail.com)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Credits

- **Author**: Henrik W (henrik092)
- **V6 Refactoring**: Claude Code (AI-assisted development)
- **Transcription**: OpenAI Whisper, faster-whisper, sherpa-onnx
- **System Tray**: pystray, AppIndicator3
- **Audio**: sounddevice, webrtcvad, noisereduce

---

## Links

- **GitHub Repository**: [github.com/henrik092/whisprBar](https://github.com/henrik092/whisprBar)
- **Quick Start Guide**: [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) - 5-minute setup for new users
- **Issues**: [GitHub Issues](https://github.com/henrik092/whisprBar/issues)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md) - Version history
- **Developer Guide**: [CLAUDE.md](CLAUDE.md) - Architecture and development
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines

---

## Support

### Reporting Issues

1. Run diagnostics: `~/.local/bin/whisprbar --diagnose`
2. Collect debug log: `WHISPRBAR_DEBUG=1 ~/.local/bin/whisprbar 2>&1 | tee debug.log`
3. Gather system info: `uname -a`, `echo $XDG_SESSION_TYPE`
4. Open issue on GitHub with logs and system info

### Community

- GitHub Discussions (coming soon)
- Issue Tracker: [GitHub Issues](https://github.com/henrik092/whisprBar/issues)

---

**Built with ❤️ for Linux users who value privacy and convenience.**
