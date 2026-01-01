# BUG-E06: Arbitrary Sleep in Async Context

**Status:** Open
**Priority:** HIGH
**Module:** `whisprbar/transcription.py:583-584`
**Impact:** Either too long wait or missed transcripts

---

## Problem Statement

The code uses a hardcoded 500ms sleep to wait for final transcripts. This is unreliable - network latency varies, and 500ms may be too long or too short.

---

## Technical Details

**Current Code:**
```python
# transcription.py:583-584
await asyncio.sleep(0.5)  # Arbitrary 500ms
```

---

## Proposed Solution

**Fixed Code:**
```python
# Wait for actual completion with timeout
max_wait = 2.0
check_interval = 0.1
waited = 0

while waited < max_wait:
    if result_queue.empty() and no_more_data_expected:
        break
    await asyncio.sleep(check_interval)
    waited += check_interval
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
