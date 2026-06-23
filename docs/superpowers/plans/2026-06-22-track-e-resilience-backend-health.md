# Track E Resilience And Backend Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make live backend failures visible, recoverable, and correctness-preserving.

**Architecture:** Track live-session health in the streaming session abstraction. Any dropped audio chunk, queue overflow, timeout, or connection failure invalidates the live result so batch fallback is used instead of partial text. Surface selected-backend readiness in diagnostics/settings without exposing secrets.

**Tech Stack:** Existing Deepgram/ElevenLabs realtime sessions, pytest, settings WebKit HTML, diagnostics helpers.

---

## File Structure

- Modify `whisprbar/transcription/base.py`: add live session health enum or dataclass.
- Modify `whisprbar/transcription/deepgram.py`: mark dropped chunks/timeout/failure invalid.
- Modify `whisprbar/transcription/elevenlabs.py`: same invalidation semantics.
- Modify `whisprbar/main.py`: log fallback reason in runtime metadata.
- Modify `whisprbar/ui/settings_webview.py`: display selected backend readiness.
- Modify tests: `tests/test_deepgram.py`, `tests/test_transcription.py`, `tests/test_main_audio_feedback.py`, `tests/test_settings_webview.py`.

### Task 1: Protect Against Partial Live Results

**Files:**
- Modify: `whisprbar/transcription/deepgram.py`
- Modify: `whisprbar/transcription/elevenlabs.py`
- Test: `tests/test_deepgram.py`
- Test: `tests/test_transcription.py`

- [ ] **Step 1: Add or keep queue-overflow tests**

Use tests named:

```python
def test_deepgram_realtime_session_discards_partial_text_after_queue_overflow(monkeypatch):
    ...
    assert session.finish() is None
```

and:

```python
def test_elevenlabs_realtime_session_discards_partial_text_after_queue_overflow(monkeypatch):
    ...
    assert session.finish() is None
```

- [ ] **Step 2: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_deepgram.py::test_deepgram_realtime_session_discards_partial_text_after_queue_overflow tests\test_transcription.py::test_elevenlabs_realtime_session_discards_partial_text_after_queue_overflow -q
```

Expected: FAIL until overflow invalidates live results.

- [ ] **Step 3: Implement invalidation**

Add `_invalidated = threading.Event()` or equivalent. Set it when `push_audio()` hits queue full, send fails, finalize times out hard, or receiver errors. `finish()` returns `None` if invalidated, even when `_result_parts` has text.

- [ ] **Step 4: Run backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_deepgram.py tests\test_transcription.py -q
```

Expected: PASS.

### Task 2: Record Fallback Reasons

**Files:**
- Modify: `whisprbar/main.py`
- Test: `tests/test_main_audio_feedback.py`
- Test: `tests/test_main_flow_integration.py`

- [ ] **Step 1: Write metadata test**

Add a test proving live failure adds `live_fallback_reason` or `live_session_status` to runtime metadata and then batch transcription is attempted.

- [ ] **Step 2: Implement metadata**

Have `_transcribe_processed_audio()` return text, elapsed milliseconds, and an optional status dictionary. Preserve existing callers by updating tests and call sites in one pass.

- [ ] **Step 3: Run integration tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_main_audio_feedback.py tests\test_main_flow_integration.py -q
```

Expected: PASS.

### Task 3: Add Backend Readiness Surface

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Test: `tests/test_settings_webview.py`

- [ ] **Step 1: Write readiness HTML test**

Add a test that renders settings with `transcription_backend="deepgram"` and no key status, then asserts the HTML contains a selected-backend readiness row and no secret value.

- [ ] **Step 2: Implement readiness data**

Use existing env/key detection helpers. Display status like "API key missing", "configured", "local backend", or "not installed" without printing key values.

- [ ] **Step 3: Run Track E verifier**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcription.py tests\test_deepgram.py tests\test_main_audio_feedback.py tests\test_settings_webview.py -q
```

Expected: PASS.

### Task 4: Commit Track E

```powershell
git diff --check
git add whisprbar/transcription/base.py whisprbar/transcription/deepgram.py whisprbar/transcription/elevenlabs.py whisprbar/main.py whisprbar/ui/settings_webview.py tests/test_deepgram.py tests/test_transcription.py tests/test_main_audio_feedback.py tests/test_main_flow_integration.py tests/test_settings_webview.py
git commit -m "fix: invalidate partial live transcription results"
```
