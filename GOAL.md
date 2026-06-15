# Goal: Simple Wispr-Flow-Like WhisprBar

## Outcome

Make WhisprBar feel like a simple Wispr-Flow-style dictation product for normal users: hold the hotkey, speak, release, and get clean text, with settings organized around user intent instead of implementation details.

## Baseline

Worktree:

`/home/rik/.config/superpowers/worktrees/WhisprBar/whispr-flow-simple`

Branch:

`codex/whispr-flow-simple`

Known starting state:

- Existing Flow modules and WebKit settings UI are already present.
- Baseline tests are not fully green before feature work.
- `.venv/bin/pytest -q` currently reports `365 passed, 36 skipped, 1 failed`.
- Known failure: `tests/test_recording_indicator_flow.py::test_flow_hotkey_label_uses_toggle_binding` expects `Right Ctrl` but receives `CTRL_R`.

## Constraints

- Preserve existing configuration compatibility.
- Keep Wayland clipboard-only behavior as a known platform limitation.
- Do not add cloud sync, accounts, mobile apps, or a new transcription engine.
- Do not weaken tests or narrow the verifier to hide failures.
- Do not delete large legacy paths, change defaults with behavioral risk, push, release, open a PR, or commit implementation changes beyond this approved goal/spec setup without explicit user approval.

## Primary Verifier

Run in the worktree:

```bash
.venv/bin/pytest -q
```

Completion requires this command to pass without failures.

## Supporting Checks

Run in the worktree:

```bash
.venv/bin/python -m compileall -q whisprbar tests
```

Also include focused tests for:

- the Flow-bar hotkey label rendering `CTRL_R` as `Right Ctrl`;
- the simple settings grouping around Flow, Words, Shortcuts, History, and Advanced;
- any config migration or validation changed by the implementation.

If the settings UI is materially changed, inspect the rendered settings surface and record the evidence.

## Iteration Loop

1. Inspect the current code path and tests for the next smallest change.
2. Add or update a focused failing test when behavior changes.
3. Implement one meaningful improvement.
4. Run the focused test.
5. Run broader tests when the focused test passes.
6. Record evidence and the next action.

## Blocker Standard

Only mark blocked when an external dependency or user decision prevents the next meaningful step after repeated attempts. A failing test, unclear code, or implementation difficulty is not enough.

## Completion Proof

Before marking complete, provide:

- paths changed;
- final `.venv/bin/pytest -q` result;
- final compileall result;
- UI/manual inspection evidence if applicable;
- any remaining risks.
