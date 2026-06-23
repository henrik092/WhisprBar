# Track C Context-Aware Paste And Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make dictation output adapt safely to chats, mail, browser fields, editors, terminals, and note contexts.

**Architecture:** Centralize target context detection and map each target to a paste policy plus Flow profile hint. Keep the paste layer conservative: context can influence formatting and policy, but failures must fall back to the existing safe paste/clipboard behavior.

**Tech Stack:** Existing `whisprbar/flow/context.py`, `PastePolicy`, `whisprbar/paste.py`, platform/session detection utilities, pytest.

---

## File Structure

- Modify `whisprbar/flow/context.py`: add target-context classification.
- Modify `whisprbar/flow/models.py`: add optional context fields if needed.
- Modify `whisprbar/flow/pipeline.py`: consume target context for profile/paste hints.
- Modify `whisprbar/paste.py`: preserve safe target policies.
- Modify `whisprbar/main.py`: collect context before Flow processing and pass it through.
- Modify tests: `tests/test_flow_context.py`, `tests/test_flow_pipeline.py`, `tests/test_paste.py`, `tests/test_main_flow_integration.py`.

### Task 1: Add Target Context Classification

**Files:**
- Modify: `whisprbar/flow/context.py`
- Test: `tests/test_flow_context.py`

- [ ] **Step 1: Write classification tests**

Add tests for app/window strings:

```python
def test_classify_target_context_detects_terminal():
    from whisprbar.flow.context import classify_target_context

    context = classify_target_context(app_id="gnome-terminal", window_title="Terminal")

    assert context.kind == "terminal"
    assert context.allow_rich_formatting is False
```

```python
def test_classify_target_context_detects_mail():
    from whisprbar.flow.context import classify_target_context

    context = classify_target_context(app_id="thunderbird", window_title="Inbox")

    assert context.kind == "mail"
    assert context.preferred_style == "email"
```

- [ ] **Step 2: Run failing tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_context.py -q
```

Expected: FAIL for new functions until implemented.

- [ ] **Step 3: Implement classification**

Add a small dataclass `TargetContext(kind, preferred_style, allow_rich_formatting, paste_safety)` and map known app IDs/titles. Unknown targets return `kind="generic"` and conservative defaults.

### Task 2: Route Context Into Flow

**Files:**
- Modify: `whisprbar/flow/pipeline.py`
- Modify: `whisprbar/main.py`
- Test: `tests/test_flow_pipeline.py`
- Test: `tests/test_main_flow_integration.py`

- [ ] **Step 1: Write Flow routing test**

Add a test proving terminal context disables rich formatting and mail context selects an email-friendly style without changing raw transcript text.

- [ ] **Step 2: Implement routing**

Pass `TargetContext` into `process_flow_text()` as an optional argument. If changing the signature is too invasive, store it in config-derived metadata for the call and keep backward compatibility.

- [ ] **Step 3: Run routing tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_context.py tests\test_flow_pipeline.py tests\test_main_flow_integration.py -q
```

Expected: PASS.

### Task 3: Enforce Paste Safety

**Files:**
- Modify: `whisprbar/paste.py`
- Test: `tests/test_paste.py`

- [ ] **Step 1: Write paste policy tests**

Add a test proving terminal context never auto-presses enter unless a command explicitly permits it, and Wayland still degrades to clipboard-only when no safe injection tool is available.

- [ ] **Step 2: Implement policy merge**

Merge context policy with Flow `PastePolicy` using the safer value when they conflict. A target safety restriction must win over style preference.

- [ ] **Step 3: Run Track C verifier**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_paste.py tests\test_flow_context.py tests\test_flow_pipeline.py tests\test_main_flow_integration.py -q
```

Expected: PASS.

### Task 4: Commit Track C

```powershell
git diff --check
git add whisprbar/flow/context.py whisprbar/flow/models.py whisprbar/flow/pipeline.py whisprbar/paste.py whisprbar/main.py tests/test_flow_context.py tests/test_flow_pipeline.py tests/test_paste.py tests/test_main_flow_integration.py
git commit -m "feat: adapt paste behavior to target context"
```
