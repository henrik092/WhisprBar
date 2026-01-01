# BUG-E07: Missing Connection Timeout

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/transcription.py:547-554`
**Impact:** Application may hang indefinitely on slow network

---

## Problem Statement

The WebSocket connection attempt has no timeout. If the network is slow or ElevenLabs API hangs, the application blocks indefinitely.

---

## Technical Details

**Current Code:**
```python
# transcription.py:547-554
connection = await self.client.speech_to_text.realtime.connect(
    RealtimeAudioOptions(...)
)
# No timeout!
```

---

## Proposed Solution

**Fixed Code:**
```python
try:
    connection = await asyncio.wait_for(
        self.client.speech_to_text.realtime.connect(
            RealtimeAudioOptions(...)
        ),
        timeout=10.0  # 10 second timeout
    )
except asyncio.TimeoutError:
    debug("ElevenLabs connection timeout after 10 seconds")
    return None
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
