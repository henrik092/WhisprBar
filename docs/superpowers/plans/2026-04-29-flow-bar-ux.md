# Flow Bar UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the A2.1 Soft Dark Flow-Bar for Flow Mode while preserving the classic WhisprBar indicator when Flow Mode is disabled.

**Architecture:** Extend `whisprbar/ui/recording_indicator.py` with a Flow renderer selected by `cfg["flow_mode_enabled"]`. Keep the public indicator API stable and adjust `main.dispatch_transcript_text()` so Flow status order is `Pasting` then `Done`.

**Tech Stack:** Python 3, GTK3 DrawingArea, Cairo, pytest.

---

## File Map

- Modify `whisprbar/ui/recording_indicator.py`
  - Add `PHASE_REWRITING`
  - Add Flow renderer selection
  - Add Flow label/hotkey helpers
  - Draw A2.1 Soft Dark bar for all phases
- Modify `whisprbar/main.py`
  - Show `Pasting` before paste and `Done` after paste
  - Preserve existing clipboard-only behavior
- Add/modify `tests/test_recording_indicator_flow.py`
  - Test pure helper behavior without GTK rendering
- Modify `tests/test_main_flow_integration.py`
  - Verify status order for paste path

---

## Task 1: Flow Indicator Helpers

**Files:**
- Modify: `whisprbar/ui/recording_indicator.py`
- Test: `tests/test_recording_indicator_flow.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_recording_indicator_flow.py`:

```python
"""Tests for Flow Mode recording indicator helpers."""

import pytest

from whisprbar.ui import recording_indicator as indicator


@pytest.mark.unit
def test_flow_indicator_enabled_from_config():
    assert indicator._is_flow_indicator_enabled({"flow_mode_enabled": True}) is True
    assert indicator._is_flow_indicator_enabled({"flow_mode_enabled": False}) is False
    assert indicator._is_flow_indicator_enabled({}) is False


@pytest.mark.unit
def test_flow_phase_labels_include_rewriting():
    assert indicator._flow_phase_label(indicator.PHASE_RECORDING) == "Listening"
    assert indicator._flow_phase_label(indicator.PHASE_PROCESSING) == "Processing"
    assert indicator._flow_phase_label(indicator.PHASE_TRANSCRIBING) == "Transcribing"
    assert indicator._flow_phase_label(indicator.PHASE_REWRITING) == "Rewriting"
    assert indicator._flow_phase_label(indicator.PHASE_PASTING) == "Pasting"
    assert indicator._flow_phase_label(indicator.PHASE_COMPLETE) == "Done"
    assert indicator._flow_phase_label("unknown") == "Working"


@pytest.mark.unit
def test_flow_hotkey_label_uses_toggle_binding():
    cfg = {"hotkeys": {"toggle_recording": "CTRL_R"}, "hotkey": "F9"}
    assert indicator._flow_hotkey_label(cfg) == "Right Ctrl"


@pytest.mark.unit
def test_flow_hotkey_label_falls_back_to_legacy_hotkey():
    assert indicator._flow_hotkey_label({"hotkey": "F9"}) == "F9"
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m pytest tests/test_recording_indicator_flow.py -q
```

Expected: fails because `_is_flow_indicator_enabled`, `_flow_phase_label`, `_flow_hotkey_label`, or `PHASE_REWRITING` are not defined.

- [ ] **Step 3: Implement helpers**

In `whisprbar/ui/recording_indicator.py`, add `PHASE_REWRITING = "rewriting"`, plus:

```python
def _is_flow_indicator_enabled(cfg: Optional[dict]) -> bool:
    return bool((cfg or {}).get("flow_mode_enabled", False))


def _flow_phase_label(phase: str) -> str:
    return {
        PHASE_RECORDING: "Listening",
        PHASE_PROCESSING: "Processing",
        PHASE_TRANSCRIBING: "Transcribing",
        PHASE_REWRITING: "Rewriting",
        PHASE_PASTING: "Pasting",
        PHASE_COMPLETE: "Done",
        PHASE_ERROR: "Error",
    }.get(phase, "Working")


def _flow_hotkey_label(cfg: Optional[dict]) -> str:
    try:
        from whisprbar.hotkeys import hotkey_to_label
        config = cfg or {}
        hotkeys = config.get("hotkeys") or {}
        binding = hotkeys.get("toggle_recording") or config.get("hotkey")
        return hotkey_to_label(binding) if binding else ""
    except Exception:
        return ""
```

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m pytest tests/test_recording_indicator_flow.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add whisprbar/ui/recording_indicator.py tests/test_recording_indicator_flow.py
git commit -m "test: cover flow indicator helpers"
```

## Task 2: Soft Dark Flow Renderer

**Files:**
- Modify: `whisprbar/ui/recording_indicator.py`

- [ ] **Step 1: Add Flow renderer config state**

In `RecordingIndicator.__init__`, store:

```python
self._cfg = cfg
self._flow_mode = _is_flow_indicator_enabled(cfg)
self._flow_hotkey = _flow_hotkey_label(cfg)
```

- [ ] **Step 2: Route drawing by mode**

In `_on_draw()`, after drawing the current background setup is prepared, route Flow Mode first:

```python
if self._flow_mode:
    self._draw_flow_bar(cr, w, h, alpha)
    return False
```

Then keep the existing classic drawing branch unchanged.

- [ ] **Step 3: Implement `_draw_flow_bar()`**

Add a helper that draws:

- soft dark rounded pill background
- small WB accent badge
- animated blue/green line or bars during `recording`
- compact status dot/icon for non-recording phases
- phase label from `_flow_phase_label()`
- elapsed timer and hotkey hint during `recording`
- info text for `complete`

- [ ] **Step 4: Syntax check**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m py_compile whisprbar/ui/recording_indicator.py
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add whisprbar/ui/recording_indicator.py
git commit -m "feat: add soft dark flow bar renderer"
```

## Task 3: Flow Status Order

**Files:**
- Modify: `whisprbar/main.py`
- Test: `tests/test_main_flow_integration.py`

- [ ] **Step 1: Write failing status-order test**

Add to `tests/test_main_flow_integration.py`:

```python
def test_dispatch_transcript_shows_paste_before_done(monkeypatch):
    phases = []
    flow_output = FlowOutput(raw_text="raw", final_text="Final text", profile_id="default")
    monkeypatch.setattr(main, "process_flow_text", lambda text, language, cfg: flow_output)
    monkeypatch.setattr(main, "write_history", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "auto_paste", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "cfg", {"language": "en", "auto_paste_enabled": True})

    main.dispatch_transcript_text(
        "raw",
        output_seconds=1.0,
        show_indicator_func=lambda phase, cfg, info="": phases.append((phase, info)),
    )

    assert [phase for phase, _info in phases] == ["pasting", "complete"]
```

- [ ] **Step 2: Run test to verify red**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m pytest tests/test_main_flow_integration.py::test_dispatch_transcript_shows_paste_before_done -q
```

Expected: fails because current order is complete then pasting.

- [ ] **Step 3: Fix status order**

In `dispatch_transcript_text()`, move the `PHASE_COMPLETE` call after `auto_paste()`. For auto-paste enabled:

```python
if cfg.get("auto_paste_enabled"):
    if show_indicator_func is not None:
        show_indicator_func(PHASE_PASTING, cfg)
    auto_paste(final_text, policy=flow_output.paste_policy)
    if show_indicator_func is not None:
        show_indicator_func(PHASE_COMPLETE, cfg, info=word_info)
else:
    copy_to_clipboard(final_text)
    notify(f"Transcription: {final_text[:50]}...")
    if show_indicator_func is not None:
        show_indicator_func(PHASE_COMPLETE, cfg, info=word_info)
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m pytest tests/test_main_flow_integration.py tests/test_main_flow_actions.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add whisprbar/main.py tests/test_main_flow_integration.py
git commit -m "fix: show flow paste before done"
```

## Task 4: Verification and Local Test Restart

**Files:**
- No code files unless verification reveals a defect

- [ ] **Step 1: Run full tests**

```bash
/home/rik/WhisprBar/.venv/bin/python -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Run import/syntax sanity**

```bash
/home/rik/WhisprBar/.venv/bin/python -c "from whisprbar.ui.recording_indicator import PHASE_REWRITING, RecordingIndicator; from whisprbar.flow.pipeline import process_flow_text; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Restart local test instance**

Stop the current test app, then start the worktree app:

```bash
pkill -f "/home/rik/WhisprBar/.claude/worktrees/wispr-flow-parity/whisprbar.py" || true
setsid -f env WHISPRBAR_DEBUG=1 /home/rik/WhisprBar/.venv/bin/python /home/rik/WhisprBar/.claude/worktrees/wispr-flow-parity/whisprbar.py > /tmp/whisprbar-flow-test.log 2>&1
```

- [ ] **Step 4: Verify running path**

```bash
pgrep -af 'whisprbar|WhisprBar'
tail -40 /tmp/whisprbar-flow-test.log
```

Expected: process points to `.claude/worktrees/wispr-flow-parity/whisprbar.py`, log shows config loaded.
