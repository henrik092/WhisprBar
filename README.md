# WhisprBar

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/henrik092/whisprBar/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](https://www.linux.org/)

A Linux system tray app for voice-to-text transcription. Press a hotkey, speak, release -- your text is automatically pasted into the active window.

## Features

- **Multiple backends**: Deepgram Nova-2 (<300ms), OpenAI Whisper, ElevenLabs Scribe, faster-whisper (local/offline), sherpa-onnx (streaming)
- **Global hotkey**: Press F9 (configurable) to record, release to transcribe and auto-paste
- **Auto-paste**: Pastes directly into the active window (X11) or clipboard (Wayland)
- **Audio processing**: Voice activity detection, noise reduction, chunked parallel processing for long recordings
- **Live overlay**: Real-time transcription preview
- **Flow Mode**: Context-aware cleanup, spoken commands, snippets, dictionary replacements, and optional rewrite assistance before paste
- **Scratchpad**: Local note window for collecting, editing, and copying dictated text
- **System tray**: AppIndicator (GNOME/Ubuntu) with PyStray fallback
- **Multi-language**: 90+ languages supported (backend-dependent)
- **Privacy-friendly**: Use faster-whisper for fully offline, local transcription

## Installation

```bash
git clone https://github.com/henrik092/whisprBar.git WhisperBar
cd WhisperBar
./install.sh
```

The installer handles system dependencies, Python venv, and creates a desktop entry.

Launch via application menu or:

```bash
~/.local/bin/whisprbar
```

### API Key Setup

For cloud backends, edit `~/.config/whisprbar.env`:

```bash
DEEPGRAM_API_KEY=...        # Recommended - fastest
OPENAI_API_KEY=sk-proj-...  # Alternative
ELEVENLABS_API_KEY=sk_...   # Alternative
```

```bash
chmod 600 ~/.config/whisprbar.env
```

For **offline use**, no API key needed -- just install faster-whisper and select it in Settings.

## Usage

1. Launch WhisprBar (tray icon appears)
2. Press and hold **F9**
3. Speak
4. Release F9 -- text is transcribed and pasted

Right-click the tray icon for **Settings** (language, hotkey, backend, VAD, noise reduction, etc.).

### Flow Mode

Flow Mode turns the raw transcript into paste-ready text before insertion. It can:

- detect the active app and apply a matching profile for terminal, editor, chat, email, or notes
- replace custom phrases from `~/.config/whisprbar/dictionary.json`
- expand spoken snippets from `~/.config/whisprbar/snippets.json`
- react to spoken commands such as "make this professional", "make this shorter", "as list", "clipboard only", "press enter", or "new line"
- apply deterministic formatting, including punctuation words, simple lists, and backtrack phrases
- optionally call a rewrite provider for stronger style cleanup when `OPENAI_API_KEY` is configured

Flow Mode is available from the **Flow** tab in Settings. The local formatting, dictionary,
snippets, command detection, and scratchpad features work offline. Optional cloud rewriting is
disabled by default and only runs when enabled explicitly.

Example dictionary file:

```json
[
  {"phrase": "whisper bar", "replacement": "WhisprBar"},
  {"phrase": "pull request", "replacement": "PR"}
]
```

Example snippets file:

```json
[
  {"trigger": "my email signature", "text": "Best regards,\nRik"}
]
```

## Platform Support

| | X11 | Wayland |
|---|---|---|
| Tray icon | Full | Full |
| Auto-paste | Full (xdotool) | Clipboard only |
| Hotkeys | Full | Full |
| Flow context awareness | Active-window profile detection | Safe default profile |

Tested on Ubuntu, Debian, Fedora, Arch with GNOME, KDE, Cinnamon, XFCE, MATE.

**Wayland limitation**: Auto-paste copies to clipboard only (Wayland prevents automated window control).

## Troubleshooting

```bash
# Run diagnostics
~/.local/bin/whisprbar --diagnose

# Debug logging
WHISPRBAR_DEBUG=1 ~/.local/bin/whisprbar
```

See [common issues](https://github.com/henrik092/whisprBar/issues) or open a new issue with diagnostics output.

## Development

```bash
python3 -m venv --system-site-packages .venv   # --system-site-packages required for GTK
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python whisprbar.py
```

See [CLAUDE.md](CLAUDE.md) for architecture docs.

## License

[MIT](LICENSE) -- Copyright (c) 2024 Henrik W (henrik092)
