# BUG-E09: No API Key Validation Before Connect

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/transcription.py:517-518`
**Impact:** Late failure, poor user feedback

---

## Problem Statement

The API key is only validated when the WebSocket connection fails. User doesn't know their key is invalid until first transcription attempt.

---

## Technical Details

**Current Code:**
```python
# transcription.py:517-518
if not self.ensure_client():  # Only checks key exists, not validity
    return None
```

---

## Proposed Solution

**Fixed Code:**
```python
def ensure_client(self) -> bool:
    with self.client_lock:
        if self.client is not None:
            return True

        api_key = self._get_api_key()
        if not api_key:
            return False

        try:
            from elevenlabs import ElevenLabs
            self.client = ElevenLabs(api_key=api_key)

            # Validate key with lightweight API call
            # (Implementation depends on ElevenLabs SDK)

            return True
        except Exception as exc:
            debug(f"ElevenLabs client init failed: {exc}")
            return False
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
