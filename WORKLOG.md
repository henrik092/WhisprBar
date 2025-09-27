# WhisprBar Work Log

## Starting Point
- Reviewed the instruction documents `anleitung 1 .md` and `anleitung 2 .md`.
- Built the new tray application `whisprbar.py`: global hotkey recording, OpenAI transcription, clipboard/auto-paste integration, tray menu, configuration file, and history tracking.

## Implemented Features
- Persistent configuration in `~/.config/whisprbar.json` and history logging in `~/.local/share/whisprbar/history.jsonl`.
- Global hotkey capture via `pynput` (function keys and single characters) with a dynamic tray menu.
- Microphone selection by name, language toggle (de/en), auto-paste toggle, hotkey recording, shortcuts to open history/config files.
- Tray icon colours: white = idle, red = recording; tooltips show the active hotkey.
- Audio pipeline using `sounddevice` (16 kHz mono), optional WebRTC VAD, WAV export, and `openai` transcription.
- Transcript handling: copy to clipboard, optional auto-paste (`xdotool` or `pynput`), history with duration/word count, terminal log line `[TRANSCRIPT]`.
- Debug logs on terminal launch (`WHISPRBAR_DEBUG=1` or automatic TTY detection), duration/word counters, ASCII notifications.
- Launcher `whisprbar-launcher.sh`: detects venv, sources `.env`, adjusts `PYTHONPATH` for system GI bindings, handles logging, and launches via the desktop entry.
- Updated installation notes (`INSTALL.md`) covering python3-gi, AppIndicator, xdotool, x11-utils.

## Key Changes
- Notifications are disabled by default (`notifications_enabled=false`).
- Auto-paste appends a space to each transcript by default.
- Auto-paste modes: `auto` (window heuristic via xdotool/xprop), `ctrl_v`, `ctrl_shift_v`, `shift_insert`, `type`.
- Runtime checks flag missing tools (xdotool, python3-gi) and rebuild the tray menu after each action.
- Wayland detection degrades auto-paste to “clipboard only,” updates the tray status, and shows warnings when switching modes.
- Tray backend discovery (AppIndicator/GTK) uses resilient initialization and logging; menu and tooltip expose the active backend.
- GTK settings window covers language, microphone, paste mode, toggles for notifications/auto-paste/VAD, and Wayland hints.
- Tray loops are blocking again: AppIndicator uses `GLib.MainLoop`, PyStray keeps `icon.run`, preventing the program from exiting immediately.

## Known Limitations
- PyStray on GTK still shows flaky context menus under Cinnamon (GLib-GIO warning); GNOME requires the AppIndicator extension or no tray icon appears.
- Undo, typed-input mode, smart injection, history UI, and other features from `voice_input_tool.py` are not yet ported.

## Bugs & Fixes
- Tray icon vanished right after launch (main thread continued, tray loop was running in a daemon thread). Fix: AppIndicator now runs `GLib.MainLoop`, PyStray reinstates `icon.run(setup=...)` on the main thread.
- `ImportError: No module named 'gi'` during PyStray import. Fix: prepend system GI paths to `sys.path` before importing and keep the AppIndicator import optional.
- GLib-GIO warnings on GNOME without AppIndicator support. Fix: use the AppIndicator backend when available; otherwise auto-switch to PyStray fallback and log hints.

## Next Key Steps
1. Replace PyStray in the long term (native Gtk/AppIndicator) and port missing features from `voice_input_tool.py` (undo/history UI, etc.).
2. Implement a system check dialog and first-run wizard (hotkey/mic tests, provider selection, diagnostic reports).
3. Optionally add auto-silence recording, richer config UI, multilingual support, and additional providers (local Whisper, Deepgram, ...).
4. Evaluate a Cinnamon-specific panel applet (JS/DBus) to gain native placement and interaction control.

## Update Tray Icon
- Tray icon now has a subtle circular background with a white outline for visibility on light and dark themes.
- AppIndicator backend uses an early-sorting ID (`aa-whisprbar`) and sets `ordering-index=0` to keep the icon left-aligned where supported; failures are logged for debugging.

## Update Settings
- GTK settings window still saves on “Save” and now offers a hotkey section: display the current shortcut, capture a new one via “Change,” and reset to F9 with “Reset.”
- Hotkey capture reuses the global listener; once recording finishes the UI updates, and closing the dialog stops the listener cleanly.
- Tray menus now show only the current hotkey; hotkey changes, history, and config access moved into the settings UI to keep the context menu minimal.
- Settings fields (hotkey, auto-paste, paste mode, VAD) include info icons or tooltips describing behaviour and constraints.
- Hotkeys support modifier combinations (Ctrl/Shift/Alt/Super); listener and capture dialog detect multi-key combos and store them as `CTRL+F9`, etc.
- During hotkey capture existing shortcuts are disabled so recordings do not start accidentally.

## Update Voice Activity Detection
- Integrated `webrtcvad` trims recordings reliably: 30 ms frames with ~100 ms context remove silence before/after speech without losing short pauses.
- Debug logs report the trimmed duration; if detection fails or speech is absent, the algorithm falls back to the original audio.
- Recordings shorter than 250 ms of speech are skipped to avoid unnecessary API calls.

## Deployment Preparations
- Added `DEPLOY_PLAN.md` documenting system dependencies, installer plans, and release preparation tasks.

## Deployment Updates
- Expanded section 1 of the deploy plan (desktop/package matrix, scope, runtime checks) as groundwork for automated installers.
- Created `install.sh`: detects package managers (apt/dnf/pacman), optionally installs missing system packages, sets up `.venv` with `requirements.txt`, writes `~/.config/whisprbar.env`, and offers launcher/desktop setup.
- Added `requirements.txt` and fully restructured `INSTALL.md` (installer quickstart, package overview, manual fallback, troubleshooting).
- Installer now detects non-interactive runs, switches to auto mode, and collects missing `OPENAI_API_KEY` values via GUI (`zenity`/`kdialog`) to support double-click installs.
- System package checks include `zenity` so GUI prompts work without prior installation.
- Fixed missing-package output (`print_missing_packages` separates items cleanly) so apt/dnf/pacman can consume the list directly.
- Revised the `.env` writer: installer now always writes `OPENAI_API_KEY` and `WHISPRBAR_HOME` in the desired format, preserves other entries, and avoids broken shell exports.
- Installer repairs legacy env files with misplaced key lines (`configure_env_file` detects legacy format) and shows the API key in the terminal prompt so empty input is less likely.
- Launcher now surfaces errors graphically (`notify-send`/`zenity`) and aborts via `fail()` so double-click users understand failure reasons.
- Desktop installer writes the `.desktop` Exec path to the user location, runs `update-desktop-database`/`xdg-desktop-menu forceupdate`, ensuring the menu entry appears immediately and targets the correct launcher.
- Deploy plan documents why terminal prompts show the API key (avoid blank entries) while GUI prompts stay masked.
- Installer optionally launches WhisprBar after the summary (prompt now English) and starts it via the launcher when confirmed; auto/dry-run skip the prompt.
- `whisprbar.py --diagnose` now returns a complete CLI report (session, tray, auto-paste, notifications, audio, API key, file permissions) with remediation hints.
- GTK diagnostic window acts as a first-run wizard: runs the same checks, offers “Run again,” sets `first_run_complete`, and appears in the tray menu (`Diagnostics...`).
- Non-GTK fallback prints the diagnostic report to the terminal; configuration remembers the result (`first_run_complete`).
- Launcher accepts arguments (e.g., `~/.local/bin/whisprbar --diagnose`) and forwards them to `whisprbar.py`.
- README now includes an overview, quickstart, diagnostic notes; `.gitignore` covers venv/cache/notes; MIT licence marked as a to-do for GitHub readiness.

## Fix VAD Pause Dropouts
- `apply_vad` keeps everything between the first and last speech segments instead of cutting quiet mid-sections.
- Padding is configurable (`vad_padding_ms`, default 200 ms) and uses VAD mode 1, preventing soft syllables from disappearing after long pauses.
- The VAD result check reverts to original audio when the trimmed recording becomes very short (<40% of original); debug logs record the decision.

## Improve VAD Reliability
- Additional RMS analysis restores quiet speech parts when WebRTC VAD misses them after longer pauses; silent regions remain trimmed.
- Configurable thresholds (`vad_energy_ratio`, `vad_energy_floor`, `vad_bridge_ms`) merge soft syllables and short gaps without removing entire recordings.
- Debug logs state how many frames the energy heuristic adds, simplifying later tuning.
- Dynamic thresholds rely on the RMS distribution (75th percentile) and add a secondary relaxed detector (`vad_min_energy_frames`) so trailing phrases survive longer pauses.

## Settings UI Enhancements
- Added VAD sliders to the settings window (sensitivity, pause bridging, noise guard) accessible via the tray menu.
- Values map directly to the config (`vad_energy_ratio`, `vad_bridge_ms`, `vad_min_energy_frames`) and auto-disable when VAD is off or unavailable.
- Tooltips explain what moving left/right does (higher tolerance vs. faster trimming) and show recommended starting values.
- Placed the recommended default next to the info icon so users can see it without opening the tooltip.
- Updated defaults: sensitivity 0.02, pause bridging 180 ms, noise guard 2 frames—better balance between pause trimming and quiet speech.

## Fix VAD Crash After Long Pauses
- `apply_vad` now normalises audio frames to 1D so remaining blocks (queue yields `(n, 1)` arrays) concatenate safely.
- Eliminated `ValueError: arrays must have same number of dimensions`; subsequent recordings succeed.
- `transcribe_audio` reports audio throughput (`input`, `output`, `saved`, `ratio`) regardless of VAD state.
- VAD now segments multiple speech islands, removes long pauses between them, and logs segment lengths for inspection.

## 2025-09-25 GitHub Preparation
- Extended the deployment plan with a GitHub playbook (create repo, connect remote, publish release, set up community assets, configure branch protection).
- Generated the MIT licence file (`LICENSE`) with copyright attribution.
- Documented outstanding README/CHANGELOG/template work inside the plan so the first public push stays organised.

## 2025-09-25 Documentation Localization
- Translated all publishable documents (`AGENTS.md`, `INSTALL.md`, `DEPLOY_PLAN.md`, `WORKLOG.md`) into English to satisfy GitHub readiness requirements.
- Updated `README.md` to reference the MIT licence explicitly and adjusted `whisprbar.desktop` metadata to English wording.
- Ran repo-wide checks to confirm no remaining German strings remain in tracked files.

## 2025-09-25 Update Notifications
- Added an asynchronous GitHub release check (`whisprbar.py`) that alerts when a newer tag is available and suggests `git pull && ./install.sh`.
- Recorded update instructions in `README.md` and `INSTALL.md` so users know how to refresh their local installations.
- Noted the new notifier in `DEPLOY_PLAN.md` to track distribution readiness.
- Update alerts now bypass the general notification toggle, ensuring upgrade prompts are always delivered.

## 2025-09-25 Versioning Guidelines
- Documented the release workflow in `AGENTS.md` (semantic versioning, `APP_VERSION` source of truth, tagging convention).
- Established the rule to update `WORKLOG.md` and the future `CHANGELOG.md` alongside every version bump.
- Reminded contributors to push matching `vX.Y.Z` tags so the in-app update notifier can detect new releases.

## 2025-09-25 Changelog Setup
- Created `CHANGELOG.md` following the Keep a Changelog format with the initial `0.1.0` release entry and compare link.
- Updated `AGENTS.md` so future releases explicitly update the changelog and maintain an "Unreleased" section during development.
- Noted that changelog updates go hand-in-hand with worklog entries for each version bump.

## 2025-09-25 README Streamlining
- Trimmed the README to focus on essentials (features, quickstart, configuration), moving contributor-oriented notes elsewhere.
- Added a direct link to the OpenAI API key management page so new users can generate credentials quickly.

## 2025-09-26 Recording Tail Preservation
- Updated the audio stream callback to keep queueing frames while the capture queue is active so manual stops retain the full spoken tail even when VAD is disabled.
- Defer queue teardown until after the input stream stops and drains, eliminating the clipped endings reported after the latest VAD changes.
- Confirmed the tray UI still reflects the stopped state immediately while background transcription continues as before.

## 2025-09-26 Queue Drain Grace Period
- Added a 200 ms grace window while draining the audio queue so late PortAudio callbacks have time to flush their frames into the recorder before teardown.
- Guarded the drain loop with a short timeout to avoid hangs while still capturing the final spoken words after long silences.

## 2025-09-27 Release v0.1.1
- Bumped `APP_VERSION` to 0.1.1 and tagged the changelog with the transcribing indicator and queue-drain fixes.
- Recorded the API key docs tweak in the release notes and kept the Unreleased section ready for future work.
- Ignored `.vscode/` locally so editor metadata stays out of the repository ahead of tagging.
