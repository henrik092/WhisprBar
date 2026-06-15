# Transcript SQLite Store Implementation Plan

Status: Implemented before local documentation integration on 2026-06-15. Kept as historical implementation context, not as an active checklist.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store every successful WhisprBar dictation in a durable SQLite database for later script and AI-model analysis.

**Architecture:** Add `whisprbar/transcript_store.py` as the single SQLite boundary. Keep the existing JSONL history for current UI behavior, and call the SQLite store from `dispatch_transcript_text()` with the same final transcript metadata.

**Tech Stack:** Python standard library `sqlite3`, JSON metadata, pytest.

---

## File Structure

- Create `whisprbar/transcript_store.py`: SQLite schema creation and insert helper.
- Create `tests/test_transcript_store.py`: unit tests for schema, insert, metadata, and privacy opt-out.
- Modify `whisprbar/main.py`: import and call `save_transcript_record()`.
- Modify `tests/test_main_flow_integration.py`: verify dispatch persists the final transcript to the database helper.

### Task 1: SQLite Store Module

**Files:**
- Create: `whisprbar/transcript_store.py`
- Test: `tests/test_transcript_store.py`

- [ ] **Step 1: Write failing tests**

```python
def test_save_transcript_record_creates_sqlite_row(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    row_id = save_transcript_record(
        "Final text",
        1.25,
        2,
        metadata={
            "raw_text": "raw text",
            "profile_id": "email",
            "rewrite_status": "applied",
        },
        config={"language": "en", "transcription_backend": "openai"},
        database_path=database_path,
        created_at="2026-05-30T10:00:00+00:00",
    )
    assert row_id == 1
    rows = database_path_rows(database_path)
    assert rows[0]["text"] == "Final text"
    assert rows[0]["raw_text"] == "raw text"
    assert rows[0]["profile_id"] == "email"
    assert rows[0]["metadata"]["rewrite_status"] == "applied"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcript_store.py -q`
Expected: FAIL because `whisprbar.transcript_store` does not exist.

- [ ] **Step 3: Implement minimal store**

Create `save_transcript_record()`, schema creation, JSON metadata serialization, and privacy opt-out for `flow_history_storage == "never"`.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_transcript_store.py -q`
Expected: PASS.

### Task 2: Main Dispatch Integration

**Files:**
- Modify: `whisprbar/main.py`
- Modify: `tests/test_main_flow_integration.py`

- [ ] **Step 1: Write failing dispatch test**

Assert `dispatch_transcript_text()` calls `save_transcript_record()` with the final text, duration, word count, Flow metadata, and live config.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_main_flow_integration.py::test_dispatch_transcript_persists_analysis_record -q`
Expected: FAIL because the call is not wired yet.

- [ ] **Step 3: Wire the call**

Import `save_transcript_record` in `whisprbar/main.py` and call it immediately after `write_history()`.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/pytest tests/test_transcript_store.py tests/test_main_flow_integration.py -q`
Expected: PASS.

### Task 3: Verification

**Files:**
- Verify all modified code.

- [ ] **Step 1: Run test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 2: Run compile check**

Run: `.venv/bin/python -m compileall -q whisprbar tests`
Expected: PASS with no output.
