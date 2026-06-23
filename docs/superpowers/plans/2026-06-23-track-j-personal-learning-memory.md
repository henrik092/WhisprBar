# Track J Personal Learning Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WhisprBar gradually adapt to the user's app-specific wording, corrections, and repeated snippets while keeping review explicit.

**Architecture:** Extend existing Flow profiles, transcript SQLite metadata, snippets, and Learning Inbox instead of adding a new learning subsystem. Store only compact local statistics by default; any body-bearing snippet suggestion must be explicitly reviewed before it is saved as a snippet.

**Tech Stack:** Python 3.10+, pytest, SQLite transcript store, JSON state files under `~/.local/share/whisprbar`, existing `flow.profiles`, `flow.learning_inbox`, and settings WebKit UI.

---

## File Structure

- Create `whisprbar/flow/style_memory.py`: local per-profile style counters and bounded recommendations.
- Create `tests/test_flow_style_memory.py`: tests for loading, saving, observing, and applying style recommendations.
- Modify `whisprbar/flow/profiles.py`: merge style memory into resolved profiles when enabled.
- Modify `whisprbar/flow/learning_inbox.py`: allow reviewed snippet candidates to become snippets, not only dictionary entries.
- Create `tests/test_flow_snippet_suggestions.py`: tests for repeated local phrase mining from SQLite.
- Create `whisprbar/flow/snippet_suggestions.py`: builds conservative repeated-output candidates.
- Modify `whisprbar/config.py`, `whisprbar/config_types.py`, and `whisprbar/ui/settings_webview.py`: add review and privacy controls.
- Modify `tests/test_learning_inbox.py`, `tests/test_flow_profiles.py`, and `tests/test_settings_webview.py`: cover the new review paths and settings payload.

## Behavior Contract

- Style memory is opt-in through `flow_style_memory_enabled`.
- Style memory stores counters and profile preferences, not raw transcript bodies.
- Correction learning never changes dictionary or snippets without explicit user approval.
- Snippet suggestions can display the repeated text only when local history storage is not `never` and the user opens the Learning Inbox.
- Private local mode from Track L must disable this track's body-bearing suggestions.

### Task 1: Add Local Style Memory Store

**Files:**
- Create: `whisprbar/flow/style_memory.py`
- Create: `tests/test_flow_style_memory.py`

- [ ] **Step 1: Write failing style-memory tests**

```python
"""Tests for per-profile Flow style memory."""

import pytest

from whisprbar.flow.models import AppContext, FlowOutput
from whisprbar.flow.style_memory import (
    StyleMemoryStore,
    apply_style_memory_to_profile,
)
from whisprbar.flow.models import FlowProfile


@pytest.mark.unit
def test_style_memory_observes_rewrite_success(tmp_path):
    path = tmp_path / "style_memory.json"
    store = StyleMemoryStore(path)

    store.observe(
        AppContext("x11", app_class="Slack", window_title="Team"),
        FlowOutput(
            raw_text="hello team",
            final_text="Hello team.",
            profile_id="chat",
            rewrite_status="applied",
        ),
    )

    payload = store.load()
    assert payload["profiles"]["chat"]["rewrite_applied"] == 1


@pytest.mark.unit
def test_style_memory_can_disable_rewrite_after_failures(tmp_path):
    path = tmp_path / "style_memory.json"
    store = StyleMemoryStore(path)
    store.save(
        {
            "version": 1,
            "profiles": {
                "chat": {
                    "rewrite_applied": 1,
                    "rewrite_failed": 5,
                    "last_seen": "2026-06-23T10:00:00+00:00",
                }
            },
        }
    )

    profile = apply_style_memory_to_profile(
        FlowProfile(profile_id="chat", label="Chat", rewrite_mode="concise"),
        store.load(),
        enabled=True,
    )

    assert profile.rewrite_mode == "none"
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_style_memory.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.flow.style_memory'
```

- [ ] **Step 3: Add style-memory implementation**

Create `whisprbar/flow/style_memory.py`:

```python
"""Local per-profile Flow style memory."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from whisprbar.config import DATA_DIR
from whisprbar.flow.models import AppContext, FlowOutput, FlowProfile

STYLE_MEMORY_VERSION = 1
STYLE_MEMORY_PATH = DATA_DIR / "style_memory.json"


class StyleMemoryStore:
    """Small JSON store for profile-level counters."""

    def __init__(self, path: Path = STYLE_MEMORY_PATH) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": STYLE_MEMORY_VERSION, "profiles": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": STYLE_MEMORY_VERSION, "profiles": {}}
        if not isinstance(payload, dict):
            return {"version": STYLE_MEMORY_VERSION, "profiles": {}}
        profiles = payload.get("profiles")
        if not isinstance(profiles, dict):
            profiles = {}
        return {"version": STYLE_MEMORY_VERSION, "profiles": profiles}

    def save(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": STYLE_MEMORY_VERSION,
            "profiles": payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {},
        }
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, self.path)
        self.path.chmod(0o600)

    def observe(self, context: AppContext, output: FlowOutput) -> None:
        payload = self.load()
        profiles = payload.setdefault("profiles", {})
        item = profiles.setdefault(output.profile_id, {})
        status = output.rewrite_status or "not_requested"
        if status == "applied":
            item["rewrite_applied"] = int(item.get("rewrite_applied", 0)) + 1
        elif status in {"failed", "timeout", "not_configured"}:
            item["rewrite_failed"] = int(item.get("rewrite_failed", 0)) + 1
        item["last_seen"] = datetime.now(timezone.utc).isoformat()
        if context.app_class:
            item["last_app_class"] = context.app_class
        self.save(payload)


def apply_style_memory_to_profile(profile: FlowProfile, payload: Mapping[str, Any], *, enabled: bool) -> FlowProfile:
    """Return a profile adjusted by conservative local style memory."""
    if not enabled:
        return profile
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), Mapping) else {}
    item = profiles.get(profile.profile_id) if isinstance(profiles, Mapping) else None
    if not isinstance(item, Mapping):
        return profile
    failed = int(item.get("rewrite_failed", 0) or 0)
    applied = int(item.get("rewrite_applied", 0) or 0)
    if failed >= 3 and failed > applied * 2:
        return replace(profile, rewrite_mode="none")
    return profile
```

- [ ] **Step 4: Verify style-memory tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_style_memory.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit style memory store**

```bash
git add whisprbar/flow/style_memory.py tests/test_flow_style_memory.py
git commit -m "feat: add local style memory store"
```

### Task 2: Apply Style Memory In Profile Resolution

**Files:**
- Modify: `whisprbar/flow/profiles.py`
- Modify: `whisprbar/flow/pipeline.py`
- Modify: `whisprbar/config.py`
- Modify: `whisprbar/config_types.py`
- Modify: `tests/test_flow_profiles.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing profile-resolution test**

Append to `tests/test_flow_profiles.py`:

```python
@pytest.mark.unit
def test_resolve_profile_can_apply_style_memory(monkeypatch):
    from whisprbar.flow import profiles

    monkeypatch.setattr(
        profiles,
        "load_style_memory_payload",
        lambda: {
            "version": 1,
            "profiles": {"chat": {"rewrite_applied": 1, "rewrite_failed": 5}},
        },
    )

    profile = profiles.resolve_profile(
        AppContext("x11", app_class="Slack", window_title="Team"),
        {"flow_style_memory_enabled": True},
    )

    assert profile.profile_id == "chat"
    assert profile.rewrite_mode == "none"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_profiles.py::test_resolve_profile_can_apply_style_memory -q
```

Expected:

```text
AttributeError: module 'whisprbar.flow.profiles' has no attribute 'load_style_memory_payload'
```

- [ ] **Step 3: Wire style memory into profiles**

In `whisprbar/flow/profiles.py`, import:

```python
from whisprbar.flow.style_memory import StyleMemoryStore, apply_style_memory_to_profile
```

Add:

```python
def load_style_memory_payload() -> dict:
    return StyleMemoryStore().load()
```

At the end of `resolve_profile`, before `return profile`, add:

```python
profile = apply_style_memory_to_profile(
    profile,
    load_style_memory_payload(),
    enabled=bool(cfg.get("flow_style_memory_enabled", False)),
)
```

Add defaults to `whisprbar/config.py` and `whisprbar/config_types.py`:

```python
"flow_style_memory_enabled": False,
```

- [ ] **Step 4: Observe Flow outputs after dispatch**

In `whisprbar/flow/pipeline.py`, do not save style memory inside pure processing. In `whisprbar/main.py`, after a successful final Flow output is known and before returning from `dispatch_transcript_text`, call:

```python
if cfg.get("flow_style_memory_enabled", False):
    from whisprbar.flow.style_memory import StyleMemoryStore
    context_data = flow_output.metadata.get("context", {}) if isinstance(flow_output.metadata, dict) else {}
    StyleMemoryStore().observe(
        AppContext(
            session_type=str(context_data.get("session_type") or "unknown"),
            app_class=str(context_data.get("app_class") or ""),
            app_name=str(context_data.get("app_name") or ""),
            window_title=str(context_data.get("window_title") or ""),
        ),
        flow_output,
    )
```

- [ ] **Step 5: Verify profile and config tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_profiles.py tests\test_config.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 6: Commit profile style memory**

```bash
git add whisprbar/flow/profiles.py whisprbar/main.py whisprbar/config.py whisprbar/config_types.py tests/test_flow_profiles.py tests/test_config.py
git commit -m "feat: apply local style memory to flow profiles"
```

### Task 3: Build Reviewed Snippet Suggestions

**Files:**
- Create: `whisprbar/flow/snippet_suggestions.py`
- Create: `tests/test_flow_snippet_suggestions.py`
- Modify: `whisprbar/flow/learning_inbox.py`
- Modify: `tests/test_learning_inbox.py`

- [ ] **Step 1: Write failing repeated-snippet test**

```python
"""Tests for repeated local snippet suggestions."""

import pytest

from whisprbar.flow.snippet_suggestions import build_snippet_suggestions
from whisprbar.transcript_store import save_transcript_record


@pytest.mark.unit
def test_build_snippet_suggestions_from_repeated_text(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    for index in range(3):
        save_transcript_record(
            "Best regards, Henrik",
            1.0,
            3,
            metadata={"profile_id": "email"},
            config={"language": "en"},
            database_path=database_path,
            created_at=f"2026-06-23T10:00:0{index}+00:00",
        )

    suggestions = build_snippet_suggestions(database_path=database_path, min_evidence=2)

    assert suggestions[0].kind == "snippet"
    assert suggestions[0].text == "Best regards, Henrik"
    assert suggestions[0].evidence_count == 3
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_snippet_suggestions.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.flow.snippet_suggestions'
```

- [ ] **Step 3: Add snippet-suggestion builder**

Create `whisprbar/flow/snippet_suggestions.py`:

```python
"""Reviewed snippet suggestions from repeated local transcript outputs."""

from collections import Counter
from dataclasses import dataclass
import sqlite3
from pathlib import Path

from whisprbar.transcript_store import DATABASE_PATH


@dataclass(frozen=True)
class SnippetSuggestion:
    kind: str
    text: str
    evidence_count: int


def _word_count(text: str) -> int:
    return len([part for part in text.split() if part.strip()])


def build_snippet_suggestions(*, database_path: Path = DATABASE_PATH, min_evidence: int = 2) -> list[SnippetSuggestion]:
    database_path = Path(database_path)
    if not database_path.exists():
        return []

    counts: Counter[str] = Counter()
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        for (text,) in connection.execute("SELECT text FROM transcripts WHERE text != ''"):
            value = str(text or "").strip()
            words = _word_count(value)
            if 2 <= words <= 20:
                counts[value] += 1
    finally:
        connection.close()

    return [
        SnippetSuggestion(kind="snippet", text=text, evidence_count=count)
        for text, count in counts.most_common()
        if count >= min_evidence
    ]
```

- [ ] **Step 4: Extend Learning Inbox approval**

In `whisprbar/flow/learning_inbox.py`, add snippet candidates from `build_snippet_suggestions()` when `include_body_suggestions=True` is passed to `get_learning_inbox_summary`. Use candidate IDs based on `kind`, `text`, and count. On approval, save a snippet with a generated trigger:

```python
trigger = "snippet " + candidate.id[:6]
entries = load_snippets()
entries.append(Snippet(trigger=trigger, text=candidate.written))
save_snippets(entries)
```

Keep `include_body_suggestions=False` as the default so the current body-free settings summary remains conservative unless the Settings UI explicitly requests review data.

- [ ] **Step 5: Verify snippet suggestion and inbox tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_snippet_suggestions.py tests\test_learning_inbox.py tests\test_flow_snippets.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 6: Commit snippet suggestions**

```bash
git add whisprbar/flow/snippet_suggestions.py whisprbar/flow/learning_inbox.py tests/test_flow_snippet_suggestions.py tests/test_learning_inbox.py
git commit -m "feat: suggest reviewed snippets from local history"
```

### Task 4: Add Settings Controls And Final Verification

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Modify: `tests/test_settings_webview.py`

- [ ] **Step 1: Write failing settings payload test**

Append to `tests/test_settings_webview.py`:

```python
@pytest.mark.unit
def test_apply_settings_payload_saves_style_memory_flag(mock_config):
    from whisprbar.ui.settings_webview import apply_settings_payload

    result = apply_settings_payload(
        mock_config,
        {"settings": {"flow_style_memory_enabled": "true"}},
        save_config_func=lambda: None,
        update_device_func=lambda: None,
    )

    assert result.ok is True
    assert mock_config["flow_style_memory_enabled"] is True
```

- [ ] **Step 2: Run the failing settings test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_settings_webview.py::test_apply_settings_payload_saves_style_memory_flag -q
```

Expected:

```text
AssertionError: assert False is True
```

- [ ] **Step 3: Add settings apply and UI row**

In `apply_settings_payload`, add:

```python
config["flow_style_memory_enabled"] = _bool_value(
    _setting(settings, "flow_style_memory_enabled", config.get("flow_style_memory_enabled", False))
)
```

In the Flow settings section generated by `generate_settings_html`, add:

```python
_switch(
    "flow_style_memory_enabled",
    tr("settings.flow_style_memory"),
    tr("settings.flow_style_memory_desc"),
    config.get("flow_style_memory_enabled", False),
)
```

Add translation keys in `whisprbar/i18n.py`:

```python
"settings.flow_style_memory": "Style memory",
"settings.flow_style_memory_desc": "Learn conservative app-specific rewrite preferences from reviewed local results.",
```

- [ ] **Step 4: Run Track J verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_style_memory.py tests\test_flow_profiles.py tests\test_flow_snippet_suggestions.py tests\test_learning_inbox.py tests\test_settings_webview.py tests\test_config.py -q
.\.venv\Scripts\python.exe -m compileall -q whisprbar tests
git diff --check
```

Expected:

```text
pytest exits 0
compileall exits 0
git diff --check exits 0
```

- [ ] **Step 5: Commit Track J**

```bash
git add whisprbar tests
git commit -m "feat: add reviewed personal learning controls"
```

## Manual QA

- Enable style memory, dictate in Slack or another chat app, and confirm `~/.local/share/whisprbar/style_memory.json` appears with private file permissions.
- Approve a dictionary suggestion from Settings and confirm the dictionary changes only after approval.
- Review a repeated snippet suggestion and confirm the snippet is added with a generated trigger and then expands in Flow mode.
