# WhisprBar Phase 2 Feature Backlog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the next set of WisprFlow-inspired product features as clean, testable WhisprBar implementation tracks.

**Architecture:** Phase 2 builds on the Phase 1 tracks in this folder, especially live feedback, endpointing, Flow actions, diagnostics, and latency telemetry. Each feature stays local-first, Linux-compatible, and reviewable without copying proprietary WisprFlow code, assets, prompts, request schemas, or secrets.

**Tech Stack:** Python 3.10+, pytest, GTK 3/WebKit settings UI, SQLite transcript store, existing Flow modules, existing Linux clipboard and xdotool paste paths.

---

## Track Index

- Track I: [Voice Edit And Undo](2026-06-23-track-i-voice-edit-undo.md)
- Track J: [Personal Learning Memory](2026-06-23-track-j-personal-learning-memory.md)
- Track K: [Voice Macros And Command Palette](2026-06-23-track-k-voice-macros-command-palette.md)
- Track L: [Review Popover And Safety](2026-06-23-track-l-review-popover-safety.md)
- Track M: [Mic Language And Performance](2026-06-23-track-m-mic-language-performance.md)

## Feature Mapping

| User-facing feature | Owning track | Why it belongs there |
| --- | --- | --- |
| Undo last dictation | Track I | Needs paste result history and platform-safe key injection. |
| Replace last dictation by voice | Track I | Combines voice command detection, last-paste state, and normal paste output. |
| Voice edit loop for the last result | Track I | Starts with last-output editing before attempting fragile arbitrary-selection editing. |
| Per-app style memory | Track J | Extends existing `flow.profiles` and `AppContext` resolution. |
| Correction learning | Track J | Extends the existing `flow.learning_inbox` review model. |
| Snippet builder from repeated history | Track J | Extends existing snippets and transcript SQLite storage. |
| User-defined voice macros | Track K | Extends existing command detection without hard-coding every phrase. |
| Command palette | Track K | Gives users a discoverable UI for commands, macros, and Flow actions. |
| Dictation review popover | Track L | Adds a deliberate approval step before paste when output is risky. |
| Private local mode | Track L | Centralizes history, cloud rewrite, and backend privacy policy. |
| Mic and environment health | Track M | Extends diagnostics with signal quality and noise checks. |
| Multi-language auto mode | Track M | Uses current preferred-language config and backend metadata. |
| Performance profiles | Track M | Turns latency choices into a user-facing, testable policy. |

## Sequencing

1. Complete Phase 1 Tracks A, B, E, and F first, because live events, endpointing, backend health, and latency metadata are prerequisites for several Phase 2 features.
2. Implement Track I before Track K, because macros should be able to call stable undo and replace actions instead of duplicating paste behavior.
3. Implement Track L before enabling broad learning or macros by default, because private mode and review policy define the safety boundary.
4. Implement Track J after transcript metadata and privacy policy are stable, because learning must respect storage settings and explicit review.
5. Implement Track M in parallel after diagnostics and settings layout are stable, because it is mostly policy, diagnostics, and backend selection work.

## Shared Constraints

- Keep every feature disabled or conservative by default when it can surprise the user.
- Store private data only under `~/.local/share/whisprbar` or `~/.config/whisprbar` with owner-only permissions.
- Do not send transcript bodies to cloud rewrite providers when private local mode is active.
- Do not execute shell commands, open URLs, press Enter, or submit forms from macros without an explicit setting and a visible confirmation path.
- Keep Wayland behavior clipboard-first unless a safe compositor-specific implementation is intentionally added and tested.
- Keep all implementation work Linux-first; Windows test failures already documented for unrelated POSIX/XDG assumptions are not a reason to weaken Linux behavior.

## Parent Verification

Run this after each Phase 2 track PR:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_commands.py tests\test_flow_pipeline.py tests\test_flow_profiles.py tests\test_flow_snippets.py tests\test_learning_inbox.py tests\test_paste.py tests\test_config.py tests\test_transcript_store.py tests\test_settings_webview.py -q
.\.venv\Scripts\python.exe -m compileall -q whisprbar tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected result:

```text
pytest exits 0 for the selected tests
compileall exits 0
pip check reports no broken requirements
git diff --check exits 0
```

## Done When

- Every listed feature has either a merged implementation PR or a superseding reviewed plan.
- Private mode, review behavior, and macro safety are documented before any feature becomes default-on.
- The app can be improved through separate PRs without mixing audio, paste, learning, UI, and privacy changes into one large change set.
