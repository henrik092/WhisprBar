# BUG-E12: Wrong Streaming Support Flag

**Status:** Open
**Priority:** LOW
**Module:** `whisprbar/transcription.py:509`
**Impact:** Live overlay doesn't show interim results

---

## Problem Statement

`supports_streaming()` returns `False` for ElevenLabs, but it IS a streaming backend (WebSocket-based). This prevents live overlay from showing interim transcripts.

---

## Technical Details

**Current Code:**
```python
# Missing or returns False
def supports_streaming(self) -> bool:
    return False  # WRONG!
```

---

## Proposed Solution

**Fixed Code:**
```python
def supports_streaming(self) -> bool:
    return True

# Also implement interim transcript callback for live overlay
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
