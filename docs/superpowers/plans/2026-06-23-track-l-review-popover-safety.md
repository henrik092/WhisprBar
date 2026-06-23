# Track L Review Popover And Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safety layer that lets users review risky dictations before paste and switch the app into a private local mode.

**Architecture:** Centralize privacy policy in a pure Flow module, then make paste dispatch consult that policy before writing history, running cloud rewrite, or auto-pasting long or sensitive output. Use a small GTK review popover for approval, editing, clipboard-only fallback, and cancel.

**Tech Stack:** Python 3.10+, pytest, GTK 3, existing paste policy, existing transcript store, existing Flow rewrite provider.

---

## File Structure

- Create `whisprbar/flow/privacy.py`: computes effective privacy and review policy from config and Flow output.
- Create `tests/test_flow_privacy.py`: unit tests for private mode and review decisions.
- Create `whisprbar/ui/review_popover.py`: GTK review dialog with approve, edit, copy, and cancel results.
- Create `tests/test_review_popover.py`: pure tests for review result models and non-GTK fallback behavior.
- Modify `whisprbar/flow/rewrite.py`: refuse cloud rewrite when private local mode is active.
- Modify `whisprbar/main.py`: call review policy before paste and storage.
- Modify `whisprbar/transcript_store.py` and `whisprbar/utils.py`: respect privacy mode for SQLite and JSONL writes.
- Modify `whisprbar/config.py`, `whisprbar/config_types.py`, `whisprbar/ui/settings_webview.py`, and `whisprbar/i18n.py`: expose settings.
- Modify `tests/test_transcript_store.py`, `tests/test_flow_rewrite.py`, `tests/test_main_flow_actions.py`, and `tests/test_settings_webview.py`.

## Behavior Contract

- `flow_private_local_mode` disables cloud rewrite, transcript storage, style memory, and body-bearing learning suggestions.
- Review popover triggers for long output, press-enter policy, command output, or configured always-review mode.
- Clipboard-only output can be copied from the review popover without key injection.
- Cancel means no paste and no transcript body is written.
- Non-GTK environments use clipboard-only fallback with a notification instead of crashing.

### Task 1: Add Privacy And Review Policy

**Files:**
- Create: `whisprbar/flow/privacy.py`
- Create: `tests/test_flow_privacy.py`
- Modify: `whisprbar/config.py`
- Modify: `whisprbar/config_types.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing policy tests**

```python
"""Tests for Flow privacy and review policy."""

import pytest

from whisprbar.flow.models import FlowOutput, PastePolicy
from whisprbar.flow.privacy import effective_privacy_config, should_review_output


@pytest.mark.unit
def test_private_local_mode_forces_no_storage_and_no_rewrite():
    policy = effective_privacy_config(
        {
            "flow_private_local_mode": True,
            "flow_history_storage": "normal",
            "flow_rewrite_enabled": True,
        }
    )

    assert policy["flow_history_storage"] == "never"
    assert policy["flow_rewrite_enabled"] is False
    assert policy["flow_style_memory_enabled"] is False


@pytest.mark.unit
def test_review_required_for_press_enter_policy():
    output = FlowOutput(
        raw_text="send this",
        final_text="send this",
        profile_id="default",
        paste_policy=PastePolicy(press_enter_after_paste=True),
    )

    decision = should_review_output(output, {"flow_review_mode": "smart"})

    assert decision.required is True
    assert "press_enter" in decision.reasons


@pytest.mark.unit
def test_review_not_required_for_short_plain_text():
    output = FlowOutput(raw_text="hello", final_text="hello", profile_id="default")

    decision = should_review_output(output, {"flow_review_mode": "smart"})

    assert decision.required is False
```

- [ ] **Step 2: Run the failing policy tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_privacy.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.flow.privacy'
```

- [ ] **Step 3: Add privacy policy module**

Create `whisprbar/flow/privacy.py`:

```python
"""Privacy and review policy for Flow output."""

from dataclasses import dataclass
from typing import Mapping, Tuple

from whisprbar.flow.models import FlowOutput


@dataclass(frozen=True)
class ReviewDecision:
    required: bool
    reasons: Tuple[str, ...] = ()


def effective_privacy_config(config: Mapping[str, object]) -> dict:
    effective = dict(config)
    if effective.get("flow_private_local_mode", False):
        effective["flow_history_storage"] = "never"
        effective["flow_rewrite_enabled"] = False
        effective["flow_style_memory_enabled"] = False
        effective["flow_body_learning_enabled"] = False
    return effective


def should_review_output(output: FlowOutput, config: Mapping[str, object]) -> ReviewDecision:
    mode = str(config.get("flow_review_mode", "off") or "off")
    if mode == "off":
        return ReviewDecision(required=False)
    if mode == "always":
        return ReviewDecision(required=True, reasons=("always",))

    reasons = []
    text = output.final_text or ""
    max_chars = int(config.get("flow_review_long_text_chars", 500) or 500)
    if len(text) >= max_chars:
        reasons.append("long_text")
    if output.command:
        reasons.append("command")
    if output.paste_policy is not None and output.paste_policy.press_enter_after_paste:
        reasons.append("press_enter")
    return ReviewDecision(required=bool(reasons), reasons=tuple(reasons))
```

Add config defaults:

```python
"flow_private_local_mode": False,
"flow_review_mode": "off",
"flow_review_long_text_chars": 500,
"flow_body_learning_enabled": False,
```

Clamp `flow_review_mode` to `{"off", "smart", "always"}` and `flow_review_long_text_chars` to `100..5000`.

- [ ] **Step 4: Verify privacy and config tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_privacy.py tests\test_config.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 5: Commit privacy policy**

```bash
git add whisprbar/flow/privacy.py whisprbar/config.py whisprbar/config_types.py tests/test_flow_privacy.py tests/test_config.py
git commit -m "feat: add flow privacy policy"
```

### Task 2: Enforce Private Mode In Rewrite And Storage

**Files:**
- Modify: `whisprbar/flow/rewrite.py`
- Modify: `whisprbar/transcript_store.py`
- Modify: `whisprbar/utils.py`
- Modify: `tests/test_flow_rewrite.py`
- Modify: `tests/test_transcript_store.py`

- [ ] **Step 1: Write failing rewrite privacy test**

Append to `tests/test_flow_rewrite.py`:

```python
@pytest.mark.unit
def test_rewrite_text_skips_provider_in_private_local_mode():
    from whisprbar.flow.models import AppContext, FlowProfile
    from whisprbar.flow.rewrite import rewrite_text

    class Provider:
        def rewrite(self, text, prompt, cfg):
            raise AssertionError("provider should not be called")

    result = rewrite_text(
        "hello",
        "en",
        AppContext("x11"),
        FlowProfile("default", "Default", rewrite_mode="clean"),
        None,
        (),
        {"flow_private_local_mode": True, "flow_rewrite_provider": "openai_compatible"},
        provider=Provider(),
    )

    assert result.text == "hello"
    assert result.status == "private_local_mode"
```

- [ ] **Step 2: Run the failing rewrite test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_rewrite.py::test_rewrite_text_skips_provider_in_private_local_mode -q
```

Expected:

```text
AssertionError: provider should not be called
```

- [ ] **Step 3: Enforce rewrite privacy**

At the top of `rewrite_text` in `whisprbar/flow/rewrite.py`, after the empty text check:

```python
    if cfg.get("flow_private_local_mode", False):
        return RewriteResult(text=text, status="private_local_mode")
```

In `save_transcript_record` and `write_history`, treat `flow_private_local_mode` the same as `flow_history_storage == "never"`:

```python
if config_data.get("flow_private_local_mode", False) or config_data.get("flow_history_storage") == "never":
    return None
```

For `write_history`, return before creating a JSONL row.

- [ ] **Step 4: Verify storage and rewrite tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_rewrite.py tests\test_transcript_store.py tests\test_utils.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 5: Commit private-mode enforcement**

```bash
git add whisprbar/flow/rewrite.py whisprbar/transcript_store.py whisprbar/utils.py tests/test_flow_rewrite.py tests/test_transcript_store.py tests/test_utils.py
git commit -m "feat: enforce private local mode"
```

### Task 3: Add Review Popover And Dispatch

**Files:**
- Create: `whisprbar/ui/review_popover.py`
- Create: `tests/test_review_popover.py`
- Modify: `whisprbar/main.py`
- Modify: `tests/test_main_flow_actions.py`

- [ ] **Step 1: Write failing review model tests**

```python
"""Tests for review popover result handling."""

import pytest

from whisprbar.ui.review_popover import ReviewResult, normalize_review_text


@pytest.mark.unit
def test_normalize_review_text_strips_outer_whitespace():
    assert normalize_review_text("  hello team\n") == "hello team"


@pytest.mark.unit
def test_review_result_approve_with_edit():
    result = ReviewResult(action="paste", text="edited")

    assert result.action == "paste"
    assert result.text == "edited"
```

- [ ] **Step 2: Run the failing review tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_review_popover.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.ui.review_popover'
```

- [ ] **Step 3: Add review popover module**

Create `whisprbar/ui/review_popover.py`:

```python
"""Review dialog for Flow output before paste."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ReviewResult:
    action: str
    text: str = ""


def normalize_review_text(text: str) -> str:
    return str(text or "").strip()


def review_flow_output(text: str, reasons: Iterable[str], cfg: dict) -> ReviewResult:
    """Show a small GTK review dialog and return the user's decision."""
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
    except Exception:
        return ReviewResult(action="copy", text=normalize_review_text(text))

    dialog = Gtk.Dialog(title="Review dictation", flags=0)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Copy", 10)
    dialog.add_button("Paste", Gtk.ResponseType.OK)
    dialog.set_default_size(560, 260)
    box = dialog.get_content_area()
    entry = Gtk.TextView()
    buffer = entry.get_buffer()
    buffer.set_text(text)
    box.pack_start(entry, True, True, 8)
    dialog.show_all()
    response = dialog.run()
    start, end = buffer.get_bounds()
    reviewed_text = normalize_review_text(buffer.get_text(start, end, True))
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        return ReviewResult(action="paste", text=reviewed_text)
    if response == 10:
        return ReviewResult(action="copy", text=reviewed_text)
    return ReviewResult(action="cancel")
```

- [ ] **Step 4: Wire review before paste**

In `whisprbar/main.py`, import:

```python
from whisprbar.flow.privacy import effective_privacy_config, should_review_output
```

At the start of transcript dispatch, derive:

```python
effective_cfg = effective_privacy_config(cfg)
```

Use `effective_cfg` for rewrite, storage, and learning-related behavior in that dispatch path.

Before `auto_paste`, add:

```python
review_decision = should_review_output(flow_output, effective_cfg)
if review_decision.required:
    from whisprbar.ui.review_popover import review_flow_output
    review_result = review_flow_output(flow_output.final_text, review_decision.reasons, effective_cfg)
    if review_result.action == "cancel":
        return flow_output
    if review_result.action == "copy":
        copy_to_clipboard(review_result.text)
        return flow_output
    flow_output = replace(flow_output, final_text=review_result.text)
```

Import `replace` from `dataclasses` if it is not already available.

- [ ] **Step 5: Verify review dispatch tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_review_popover.py tests\test_flow_privacy.py tests\test_main_flow_actions.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 6: Commit review popover dispatch**

```bash
git add whisprbar/ui/review_popover.py whisprbar/main.py tests/test_review_popover.py tests/test_main_flow_actions.py
git commit -m "feat: review risky dictations before paste"
```

### Task 4: Add Settings Controls And Final Verification

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Modify: `whisprbar/i18n.py`
- Modify: `tests/test_settings_webview.py`

- [ ] **Step 1: Write failing settings test**

Append to `tests/test_settings_webview.py`:

```python
@pytest.mark.unit
def test_apply_settings_payload_saves_private_mode_and_review(mock_config):
    from whisprbar.ui.settings_webview import apply_settings_payload

    result = apply_settings_payload(
        mock_config,
        {
            "settings": {
                "flow_private_local_mode": "true",
                "flow_review_mode": "smart",
                "flow_review_long_text_chars": "300",
            }
        },
        save_config_func=lambda: None,
        update_device_func=lambda: None,
    )

    assert result.ok is True
    assert mock_config["flow_private_local_mode"] is True
    assert mock_config["flow_review_mode"] == "smart"
    assert mock_config["flow_review_long_text_chars"] == 300
```

- [ ] **Step 2: Run the failing settings test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_settings_webview.py::test_apply_settings_payload_saves_private_mode_and_review -q
```

Expected:

```text
AssertionError
```

- [ ] **Step 3: Add Settings UI rows**

Add settings apply:

```python
config["flow_private_local_mode"] = _bool_value(
    _setting(settings, "flow_private_local_mode", config.get("flow_private_local_mode", False))
)
config["flow_review_mode"] = str(
    _setting(settings, "flow_review_mode", config.get("flow_review_mode", "off"))
)
config["flow_review_long_text_chars"] = _clamp_int(
    _int_value(_setting(settings, "flow_review_long_text_chars", config.get("flow_review_long_text_chars", 500)), 500),
    100,
    5000,
)
```

Add rows to the Flow settings section:

```python
_switch(
    "flow_private_local_mode",
    tr("settings.private_local_mode"),
    tr("settings.private_local_mode_desc"),
    config.get("flow_private_local_mode", False),
)
_select(
    "flow_review_mode",
    tr("settings.review_mode"),
    tr("settings.review_mode_desc"),
    (("off", "Off"), ("smart", "Smart"), ("always", "Always")),
    config.get("flow_review_mode", "off"),
)
_number_field(
    "flow_review_long_text_chars",
    tr("settings.review_long_text_chars"),
    tr("settings.review_long_text_chars_desc"),
    config.get("flow_review_long_text_chars", 500),
    minimum=100,
    maximum=5000,
    step=50,
    unit="chars",
)
```

- [ ] **Step 4: Run Track L verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_privacy.py tests\test_flow_rewrite.py tests\test_transcript_store.py tests\test_review_popover.py tests\test_main_flow_actions.py tests\test_settings_webview.py tests\test_config.py -q
.\.venv\Scripts\python.exe -m compileall -q whisprbar tests
git diff --check
```

Expected:

```text
pytest exits 0
compileall exits 0
git diff --check exits 0
```

- [ ] **Step 5: Commit Track L**

```bash
git add whisprbar tests
git commit -m "feat: add private mode and review controls"
```

## Manual QA

- Enable private local mode, dictate a phrase, and confirm no new transcript row appears in SQLite or JSONL history.
- Enable smart review and dictate a long text. Confirm the review popover appears before paste.
- Use a press-enter command with smart review enabled. Confirm the review popover appears before any Enter key is sent.
