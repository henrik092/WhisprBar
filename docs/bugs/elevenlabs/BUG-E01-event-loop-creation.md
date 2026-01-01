# BUG-E01: Event Loop Creation in Non-Async Thread

**Status:** Open
**Priority:** CRITICAL
**Module:** `whisprbar/transcription.py:597`
**Impact:** Runtime crash when called from async context

---

## Problem Statement

The `ElevenLabsTranscriber.transcribe()` method uses `asyncio.run()` to run async code, which creates a new event loop. This fails if called from a thread that already has a running event loop.

---

## Technical Details

**Root Cause:** `asyncio.run()` cannot be called from within an existing event loop.

**Current Code:**
```python
# transcription.py:597
transcript = asyncio.run(transcribe_async())
```

**Failure Scenario:**
- If GTK or another library uses asyncio on the main thread
- If transcription is called from an async context
- `RuntimeError: asyncio.run() cannot be called from a running event loop`

---

## Reproduction

**Test Case:**
```python
import asyncio

async def test_from_async_context():
    transcriber = ElevenLabsTranscriber()
    audio = np.zeros(16000, dtype=np.float32)

    # This will fail with RuntimeError
    result = transcriber.transcribe(audio, "de")

asyncio.run(test_from_async_context())
```

---

## Proposed Solution

**Fixed Code:**
```python
def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
    # ... setup ...

    async def transcribe_async():
        # ... implementation ...

    # Handle both async and sync contexts
    try:
        loop = asyncio.get_running_loop()
        # Already in async context - use nest_asyncio or run in executor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, transcribe_async())
            transcript = future.result(timeout=30)
    except RuntimeError:
        # No running loop - safe to use asyncio.run()
        transcript = asyncio.run(transcribe_async())

    return transcript
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Tests written
- [ ] Merged to main

---

**Created:** 2025-12-07
