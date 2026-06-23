# WhisprBar All-In Improvement Plan Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coordinate all major WhisprBar improvement tracks into small, testable, independently shippable PRs.

**Architecture:** Treat the merged streaming-first code on `main` as the baseline. Build one capability track at a time, with explicit interfaces between live ASR, endpointing, Flow, paste, diagnostics, storage, and settings. Avoid copying proprietary WisprFlow implementation details; reimplement only product behaviors and architectural ideas.

**Tech Stack:** Python 3.10+, pytest, WebSocket live ASR backends, existing WebKit settings UI, existing Flow modules, local SQLite transcript store.

---

## Plan Files

- `docs/superpowers/plans/2026-06-22-track-a-live-dictation-feedback.md`
- `docs/superpowers/plans/2026-06-22-track-b-smart-endpointing.md`
- `docs/superpowers/plans/2026-06-22-track-c-context-aware-paste-formatting.md`
- `docs/superpowers/plans/2026-06-22-track-d-flow-actions.md`
- `docs/superpowers/plans/2026-06-22-track-e-resilience-backend-health.md`
- `docs/superpowers/plans/2026-06-22-track-f-latency-dashboard.md`
- `docs/superpowers/plans/2026-06-22-track-g-audio-pipeline-cleanup.md`
- `docs/superpowers/plans/2026-06-22-track-h-onboarding-settings.md`

## Phase 2 Follow-Up Plans

- `docs/superpowers/plans/2026-06-23-whisprbar-phase-2-feature-backlog.md`
- `docs/superpowers/plans/2026-06-23-track-i-voice-edit-undo.md`
- `docs/superpowers/plans/2026-06-23-track-j-personal-learning-memory.md`
- `docs/superpowers/plans/2026-06-23-track-k-voice-macros-command-palette.md`
- `docs/superpowers/plans/2026-06-23-track-l-review-popover-safety.md`
- `docs/superpowers/plans/2026-06-23-track-m-mic-language-performance.md`

## Sequencing

1. Track A first: users should see live text while speaking.
2. Track B second: endpointing can use live/final signals from Track A.
3. Track E early: queue overflow, dropped chunks, and backend health protect correctness.
4. Track F after A/B/E: latency dashboard needs meaningful metadata from real paths.
5. Track C before D: context-aware paste gives actions a safe target policy.
6. Track D after C: actions should not bypass paste policy or target safeguards.
7. Track G after latency evidence shows remaining audio bottlenecks.
8. Track H alongside visible changes, but keep it as its own PR if settings scope grows.

## Global Non-Goals

- Do not copy proprietary WisprFlow code, assets, prompts, request schemas, API details, or secrets.
- Do not introduce required large local model dependencies without approval.
- Do not change default backend, privacy retention, or hotkeys without approval.
- Do not use paid/live API calls for benchmarks without approval.
- Do not hide known Windows-only full-suite failures around POSIX modes, XDG separators, `ls`, or `/tmp`.

## Parent Verification

Run after each track PR, adjusting for track scope:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio.py tests\test_transcription.py tests\test_deepgram.py tests\test_paste.py tests\test_main_audio_feedback.py tests\test_main_flow_actions.py tests\test_main_flow_integration.py tests\test_flow_context.py tests\test_flow_commands.py tests\test_flow_pipeline.py tests\test_flow_formatting.py tests\test_flow_rewrite.py tests\test_settings_webview.py tests\test_transcript_store.py -q
.\.venv\Scripts\python.exe -m compileall -q whisprbar tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

## Done When

- Each plan file has been implemented or intentionally superseded by a reviewed replacement plan.
- Each implemented track has focused tests and a PR with verification evidence.
- The final app can show live feedback, stop intelligently, choose safe paste behavior, run Flow actions, recover from live backend failures, explain latency, and guide setup.
