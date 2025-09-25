# WhisprBar

WhisprBar is a tray-based voice-to-text assistant for Linux desktops. Press a global hotkey to capture audio, transcribe it via OpenAI Whisper, and automatically copy/paste the transcript into the current application.

## Features
- Tray icon with AppIndicator/PyStray backends for Cinnamon, GNOME, KDE, XFCE.
- Global hotkey recording with on-the-fly device selection.
- OpenAI transcription pipeline with clipboard copy and optional auto-paste heuristics.
- Voice activity detection (optional) to trim silence and avoid empty API calls.
- Persistent settings (`~/.config/whisprbar.json`) and transcription history (`~/.local/share/whisprbar/history.jsonl`).
- First-run diagnostics wizard + CLI `--diagnose` command for quick environment checks.

## Requirements
- Linux desktop with working audio input and tray support.
- Python 3.10+ (virtualenv recommended).
- System packages: `python3-gi`, AppIndicator libs, `xdotool` (X11), `wl-clipboard` (Wayland), `libnotify-bin`, `zenity`, ALSA/PipeWire tools. See `INSTALL.md` for distro-specific package lists.
- An OpenAI API key stored in `~/.config/whisprbar.env`.

## Quickstart
```bash
git clone https://github.com/<your-account>/whisprbar.git
cd whisprbar
chmod +x install.sh
./install.sh
```

The installer checks system dependencies, creates a virtual environment, installs Python requirements, and offers to write the launcher + desktop entry. Provide your `OPENAI_API_KEY` when prompted.

Launch WhisprBar via your menu entry or:

```bash
~/.local/bin/whisprbar
```

On first launch a diagnostics window appears, summarising session type, tray backend, auto-paste readiness, audio devices, and API key configuration. You can rerun it anytime via the tray menu (`Diagnostics...`) or from the CLI:

```bash
~/.local/bin/whisprbar --diagnose
```

## Configuration
- Runtime settings: `~/.config/whisprbar.json`
- Environment secrets: `~/.config/whisprbar.env`
- History log: `~/.local/share/whisprbar/history.jsonl`

Use the tray settings dialog to adjust language, microphone, auto-paste mode, notifications, VAD, and hotkey bindings.

## Development Notes
- Dependencies are listed in `requirements.txt`. Optional VAD support requires `webrtcvad`.
- Run inside the virtualenv for local testing:
  ```bash
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -r requirements.txt
  python whisprbar.py
  ```
- Enable verbose logs with `WHISPRBAR_DEBUG=1`.
- `WORKLOG.md` tracks feature progress; `DEPLOY_PLAN.md` documents the release roadmap.

## License
WhisprBar is released under the MIT License. See `LICENSE` for details.

## Security
- Never commit API keys or personal data. The `.gitignore` excludes virtualenvs, caches, and `.env` files by default.
- Users should store credentials only in `~/.config/whisprbar.env`.

## Next Steps
- Finalise dependency metadata (`requirements.txt` vs. `pyproject.toml`).
- Prototype packaging targets (AppImage, Flatpak, AUR) per `DEPLOY_PLAN.md`.
- Set up CI/CD (GitHub Actions) for builds, diagnostics, and release artifacts.
# whisprBar
