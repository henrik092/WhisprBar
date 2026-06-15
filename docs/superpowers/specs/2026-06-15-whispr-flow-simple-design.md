# WhisprBar Simple Flow Design

## Goal

Make WhisprBar feel closer to Wispr Flow for normal users: simple, obvious, and usable without understanding audio, transcription, or rewrite internals.

The everyday model is:

1. Hold the recording hotkey.
2. Speak naturally.
3. Release the key.
4. Clean text appears where the cursor is.

## Product Direction

WhisprBar should stop presenting Flow as a technical pipeline. The first visible experience should be a small Flow-style recording/status bar and a simple settings surface focused on normal user choices:

- whether Flow Mode is on;
- which languages are used;
- which writing style is preferred;
- whether personal words and snippets should be used;
- a quick way to test dictation.

Advanced controls remain available, but they should not dominate the first settings screen.

## Current Baseline

Observed in the `codex/whispr-flow-simple` worktree:

- Flow modules already exist under `whisprbar/flow/`.
- The WebKit settings UI is the exported default via `whisprbar/ui/__init__.py`.
- The old GTK settings file still exists and is large, but not the default settings entrypoint.
- Transcript SQLite storage exists and is covered by tests.
- Baseline test suite is not green before this work: `.venv/bin/pytest -q` reports `365 passed, 36 skipped, 1 failed`.
- The known baseline failure is `tests/test_recording_indicator_flow.py::test_flow_hotkey_label_uses_toggle_binding`, where `CTRL_R` is shown instead of `Right Ctrl`.

## User Experience

### Flow Bar

The recording indicator should communicate the current state like a lightweight Flow bar:

- `Listening` while recording;
- `Processing`, `Transcribing`, `Rewriting`, and `Pasting` as needed;
- `Done` or an error state after completion;
- the active recording hotkey shown in a human-friendly form.

It should support the normal mental model: press, speak, release. It should not explain implementation steps unless a step is happening.

### Simple Settings

The settings entry should prioritize five areas:

- **Flow**: enable/disable Flow Mode, choose simple preset/style, select preferred languages, run a test dictation.
- **Words**: manage dictionary terms and snippets in plain language.
- **Shortcuts**: set recording, cancel, paste last, and scratchpad shortcuts.
- **History**: show recent dictations and storage preference.
- **Advanced**: backend, API keys, VAD, noise reduction, chunking, overlay dimensions, rewrite provider, and other technical controls.

The default view should not look like a full system configuration panel.

## Implementation Boundaries

In scope:

- simplify the WebKit settings information architecture around Flow-first usage;
- improve Flow-bar labels and visible status;
- keep or improve existing dictionary, snippet, command, history, and transcript-store behavior;
- fix the known baseline indicator label failure if it blocks verification;
- remove or isolate dead settings paths only when directly needed for this work.

Out of scope:

- cloud sync;
- mobile apps;
- new transcription engines;
- paid plans or accounts;
- team/admin features;
- rewriting the entire app shell.

## Data and Configuration

The existing config keys may remain, but the UI should group them by user intent rather than by internal subsystem. Existing configs must continue to load. Any new config key needs:

- a default in `whisprbar/config.py`;
- validation or clamping if user-editable;
- focused tests;
- migration behavior if it changes an existing key.

## Error Handling

The simple path must fail softly:

- if rewrite fails, paste the locally processed transcript;
- if history storage fails, do not block paste;
- if Wayland blocks auto-paste, make clipboard-only behavior clear;
- if a backend/API key is missing, show the missing requirement in the relevant settings area.

## Verification

Primary verifier:

- `.venv/bin/pytest -q` passes in the worktree.

Supporting checks:

- `.venv/bin/python -m compileall -q whisprbar tests` passes.
- A focused settings test proves the simple settings grouping is generated.
- A focused indicator test proves `CTRL_R` renders as `Right Ctrl`.
- If UI rendering is changed materially, inspect the local settings surface with a browser or WebKit-capable manual check and record the result.

## Approval Gates

Ask before:

- deleting large legacy files such as `whisprbar/ui/settings.py`;
- changing default backend, hotkey, history-retention, or cloud rewrite behavior;
- pushing, opening a PR, or committing implementation changes beyond this approved goal/spec setup;
- making any public release or tag.
