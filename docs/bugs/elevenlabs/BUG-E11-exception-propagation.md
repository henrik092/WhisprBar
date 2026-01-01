# BUG-E11: Exception Details Not Propagated

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/transcription.py:592-608`
**Impact:** Generic errors, hard to diagnose issues

---

## Problem Statement

All exceptions are caught and converted to `None`. The caller doesn't know if the error was authentication, network, or API-related.

---

## Technical Details

**Current Code:**
```python
# transcription.py:592-608
except Exception as exc:
    debug(f"ElevenLabs async transcription failed: {exc}")
    return None  # Generic failure
```

---

## Proposed Solution

**Fixed Code:**
```python
class ElevenLabsError(Exception):
    def __init__(self, message: str, error_type: str):
        self.error_type = error_type
        super().__init__(message)

# In transcribe():
except asyncio.TimeoutError:
    debug("ElevenLabs timeout")
    notify("ElevenLabs: Connection timeout")
    return None
except AuthenticationError:
    debug("ElevenLabs auth failed")
    notify("ElevenLabs: Invalid API key")
    return None
except Exception as exc:
    debug(f"ElevenLabs error: {exc}")
    notify(f"ElevenLabs: {type(exc).__name__}")
    return None
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
