# BUG-E02: Race Condition in Transcript Collection

**Status:** Open
**Priority:** CRITICAL
**Module:** `whisprbar/transcription.py:544-591`
**Impact:** Lost transcript data, incomplete transcriptions

---

## Problem Statement

The callback `on_committed_transcript` appends to a list (`result_text`) that is accessed from the main coroutine without synchronization. This causes a race condition where transcripts may be lost.

---

## Technical Details

**Root Cause:** Unsynchronized access to shared list between callback and main coroutine.

**Current Code:**
```python
# transcription.py:558-564
result_text = []  # Shared mutable list

def on_committed_transcript(data):
    text = data.get("text", "")
    if text:
        result_text.append(text)  # Called from callback thread

# transcription.py:590
return " ".join(result_text).strip()  # Accessed from main coroutine
```

**Race Condition:**
1. Callback fires, starts appending
2. Main coroutine reads list for join
3. Callback fires again during join
4. Data lost or corrupted

---

## Proposed Solution

**Fixed Code:**
```python
async def transcribe_async():
    result_queue = asyncio.Queue()

    def on_committed_transcript(data):
        text = data.get("text", "")
        if text:
            # Thread-safe queue operation
            asyncio.run_coroutine_threadsafe(
                result_queue.put(text),
                asyncio.get_event_loop()
            )

    # ... connection setup ...

    # Collect results with timeout
    results = []
    try:
        while True:
            text = await asyncio.wait_for(result_queue.get(), timeout=0.5)
            results.append(text)
    except asyncio.TimeoutError:
        pass  # No more data

    return " ".join(results).strip()
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Tests written
- [ ] Merged to main

---

**Created:** 2025-12-07
