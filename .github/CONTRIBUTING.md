# Contributing to WhisprBar

Thanks for helping improve WhisprBar. Keep changes focused and include enough
verification detail that another Linux desktop user can reproduce the result.

## Development Setup

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Use `--system-site-packages` so GTK/AppIndicator bindings from the system Python
remain available.

## Checks

Run the affected tests first, then the full suite before opening a pull request:

```bash
.venv/bin/pytest tests/test_transcription.py
.venv/bin/pytest
```

For desktop behavior, also mention any manual checks you performed:

- tray icon appears
- hotkey starts and stops recording
- transcription completes
- text insertion works on X11, or clipboard fallback works on Wayland
- settings changes persist

## Repository Hygiene

- Keep runtime code in `whisprbar/`.
- Keep automated tests in `tests/`.
- Keep reference docs in `docs/`.
- Keep GitHub templates in `.github/`.
- Do not commit local API keys, transcript history, coverage output, caches, or
  Nextcloud sync metadata.
