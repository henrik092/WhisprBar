# Track K Voice Macros And Command Palette Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users define their own spoken commands and discover built-in Flow actions without editing Python code.

**Architecture:** Keep macro execution inside the existing Flow pipeline and restrict the first version to safe local actions: rewrite mode, paste policy, snippet expansion, and clipboard-only output. Add a command palette UI as a read/write view over built-in commands and user macros.

**Tech Stack:** Python 3.10+, pytest, JSON config under `~/.config/whisprbar`, existing `flow.commands`, existing `flow.snippets`, GTK/WebKit settings UI.

---

## File Structure

- Create `whisprbar/flow/macros.py`: load, save, validate, and match user-defined macros.
- Create `tests/test_flow_macros.py`: unit tests for macro validation and matching.
- Modify `whisprbar/flow/commands.py`: merge built-in command specs and macro command specs.
- Modify `tests/test_flow_commands.py`: cover macro command detection.
- Modify `whisprbar/ui/settings_webview.py`: add macro table and command palette page.
- Modify `tests/test_settings_webview.py`: cover macro payload apply/save.
- Modify `whisprbar/config.py` and `whisprbar/config_types.py`: add macro feature flag.
- Modify `whisprbar/i18n.py`: add labels for the command palette and macro table.

## Behavior Contract

- User macros are disabled unless `flow_macros_enabled` is true.
- Macro matching uses the same suffix-only rule as built-in commands, so normal dictation remains predictable.
- The first macro action set is local-only: `rewrite_mode`, `paste_policy`, and `snippet_text`.
- Shell execution, URL opening, and form submission are out of scope for this track because they require a stronger confirmation and permission model.

### Task 1: Add Macro Storage And Validation

**Files:**
- Create: `whisprbar/flow/macros.py`
- Create: `tests/test_flow_macros.py`

- [ ] **Step 1: Write failing macro tests**

```python
"""Tests for user-defined Flow macros."""

import json

import pytest

from whisprbar.flow.macros import Macro, load_macros, match_macro, save_macros, validate_macros


@pytest.mark.unit
def test_save_and_load_macros(tmp_path):
    path = tmp_path / "macros.json"

    save_macros(
        [
            Macro(
                macro_id="signature",
                phrase="add signature",
                action="snippet_text",
                value="Best regards",
            )
        ],
        path,
    )

    assert json.loads(path.read_text(encoding="utf-8")) == [
        {
            "macro_id": "signature",
            "phrase": "add signature",
            "action": "snippet_text",
            "value": "Best regards",
        }
    ]
    assert load_macros(path)[0].phrase == "add signature"


@pytest.mark.unit
def test_validate_macros_rejects_duplicate_phrase():
    with pytest.raises(ValueError, match="duplicate macro phrase"):
        validate_macros(
            [
                Macro("one", "same phrase", "rewrite_mode", "shorter"),
                Macro("two", "Same Phrase", "rewrite_mode", "longer"),
            ]
        )


@pytest.mark.unit
def test_match_macro_only_matches_suffix():
    macro = Macro("signature", "add signature", "snippet_text", "Best regards")

    result = match_macro("please add signature", [macro])

    assert result is not None
    assert result.text == "please"
    assert result.macro == macro
```

- [ ] **Step 2: Run the failing macro tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_macros.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.flow.macros'
```

- [ ] **Step 3: Add macro module**

Create `whisprbar/flow/macros.py`:

```python
"""User-defined local Flow macros."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
from typing import Optional, Sequence

from whisprbar.config import CONFIG_PATH
from whisprbar.utils import debug

MACROS_PATH = CONFIG_PATH.parent / "whisprbar_macros.json"
ALLOWED_ACTIONS = {"rewrite_mode", "snippet_text", "clipboard_only", "new_line"}


@dataclass(frozen=True)
class Macro:
    macro_id: str
    phrase: str
    action: str
    value: str = ""


@dataclass(frozen=True)
class MacroMatch:
    text: str
    macro: Macro


def validate_macros(macros: Sequence[Macro]) -> tuple[Macro, ...]:
    seen: set[str] = set()
    result: list[Macro] = []
    for macro in macros:
        phrase = macro.phrase.strip()
        action = macro.action.strip()
        if not macro.macro_id.strip() or not phrase:
            continue
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"invalid macro action: {action}")
        key = phrase.casefold()
        if key in seen:
            raise ValueError(f"duplicate macro phrase: {phrase}")
        seen.add(key)
        result.append(Macro(macro.macro_id.strip(), phrase, action, macro.value.strip()))
    return tuple(result)


def load_macros(path: Path = MACROS_PATH) -> list[Macro]:
    macro_path = Path(path)
    if not macro_path.exists():
        return []
    try:
        data = json.loads(macro_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        debug(f"Failed to load Flow macros {macro_path}: {exc}")
        return []
    if not isinstance(data, list):
        return []
    macros = []
    for item in data:
        if isinstance(item, dict):
            macros.append(
                Macro(
                    macro_id=str(item.get("macro_id") or ""),
                    phrase=str(item.get("phrase") or ""),
                    action=str(item.get("action") or ""),
                    value=str(item.get("value") or ""),
                )
            )
    return list(validate_macros(macros))


def save_macros(macros: Sequence[Macro], path: Path = MACROS_PATH) -> None:
    macro_path = Path(path)
    macro_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "macro_id": macro.macro_id,
            "phrase": macro.phrase,
            "action": macro.action,
            "value": macro.value,
        }
        for macro in validate_macros(macros)
    ]
    temporary = macro_path.with_name(f".{macro_path.name}.tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, macro_path)
    macro_path.chmod(0o600)


def _normalize(text: str) -> str:
    value = re.sub(r"\s+", " ", text.strip())
    return value.strip(" .,!?:;").casefold()


def match_macro(text: str, macros: Sequence[Macro]) -> Optional[MacroMatch]:
    normalized_text = _normalize(text)
    for macro in sorted(macros, key=lambda item: len(item.phrase), reverse=True):
        phrase = _normalize(macro.phrase)
        if normalized_text == phrase:
            return MacroMatch(text="", macro=macro)
        suffix = " " + phrase
        if normalized_text.endswith(suffix):
            cleaned = re.sub(rf"[\s,.;:!?]*{re.escape(macro.phrase)}[\s,.;:!?]*$", "", text, flags=re.IGNORECASE)
            return MacroMatch(text=cleaned.rstrip(" ,.;:!?").strip(), macro=macro)
    return None
```

- [ ] **Step 4: Verify macro module tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_macros.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit macro storage**

```bash
git add whisprbar/flow/macros.py tests/test_flow_macros.py
git commit -m "feat: add local voice macro storage"
```

### Task 2: Merge Macros Into Command Detection

**Files:**
- Modify: `whisprbar/flow/commands.py`
- Modify: `tests/test_flow_commands.py`
- Modify: `whisprbar/config.py`
- Modify: `whisprbar/config_types.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing macro detection test**

Append to `tests/test_flow_commands.py`:

```python
@pytest.mark.unit
def test_detect_macro_snippet_text(monkeypatch):
    from whisprbar.flow import commands
    from whisprbar.flow.macros import Macro

    monkeypatch.setattr(commands, "load_macros", lambda: [Macro("sig", "add signature", "snippet_text", "Best regards")])

    detection = commands.detect_command(
        "please add signature",
        "en",
        enabled=True,
        macros_enabled=True,
    )

    assert detection.text == "please Best regards"
    assert detection.command_id == "macro:sig"
```

- [ ] **Step 2: Run the failing command test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_commands.py::test_detect_macro_snippet_text -q
```

Expected:

```text
TypeError: detect_command() got an unexpected keyword argument 'macros_enabled'
```

- [ ] **Step 3: Extend command detection**

In `whisprbar/flow/commands.py`, import:

```python
from whisprbar.flow.macros import load_macros, match_macro
```

Change the signature:

```python
def detect_command(text: str, language: str, enabled: bool = True, macros_enabled: bool = False) -> CommandDetection:
```

Before returning no command, add:

```python
    if macros_enabled:
        macro_match = match_macro(text, load_macros())
        if macro_match is not None:
            macro = macro_match.macro
            if macro.action == "snippet_text":
                inserted = f"{macro_match.text} {macro.value}".strip()
                return CommandDetection(text=inserted, command_id=f"macro:{macro.macro_id}")
            if macro.action == "rewrite_mode":
                return CommandDetection(text=macro_match.text, command_id=f"macro:{macro.macro_id}", rewrite_mode=macro.value)
            if macro.action == "clipboard_only":
                return CommandDetection(text=macro_match.text, command_id=f"macro:{macro.macro_id}", paste_policy=PastePolicy(clipboard_only=True))
            if macro.action == "new_line":
                return CommandDetection(text=macro_match.text, command_id=f"macro:{macro.macro_id}", paste_policy=PastePolicy(add_newline=True))
```

In `whisprbar/flow/pipeline.py`, pass:

```python
macros_enabled=cfg.get("flow_macros_enabled", False),
```

Add config default:

```python
"flow_macros_enabled": False,
```

- [ ] **Step 4: Verify command detection tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_commands.py tests\test_config.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 5: Commit macro command detection**

```bash
git add whisprbar/flow/commands.py whisprbar/flow/pipeline.py whisprbar/config.py whisprbar/config_types.py tests/test_flow_commands.py tests/test_config.py
git commit -m "feat: detect user voice macros"
```

### Task 3: Add Command Palette And Macro Settings

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Modify: `whisprbar/i18n.py`
- Modify: `tests/test_settings_webview.py`

- [ ] **Step 1: Write failing settings save test**

Append to `tests/test_settings_webview.py`:

```python
@pytest.mark.unit
def test_apply_settings_payload_saves_macros(mock_config, tmp_path):
    from whisprbar.flow.macros import load_macros
    from whisprbar.ui.settings_webview import apply_settings_payload

    path = tmp_path / "macros.json"

    result = apply_settings_payload(
        mock_config,
        {
            "settings": {"flow_macros_enabled": "true"},
            "macros": [
                {"macro_id": "sig", "phrase": "add signature", "action": "snippet_text", "value": "Best regards"}
            ],
        },
        save_config_func=lambda: None,
        update_device_func=lambda: None,
        save_macros_func=lambda macros: __import__("whisprbar.flow.macros", fromlist=["save_macros"]).save_macros(macros, path),
    )

    assert result.ok is True
    assert mock_config["flow_macros_enabled"] is True
    assert load_macros(path)[0].macro_id == "sig"
```

- [ ] **Step 2: Run the failing settings test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_settings_webview.py::test_apply_settings_payload_saves_macros -q
```

Expected:

```text
TypeError: apply_settings_payload() got an unexpected keyword argument 'save_macros_func'
```

- [ ] **Step 3: Extend settings payload apply**

In `whisprbar/ui/settings_webview.py`, import:

```python
from whisprbar.flow.macros import Macro, load_macros, save_macros
```

Add optional argument to `apply_settings_payload`:

```python
save_macros_func: Callable[[Iterable[Macro]], None] = save_macros,
```

Read payload:

```python
macros_payload = payload.get("macros")
if not isinstance(macros_payload, list):
    macros_payload = []
```

Save flag and macros:

```python
config["flow_macros_enabled"] = _bool_value(
    _setting(settings, "flow_macros_enabled", config.get("flow_macros_enabled", False))
)
save_macros_func(
    [
        Macro(
            macro_id=str(item.get("macro_id") or ""),
            phrase=str(item.get("phrase") or ""),
            action=str(item.get("action") or ""),
            value=str(item.get("value") or ""),
        )
        for item in macros_payload
        if isinstance(item, Mapping)
    ]
)
```

- [ ] **Step 4: Add visible palette page**

In generated settings HTML, add a nav item and page for Commands. The page must list:

```text
Built-in rewrite commands
Built-in paste commands
User macros table with phrase, action, value
```

Keep the macro table shape compatible with the existing dictionary/snippet table pattern:

```html
<div class="wb-table" data-table="macros">
  <div class="wb-table-row">
    <input data-col="macro_id" placeholder="signature">
    <input data-col="phrase" placeholder="add signature">
    <select data-col="action">
      <option value="snippet_text">Snippet text</option>
      <option value="rewrite_mode">Rewrite mode</option>
      <option value="clipboard_only">Clipboard only</option>
      <option value="new_line">New line</option>
    </select>
    <input data-col="value" placeholder="Best regards">
    <button type="button" data-remove-row aria-label="Remove row">-</button>
  </div>
</div>
```

Update `collectPayload()` so it includes:

```javascript
payload.macros = readTable('macros');
```

- [ ] **Step 5: Run Track K verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_macros.py tests\test_flow_commands.py tests\test_flow_pipeline.py tests\test_settings_webview.py tests\test_config.py -q
.\.venv\Scripts\python.exe -m compileall -q whisprbar tests
git diff --check
```

Expected:

```text
pytest exits 0
compileall exits 0
git diff --check exits 0
```

- [ ] **Step 6: Commit Track K**

```bash
git add whisprbar tests
git commit -m "feat: add voice macros command palette"
```

## Manual QA

- Add a macro phrase "add signature" with action `snippet_text` and value "Best regards" in Settings.
- Enable Flow macros and dictate "please add signature" into a normal text editor.
- Confirm the inserted text is "please Best regards" and no command phrase remains in the output.
- Disable Flow macros and confirm the same spoken phrase stays normal dictated text.
