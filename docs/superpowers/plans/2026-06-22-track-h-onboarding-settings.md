# Track H Onboarding And Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make backend setup, microphone readiness, latency expectations, and troubleshooting obvious to normal users.

**Architecture:** Improve the existing WebKit settings UI with a small readiness model. Do not redesign the whole app shell. Reuse diagnostics and config helpers, and keep user-facing copy honest about cloud, local, X11, and Wayland behavior.

**Tech Stack:** Existing `settings_webview.py`, i18n dictionaries, diagnostics helpers, pytest.

---

## File Structure

- Modify `whisprbar/ui/settings_webview.py`: render setup/readiness sections.
- Modify `whisprbar/ui/diagnostics.py`: expose backend and microphone readiness data if not already available.
- Modify `whisprbar/i18n.py`: add concise copy for setup states.
- Modify `whisprbar/config.py` and `whisprbar/config_types.py`: only if a new persisted preference is required.
- Modify tests: `tests/test_settings_webview.py`, `tests/test_config.py`, `tests/test_project_metadata.py`.

### Task 1: Add Backend Setup Readiness

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Modify: `whisprbar/i18n.py`
- Test: `tests/test_settings_webview.py`

- [ ] **Step 1: Write readiness HTML test**

Add a test rendering selected backend states:

```python
def test_settings_html_shows_backend_setup_readiness():
    html = generate_settings_html(
        {
            "language": "en",
            "transcription_backend": "deepgram",
            "flow_mode_enabled": True,
        },
        dictionary_entries=[],
        snippets=[],
        transcript_stats={"total": 0},
    )

    assert "Backend readiness" in html
    assert "Deepgram" in html
    assert "API key" in html
```

- [ ] **Step 2: Run failing test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_settings_webview.py::test_settings_html_shows_backend_setup_readiness -q
```

Expected: FAIL until readiness UI exists.

- [ ] **Step 3: Implement readiness section**

Add a compact setup card near transcription/advanced settings. Do not print actual API key values.

### Task 2: Add Microphone Test Affordance

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Test: `tests/test_settings_webview.py`

- [ ] **Step 1: Write microphone test HTML assertion**

Assert settings HTML contains a microphone-test button or action identifier and copy explaining that it tests input level only.

- [ ] **Step 2: Implement UI affordance**

Add button markup and local JS event plumbing if the settings bridge already supports actions. If the bridge does not support actions, render a disabled "coming through diagnostics" affordance with clear copy and no fake behavior.

- [ ] **Step 3: Run settings tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_settings_webview.py -q
```

Expected: PASS.

### Task 3: Add Honest Latency/Profile Copy

**Files:**
- Modify: `whisprbar/i18n.py`
- Modify: `whisprbar/ui/settings_webview.py`
- Test: `tests/test_settings_webview.py`

- [ ] **Step 1: Add tests for profile labels**

Assert HTML contains profile descriptions for fast cloud, private local, and reliable fallback without promising exact latency.

- [ ] **Step 2: Implement copy**

Use wording such as "fastest when network is healthy", "private but depends on local model setup", and "fallback when live streaming fails".

- [ ] **Step 3: Run Track H verifier**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_settings_webview.py tests\test_config.py tests\test_project_metadata.py -q
```

Expected: PASS, with existing Windows-only POSIX mode caveat documented if `tests/test_config.py` hits it.

### Task 4: Commit Track H

```powershell
git diff --check
git add whisprbar/ui/settings_webview.py whisprbar/ui/diagnostics.py whisprbar/i18n.py whisprbar/config.py whisprbar/config_types.py tests/test_settings_webview.py tests/test_config.py tests/test_project_metadata.py
git commit -m "feat: add setup readiness guidance"
```
