# Track D Flow Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend dictation from simple text insertion into safe spoken actions such as rewrite, bullet list, reply draft, copy last, and scratchpad append.

**Architecture:** Add a small Flow action layer that receives command detection output and returns an explicit action result. Action execution must stay local unless an existing rewrite provider is already configured and enabled. External/destructive actions require confirmation or remain draft-only.

**Tech Stack:** Existing Flow command detection, Flow pipeline, scratchpad/history helpers, paste policy, pytest.

---

## File Structure

- Create `whisprbar/flow/actions.py`: action model and local action executor.
- Modify `whisprbar/flow/commands.py`: map command IDs to action IDs where appropriate.
- Modify `whisprbar/flow/pipeline.py`: route action results into `FlowOutput`.
- Modify `whisprbar/main.py`: execute action result without bypassing paste safety.
- Modify `whisprbar/ui/recording_indicator.py`: show action status.
- Modify tests: `tests/test_flow_commands.py`, `tests/test_flow_pipeline.py`, `tests/test_main_flow_actions.py`, `tests/test_main_flow_integration.py`.

### Task 1: Define Flow Action Result

**Files:**
- Create: `whisprbar/flow/actions.py`
- Test: `tests/test_flow_commands.py`

- [ ] **Step 1: Write model tests**

Add a test:

```python
def test_flow_action_result_defaults_to_safe_local_action():
    from whisprbar.flow.actions import FlowActionResult

    result = FlowActionResult(action_id="copy_last", text="hello")

    assert result.action_id == "copy_last"
    assert result.requires_confirmation is False
    assert result.external_write is False
```

- [ ] **Step 2: Run failing test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_commands.py::test_flow_action_result_defaults_to_safe_local_action -q
```

Expected: FAIL until `actions.py` exists.

- [ ] **Step 3: Implement action dataclass**

Create `FlowActionResult` with fields: `action_id`, `text`, `paste_policy`, `requires_confirmation`, `external_write`, `status`, and `message`.

### Task 2: Route Existing Commands To Actions

**Files:**
- Modify: `whisprbar/flow/commands.py`
- Modify: `whisprbar/flow/pipeline.py`
- Test: `tests/test_flow_pipeline.py`

- [ ] **Step 1: Write command routing tests**

Add tests proving `"als liste"` maps to a list-format action and `"nur in die zwischenablage"` remains a paste policy command.

- [ ] **Step 2: Implement routing**

Keep current command detection behavior. Add action metadata only for commands that need behavior beyond text rewrite or paste policy.

- [ ] **Step 3: Run Flow tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_commands.py tests\test_flow_pipeline.py -q
```

Expected: PASS.

### Task 3: Execute One High-Value Local Action End-To-End

**Files:**
- Modify: `whisprbar/main.py`
- Modify: `whisprbar/ui/recording_indicator.py`
- Test: `tests/test_main_flow_actions.py`
- Test: `tests/test_main_flow_integration.py`

- [ ] **Step 1: Write end-to-end action test**

Add a test for `copy_last` or `scratchpad_append` that proves no external write occurs and failure falls back to a visible local error.

- [ ] **Step 2: Implement local action execution**

Handle local-only actions in `dispatch_transcript_text()` after Flow processing and before paste. Do not execute external network actions in this track.

- [ ] **Step 3: Run Track D verifier**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_flow_commands.py tests\test_flow_pipeline.py tests\test_main_flow_actions.py tests\test_main_flow_integration.py -q
```

Expected: PASS.

### Task 4: Commit Track D

```powershell
git diff --check
git add whisprbar/flow/actions.py whisprbar/flow/commands.py whisprbar/flow/pipeline.py whisprbar/main.py whisprbar/ui/recording_indicator.py tests/test_flow_commands.py tests/test_flow_pipeline.py tests/test_main_flow_actions.py tests/test_main_flow_integration.py
git commit -m "feat: add safe flow actions"
```
