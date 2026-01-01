# BUG-E04: Thread Safety of Client Access

**Status:** Open
**Priority:** HIGH
**Module:** `whisprbar/transcription.py:471-506`
**Impact:** Potential crash if client unloaded during transcription

---

## Problem Statement

The `self.client` is initialized with a lock but used in `transcribe()` without holding the lock. If `unload()` is called from another thread during transcription, `self.client` could become `None`.

---

## Technical Details

**Current Code:**
```python
def ensure_client(self) -> bool:
    with self.client_lock:
        if self.client is not None:
            return True
        # ... initialize ...

def transcribe(self, audio, language="de"):
    if not self.ensure_client():  # Lock released after this
        return None
    # self.client used WITHOUT lock!
    transcript = asyncio.run(transcribe_async())  # Uses self.client
```

---

## Proposed Solution

**Fixed Code:**
```python
def transcribe(self, audio, language="de"):
    with self.client_lock:
        if not self._ensure_client_unlocked():
            return None
        client_ref = self.client  # Copy reference while holding lock

    # Use client_ref outside lock
    transcript = self._transcribe_with_client(client_ref, audio, language)
    return transcript
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
