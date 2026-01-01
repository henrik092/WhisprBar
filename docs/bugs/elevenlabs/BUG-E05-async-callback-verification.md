# BUG-E05: Async Callback Registration Not Verified

**Status:** Open
**Priority:** HIGH
**Module:** `whisprbar/transcription.py:568-570`
**Impact:** Silent failure if event registration fails

---

## Problem Statement

The event callback registration doesn't verify success. If the event name is wrong or registration fails, no transcripts are received and the function silently returns empty.

---

## Technical Details

**Current Code:**
```python
# transcription.py:568-570
connection.on(
    RealtimeEvents.COMMITTED_TRANSCRIPT, on_committed_transcript
)
# No verification that registration succeeded
```

---

## Proposed Solution

**Fixed Code:**
```python
try:
    connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, on_committed_transcript)
    debug("Registered COMMITTED_TRANSCRIPT handler")
except Exception as exc:
    debug(f"Failed to register event handler: {exc}")
    await connection.close()
    return None
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
