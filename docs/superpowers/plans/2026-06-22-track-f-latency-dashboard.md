# Track F Latency Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show local latency evidence so future performance work is measurable instead of guesswork.

**Architecture:** Reuse runtime metadata already written with transcript records. Add aggregation helpers in the transcript store and surface percentiles in the settings Analysis or Diagnostics area. Avoid exposing transcript text in exports unless explicitly requested.

**Tech Stack:** SQLite transcript store, JSON metadata, WebKit settings HTML, pytest.

---

## File Structure

- Modify `whisprbar/transcript_store.py`: aggregate latency metrics from metadata.
- Modify `whisprbar/ui/settings_webview.py`: render latency dashboard cards.
- Modify `whisprbar/main.py`: ensure metadata names remain stable.
- Modify tests: `tests/test_transcript_store.py`, `tests/test_settings_webview.py`, `tests/test_main_flow_integration.py`.

### Task 1: Aggregate Latency Metadata

**Files:**
- Modify: `whisprbar/transcript_store.py`
- Test: `tests/test_transcript_store.py`

- [ ] **Step 1: Write aggregation tests**

Add a test that inserts transcript records with metadata:

```python
{"transcribe_ms": 120.0, "flow_ms": 30.0, "paste_ms": 10.0, "backend": "deepgram"}
```

and asserts aggregate count, p50, p95, and backend split.

- [ ] **Step 2: Run failing test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcript_store.py::test_latency_stats_aggregate_metadata_percentiles -q
```

Expected: FAIL until aggregation exists.

- [ ] **Step 3: Implement aggregation**

Add `get_latency_stats(config=None)` that returns plain dictionaries with keys: `count`, `overall`, `by_backend`, and per-phase percentile values. Ignore records without numeric metadata.

- [ ] **Step 4: Run transcript store tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcript_store.py -q
```

Expected: PASS except any known Windows-only POSIX mode assertion if running full file on Windows; if that happens, run the focused latency tests and document the platform mismatch.

### Task 2: Render Latency Dashboard

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Test: `tests/test_settings_webview.py`

- [ ] **Step 1: Write HTML test**

Add a test rendering settings with latency stats and assert it contains `Latency`, `Transcription`, `Paste`, backend rows, and no raw transcript text.

- [ ] **Step 2: Implement rendering**

Add an Analysis section/card for latency. Keep numbers compact: p50, p95, sample count, and slowest phase.

- [ ] **Step 3: Run settings tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_settings_webview.py -q
```

Expected: PASS.

### Task 3: Preserve Metadata Contract

**Files:**
- Modify: `tests/test_main_flow_integration.py`
- Test: `tests/test_main_flow_integration.py`

- [ ] **Step 1: Add contract test**

Assert successful dispatch metadata can contain stable keys: `backend`, `input_seconds`, `output_seconds`, `audio_process_ms`, `transcribe_ms`, `flow_ms`, `paste_ms`, `recording_to_first_audio_ms`, `stop_to_asr_done_ms`.

- [ ] **Step 2: Run Track F verifier**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcript_store.py tests\test_settings_webview.py tests\test_main_flow_integration.py -q
```

Expected: PASS, with known Windows POSIX-mode caveat documented if encountered.

### Task 4: Commit Track F

```powershell
git diff --check
git add whisprbar/transcript_store.py whisprbar/ui/settings_webview.py tests/test_transcript_store.py tests/test_settings_webview.py tests/test_main_flow_integration.py
git commit -m "feat: add latency dashboard"
```
