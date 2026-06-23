# Track I Voice Edit And Undo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users undo, replace, and revise the last dictation without reaching for the keyboard.

**Architecture:** Start with the last WhisprBar insertion instead of arbitrary app text selection. Track paste outcomes in process memory, expose explicit hotkey actions, and detect voice edit intents in Flow before normal paste output.

**Tech Stack:** Python 3.10+, pytest, existing `whisprbar.paste` clipboard and xdotool paths, existing Flow command pipeline, existing hotkey runtime.

---

## File Structure

- Create `whisprbar/flow/editing.py`: detects spoken edit intents and returns typed edit intent objects.
- Create `tests/test_flow_editing.py`: unit tests for German and English edit-intent parsing.
- Create `whisprbar/paste_history.py`: stores the last successful paste result and performs best-effort undo through the paste backend.
- Create `tests/test_paste_history.py`: unit tests for recording and undo behavior without touching the real clipboard.
- Modify `whisprbar/flow/models.py`: add an optional `edit_intent` field to `FlowOutput`.
- Modify `whisprbar/flow/pipeline.py`: run edit-intent detection before rewrite and snippet expansion mutate the command phrase.
- Modify `whisprbar/config.py`, `whisprbar/config_types.py`, `whisprbar/hotkey_actions.py`, and `whisprbar/main.py`: add hotkey actions for undo and replace.
- Modify `tests/test_config.py`, `tests/test_main_hotkeys.py`, and `tests/test_main_flow_actions.py`: cover defaults, hotkey registration, and dispatch behavior.

## Behavior Contract

- "undo last dictation" sends one undo action only when the previous WhisprBar paste reported `status == "inserted"`.
- "replace last with <text>" first undoes the last inserted dictation, then pastes `<text>` through the normal paste policy.
- Clipboard-only or failed paste results never trigger keyboard undo; they notify the user that no inserted dictation can be reverted.
- The first implementation does not try to edit arbitrary selected app text. That avoids brittle Linux accessibility dependencies and keeps the feature reliable.

### Task 1: Detect Voice Edit Intents

**Files:**
- Create: `whisprbar/flow/editing.py`
- Create: `tests/test_flow_editing.py`

- [ ] **Step 1: Write failing edit-intent tests**

```python
"""Tests for Flow voice edit intent detection."""

import pytest

from whisprbar.flow.editing import EditIntent, detect_edit_intent


@pytest.mark.unit
def test_detect_german_undo_last_dictation():
    assert detect_edit_intent("letztes diktat rueckgaengig machen", "de") == EditIntent(
        action="undo_last",
        replacement_text="",
    )


@pytest.mark.unit
def test_detect_english_replace_last_with_text():
    assert detect_edit_intent("replace last with hello team", "en") == EditIntent(
        action="replace_last",
        replacement_text="hello team",
    )


@pytest.mark.unit
def test_normal_text_has_no_edit_intent():
    assert detect_edit_intent("hello team this is normal text", "en") is None
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_editing.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.flow.editing'
```

- [ ] **Step 3: Add the edit-intent detector**

Create `whisprbar/flow/editing.py`:

```python
"""Voice edit intent detection for the last WhisprBar insertion."""

from dataclasses import dataclass
import re
from typing import Optional


@dataclass(frozen=True)
class EditIntent:
    """A local edit command that should be handled before normal paste."""

    action: str
    replacement_text: str = ""


_UNDO_PATTERNS = (
    re.compile(r"^(undo last dictation|undo last|delete last dictation)$", re.IGNORECASE),
    re.compile(r"^(letztes diktat rueckgaengig machen|letztes rueckgaengig machen|letztes loeschen)$", re.IGNORECASE),
)

_REPLACE_PATTERNS = (
    re.compile(r"^replace last with\s+(.+)$", re.IGNORECASE),
    re.compile(r"^ersetze das letzte mit\s+(.+)$", re.IGNORECASE),
    re.compile(r"^letztes ersetzen durch\s+(.+)$", re.IGNORECASE),
)


def _clean(text: str) -> str:
    value = re.sub(r"\s+", " ", text.strip())
    return value.strip(" .,!?:;")


def detect_edit_intent(text: str, language: str) -> Optional[EditIntent]:
    """Return an edit intent for supported last-output commands."""
    normalized = _clean(text)
    if not normalized:
        return None

    for pattern in _UNDO_PATTERNS:
        if pattern.match(normalized):
            return EditIntent(action="undo_last")

    for pattern in _REPLACE_PATTERNS:
        match = pattern.match(normalized)
        if match:
            replacement_text = _clean(match.group(1))
            if replacement_text:
                return EditIntent(action="replace_last", replacement_text=replacement_text)

    return None
```

- [ ] **Step 4: Verify edit-intent tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_editing.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit the detector**

```bash
git add whisprbar/flow/editing.py tests/test_flow_editing.py
git commit -m "feat: detect voice edit intents"
```

### Task 2: Track The Last Inserted Dictation

**Files:**
- Create: `whisprbar/paste_history.py`
- Create: `tests/test_paste_history.py`

- [ ] **Step 1: Write failing paste-history tests**

```python
"""Tests for last-paste tracking."""

from unittest.mock import Mock

import pytest

from whisprbar.paste import PasteResult
from whisprbar.paste_history import PasteHistory, PasteRecord


@pytest.mark.unit
def test_records_inserted_paste():
    history = PasteHistory()

    history.record("hello", PasteResult(status="inserted", sequence="ctrl_v"))

    assert history.last_record == PasteRecord(text="hello", status="inserted", sequence="ctrl_v")


@pytest.mark.unit
def test_does_not_undo_clipboard_only_result():
    history = PasteHistory()
    send_undo = Mock(return_value=True)
    history.record("hello", PasteResult(status="clipboard_only", sequence="clipboard"))

    result = history.undo_last(send_undo)

    assert result == "not_inserted"
    send_undo.assert_not_called()


@pytest.mark.unit
def test_undo_inserted_result_calls_backend_once():
    history = PasteHistory()
    send_undo = Mock(return_value=True)
    history.record("hello", PasteResult(status="inserted", sequence="ctrl_v"))

    assert history.undo_last(send_undo) == "undone"
    send_undo.assert_called_once_with("ctrl_v")
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_paste_history.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.paste_history'
```

- [ ] **Step 3: Add in-process paste history**

Create `whisprbar/paste_history.py`:

```python
"""In-process history for the last WhisprBar paste action."""

from dataclasses import dataclass
from typing import Callable, Optional

from whisprbar.paste import PasteResult


@dataclass(frozen=True)
class PasteRecord:
    """The last paste result WhisprBar can safely reason about."""

    text: str
    status: str
    sequence: str


class PasteHistory:
    """Keep the last paste result without storing transcript bodies on disk."""

    def __init__(self) -> None:
        self.last_record: Optional[PasteRecord] = None

    def record(self, text: str, result: PasteResult) -> None:
        self.last_record = PasteRecord(text=text, status=result.status, sequence=result.sequence)

    def undo_last(self, send_undo: Callable[[str], bool]) -> str:
        record = self.last_record
        if record is None:
            return "empty"
        if record.status != "inserted":
            return "not_inserted"
        if send_undo(record.sequence):
            self.last_record = None
            return "undone"
        return "failed"
```

- [ ] **Step 4: Verify paste-history tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_paste_history.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit paste history**

```bash
git add whisprbar/paste_history.py tests/test_paste_history.py
git commit -m "feat: track last inserted dictation"
```

### Task 3: Wire Edit Intents Into Flow Dispatch

**Files:**
- Modify: `whisprbar/flow/models.py`
- Modify: `whisprbar/flow/pipeline.py`
- Modify: `whisprbar/main.py`
- Modify: `tests/test_flow_pipeline.py`
- Modify: `tests/test_main_flow_actions.py`

- [ ] **Step 1: Add failing pipeline and dispatch tests**

Append to `tests/test_flow_pipeline.py`:

```python
@pytest.mark.unit
def test_process_flow_text_exposes_replace_last_edit_intent(monkeypatch):
    from whisprbar.flow.pipeline import process_flow_text

    output = process_flow_text(
        "replace last with hello team",
        "en",
        {"flow_mode_enabled": True, "flow_context_awareness_enabled": False},
    )

    assert output.edit_intent is not None
    assert output.edit_intent.action == "replace_last"
    assert output.edit_intent.replacement_text == "hello team"
```

Append to `tests/test_main_flow_actions.py`:

```python
@pytest.mark.unit
def test_dispatch_replace_last_undoes_then_pastes(monkeypatch):
    from whisprbar.flow.editing import EditIntent
    from whisprbar.flow.models import FlowOutput
    from whisprbar.main import handle_edit_intent
    from whisprbar.paste_history import PasteHistory

    history = PasteHistory()
    history.record("old", PasteResult(status="inserted", sequence="ctrl_v"))
    pasted = []

    flow_output = FlowOutput(
        raw_text="replace last with new text",
        final_text="replace last with new text",
        profile_id="default",
        edit_intent=EditIntent(action="replace_last", replacement_text="new text"),
    )

    result = handle_edit_intent(
        flow_output,
        paste_history=history,
        send_undo=lambda sequence: True,
        paste_text=lambda text, policy=None: pasted.append(text) or PasteResult("inserted", "ctrl_v"),
    )

    assert result == "handled"
    assert pasted == ["new text"]
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_pipeline.py::test_process_flow_text_exposes_replace_last_edit_intent tests\test_main_flow_actions.py::test_dispatch_replace_last_undoes_then_pastes -q
```

Expected:

```text
AttributeError: 'FlowOutput' object has no attribute 'edit_intent'
```

- [ ] **Step 3: Add the model and pipeline fields**

Modify `whisprbar/flow/models.py`:

```python
from whisprbar.flow.editing import EditIntent
```

Add this field to `FlowOutput`:

```python
edit_intent: Optional[EditIntent] = None
```

Modify `whisprbar/flow/pipeline.py`:

```python
from whisprbar.flow.editing import detect_edit_intent
```

Inside `process_flow_text`, after `local_text = _basic_postprocess(...)`:

```python
edit_intent = detect_edit_intent(local_text, language) if cfg.get("flow_command_mode_enabled", True) else None
if edit_intent is not None:
    return FlowOutput(
        raw_text=raw_text,
        final_text=local_text,
        profile_id=profile.profile_id,
        edit_intent=edit_intent,
        metadata=_metadata(context, profile, {"edit_intent": edit_intent.action}),
    )
```

- [ ] **Step 4: Add dispatch helper in `main.py`**

Add module-level paste history near global state:

```python
from whisprbar.paste_history import PasteHistory

paste_history = PasteHistory()
```

Add helper functions near paste callbacks:

```python
def send_undo_for_last_paste(sequence: str) -> bool:
    """Send Ctrl+Z for a previous inserted paste on X11 or pynput fallback."""
    from whisprbar.paste import is_wayland_session

    if is_wayland_session():
        return False
    import shutil
    import subprocess

    xdotool = shutil.which("xdotool")
    if xdotool:
        try:
            subprocess.run([xdotool, "key", "ctrl+z"], check=True, timeout=2.0)
            return True
        except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            return False
    return False


def handle_edit_intent(flow_output, *, paste_history=paste_history, send_undo=send_undo_for_last_paste, paste_text=auto_paste) -> str:
    """Handle edit intents before normal paste dispatch."""
    intent = getattr(flow_output, "edit_intent", None)
    if intent is None:
        return "not_edit"
    if intent.action == "undo_last":
        return paste_history.undo_last(send_undo)
    if intent.action == "replace_last":
        undo_status = paste_history.undo_last(send_undo)
        if undo_status != "undone":
            notify(t("main.no_inserted_transcript_to_replace", cfg))
            return undo_status
        result = paste_text(intent.replacement_text, getattr(flow_output, "paste_policy", None))
        paste_history.record(intent.replacement_text, result)
        return "handled"
    return "not_edit"
```

Then call `handle_edit_intent(flow_output)` in `dispatch_transcript_text` before normal auto-paste. If it returns anything except `"not_edit"`, skip normal paste and persistence for the edit command text.

- [ ] **Step 5: Verify targeted tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_editing.py tests\test_paste_history.py tests\test_flow_pipeline.py::test_process_flow_text_exposes_replace_last_edit_intent tests\test_main_flow_actions.py::test_dispatch_replace_last_undoes_then_pastes -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 6: Commit Flow dispatch wiring**

```bash
git add whisprbar/flow/models.py whisprbar/flow/pipeline.py whisprbar/main.py tests/test_flow_pipeline.py tests/test_main_flow_actions.py
git commit -m "feat: handle voice edit intents"
```

### Task 4: Add Hotkeys And User-Facing Labels

**Files:**
- Modify: `whisprbar/config.py`
- Modify: `whisprbar/config_types.py`
- Modify: `whisprbar/hotkey_actions.py`
- Modify: `whisprbar/main.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_main_hotkeys.py`

- [ ] **Step 1: Write failing config and hotkey tests**

Append to `tests/test_config.py`:

```python
@pytest.mark.unit
def test_default_hotkeys_include_undo_last_dictation():
    config.reset_config()

    assert "undo_last_dictation" in config.cfg["hotkeys"]
```

Append to `tests/test_main_hotkeys.py`:

```python
@pytest.mark.unit
def test_hotkey_action_order_includes_undo_last_dictation():
    from whisprbar.hotkey_actions import HOTKEY_ACTION_ORDER

    assert "undo_last_dictation" in HOTKEY_ACTION_ORDER
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_config.py::test_default_hotkeys_include_undo_last_dictation tests\test_main_hotkeys.py::test_hotkey_action_order_includes_undo_last_dictation -q
```

Expected:

```text
2 failed
```

- [ ] **Step 3: Add default hotkey action without binding it by default**

Add to `DEFAULT_CFG["hotkeys"]` in `whisprbar/config.py`:

```python
"undo_last_dictation": None,
```

Add the same key to `HotkeyConfig` defaults in `whisprbar/config_types.py`.

Add to `HOTKEY_ACTION_ORDER` in `whisprbar/hotkey_actions.py` after `copy_last_transcript`:

```python
"undo_last_dictation",
```

Add to `HOTKEY_SETTINGS_LABELS`:

```python
"undo_last_dictation": "Letztes Diktat rueckgaengig machen",
```

- [ ] **Step 4: Wire runtime callback**

In `whisprbar/main.py`, add:

```python
def undo_last_dictation_callback() -> None:
    status = paste_history.undo_last(send_undo_for_last_paste)
    if status == "empty":
        notify(t("main.no_previous_transcript", cfg))
    elif status == "not_inserted":
        notify(t("main.last_transcript_not_inserted", cfg))
    elif status == "failed":
        notify(t("main.undo_last_failed", cfg))
```

Add this action to `get_callbacks()`:

```python
"undo_last_dictation": undo_last_dictation_callback,
```

- [ ] **Step 5: Verify hotkey tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_config.py::test_default_hotkeys_include_undo_last_dictation tests\test_main_hotkeys.py::test_hotkey_action_order_includes_undo_last_dictation -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Run Track I verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_editing.py tests\test_paste_history.py tests\test_flow_pipeline.py tests\test_main_flow_actions.py tests\test_main_hotkeys.py tests\test_config.py -q
.\.venv\Scripts\python.exe -m compileall -q whisprbar tests
git diff --check
```

Expected:

```text
pytest exits 0
compileall exits 0
git diff --check exits 0
```

- [ ] **Step 7: Commit Track I**

```bash
git add whisprbar tests
git commit -m "feat: add undo last dictation action"
```

## Manual QA

- On X11, dictate text into a text editor, then trigger the undo hotkey. The inserted text should be removed with one undo.
- On Wayland, dictate text with clipboard-only paste, then trigger undo. The app should notify that there is no inserted dictation to undo.
- Dictate "replace last with hello team" after a successful insertion. The old insertion should be undone and "hello team" should be pasted.
