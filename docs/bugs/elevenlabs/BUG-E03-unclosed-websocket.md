# BUG-E03: Unclosed WebSocket on Error

**Status:** Open
**Priority:** CRITICAL
**Module:** `whisprbar/transcription.py:544-608`
**Impact:** Resource leak, API quota consumption

---

## Problem Statement

If an exception occurs after the WebSocket connection is established but before `connection.close()` is called, the connection remains open, causing resource leaks.

---

## Technical Details

**Root Cause:** No `finally` block to ensure connection cleanup.

**Current Code:**
```python
# transcription.py:544-608
async def transcribe_async():
    try:
        connection = await self.client.speech_to_text.realtime.connect(...)

        # ... operations that might fail ...

        await connection.close()  # Only reached on success!
        return " ".join(result_text).strip()

    except Exception as exc:
        debug(f"ElevenLabs async transcription failed: {exc}")
        return None  # Connection NOT closed!
```

---

## Proposed Solution

**Fixed Code:**
```python
async def transcribe_async():
    connection = None
    try:
        connection = await self.client.speech_to_text.realtime.connect(...)

        # ... operations ...

        return " ".join(result_text).strip()

    except Exception as exc:
        debug(f"ElevenLabs async transcription failed: {exc}")
        return None

    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception as close_exc:
                debug(f"Error closing connection: {close_exc}")
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Tests written
- [ ] Merged to main

---

**Created:** 2025-12-07
