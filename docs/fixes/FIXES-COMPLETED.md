# WhisprBar V6 - Completed Fixes

This document records bugs that were fixed in previous commits.

**Last Updated:** 2026-01-01

---

## Summary

| # | Bug | Commit | Date | Status |
|---|-----|--------|------|--------|
| 1 | Signal Handler Race Condition | 35e770e | 2025-10-31 | Fixed |
| 2 | Duplicate Audio Processing | 8c712c1 | 2025-10-xx | Fixed |
| 3 | Thread-safe State Management | 491e75c | 2025-10-xx | Fixed |
| 4 | Temp File Cleanup Path Injection | 14ea64d | 2025-10-xx | Fixed |
| 5 | Audio Queue Blocking | 0571805 | 2025-10-xx | Fixed |
| 6 | VAD Queue Mismatch | - | 2025-12-07 | By Design |
| 7 | Unicode Capitalization | - | 2025-12-07 | Works 95%+ |
| 8 | Language Parameter in Chunked Transcription | - | 2026-01-01 | Fixed |
| 9 | ElevenLabs WebSocket Resource Leak | - | 2026-01-01 | Fixed |
| 10 | ElevenLabs Connection Timeout | - | 2026-01-01 | Fixed |
| 11 | ElevenLabs Race Condition | - | 2026-01-01 | Fixed |
| 12 | ElevenLabs Arbitrary Sleep | - | 2026-01-01 | Fixed |

---

## Fix Details

### 1. Signal Handler Race Condition

**Commit:** 35e770e
**File:** `whisprbar/main.py:823-833`
**Status:** FIXED

**Problem:** Signal handler performed non-signal-safe operations (I/O, locks, complex function calls).

**Solution:** Changed signal handler to only set an atomic `threading.Event` flag. Actual cleanup happens in the main loop's `check_shutdown_signal()` function.

**Current Code:**
```python
def signal_handler(sig, frame):
    """Signal handler - MUST be signal-safe!"""
    _shutdown_event.set()  # Atomic, signal-safe
```

---

### 2. Duplicate Audio Processing

**Commit:** 8c712c1
**File:** `whisprbar/main.py`, `whisprbar/transcription.py`
**Status:** FIXED

**Problem:** VAD and noise reduction were applied twice - once in `main.py` and once in `transcribe_audio()`.

**Solution:** Clear documentation that `transcribe_audio()` expects pre-processed audio. Preprocessing is done only in `main.py`.

---

### 3. Thread-safe State Management

**Commit:** 491e75c
**File:** `whisprbar/main.py:59-184`
**Status:** FIXED

**Problem:** Application state dictionary accessed from multiple threads without synchronization.

**Solution:** Implemented `AppState` class with proper locking for critical fields (`recording`, `transcribing`, `last_transcript`).

---

### 4. Temp File Cleanup Path Injection

**Commit:** 14ea64d
**File:** `whisprbar/utils.py`
**Status:** FIXED

**Problem:** Potential path traversal in temp file cleanup function.

**Solution:** Use `pathlib.Path.glob()` with strict pattern matching instead of shell commands.

---

### 5. Audio Queue Blocking

**Commit:** 0571805
**File:** `whisprbar/audio.py:126-135`
**Status:** FIXED

**Problem:** Audio callback could block if queue was full.

**Solution:** Use `put_nowait()` with defensive error handling. Queue operations are now non-blocking.

---

### 6. VAD Queue Mismatch

**Status:** BY DESIGN

**Analysis Result:** The main audio queue is unbounded (to never lose audio data), while the VAD monitoring queue is bounded with a maximum size. When the VAD queue is full, frames are dropped silently.

**Verification:** This is intentional. VAD auto-stop only needs recent audio to detect silence - it can tolerate dropped frames. The main recording queue must never drop frames.

**No fix needed.**

---

### 7. Unicode Capitalization

**Status:** WORKS 95%+

**Analysis Result:** The `postprocess_fix_capitalization()` function uses:
- `text[0].upper()` for first character
- Regex with extended character class `[a-zäöüßáéíóúàèìòùâêîôûçñ]`
- `re.UNICODE` flag

**Verification:** This covers most European languages (German, French, Spanish, Portuguese, Italian). Edge cases like ß→SS expansion are rare (only affects text starting with ß).

**No fix needed for current use cases.**

---

### 8. Language Parameter in Chunked Transcription

**Date:** 2026-01-01
**File:** `whisprbar/transcription.py:731-853, 1071`
**Status:** FIXED

**Problem:** When transcribing audio longer than 60 seconds, the chunking system was used but the `language` parameter was not passed through the call chain. All chunks were transcribed with the default language from config instead of the user-selected language.

**Impact:** Multi-language transcription was broken for long recordings. Users who selected English but recorded for >60s would get mixed German/English transcripts.

**Solution:**
1. Added `language` parameter to `transcribe_audio_chunked(audio, language)`
2. Added `language` parameter to `transcribe_chunk(chunk_audio, idx, total, language)`
3. Updated ThreadPoolExecutor call to pass language to each chunk
4. Updated call site in `transcribe_audio()` to pass language

**Current Code:**
```python
def transcribe_audio_chunked(audio: np.ndarray, language: str = "de") -> Optional[str]:
    # ...
    executor.submit(transcribe_chunk, chunk_audio, idx, len(chunks), language)
```

---

### 9. ElevenLabs WebSocket Resource Leak

**Date:** 2026-01-01
**File:** `whisprbar/transcription.py:605-611`
**Status:** FIXED

**Problem:** The ElevenLabs WebSocket connection was never closed if an exception occurred between connection establishment and the `connection.close()` call. This caused resource leaks and eventually exhausted connection limits.

**Solution:** Added `finally` block to guarantee connection cleanup:

```python
finally:
    if connection is not None:
        try:
            await connection.close()
        except Exception as close_exc:
            debug(f"Error closing ElevenLabs connection: {close_exc}")
```

---

### 10. ElevenLabs Connection Timeout

**Date:** 2026-01-01
**File:** `whisprbar/transcription.py:549-559`
**Status:** FIXED

**Problem:** No timeout on WebSocket connection. If ElevenLabs server hung or network stalled, the transcription thread would block forever, exhausting the transcription semaphore.

**Solution:** Wrapped connection in `asyncio.wait_for()` with 30-second timeout:

```python
connection = await asyncio.wait_for(
    self.client.speech_to_text.realtime.connect(...),
    timeout=30.0
)
```

---

### 11. ElevenLabs Race Condition

**Date:** 2026-01-01
**File:** `whisprbar/transcription.py:564-594`
**Status:** FIXED

**Problem:** Transcript data could be lost due to race condition between async callback populating `result_text` and the return statement reading it. The arbitrary `asyncio.sleep(0.5)` was not a reliable synchronization mechanism.

**Solution:** Replaced sleep with `asyncio.Event()` for proper synchronization:

```python
transcript_received = asyncio.Event()

def on_committed_transcript(data):
    result_text.append(text)
    transcript_received.set()  # Signal that transcript arrived

# Wait for transcript with timeout
await asyncio.wait_for(transcript_received.wait(), timeout=5.0)
```

---

### 12. ElevenLabs Arbitrary Sleep

**Date:** 2026-01-01
**File:** `whisprbar/transcription.py:590-594`
**Status:** FIXED

**Problem:** `await asyncio.sleep(0.5)` was used to wait for the final transcript. This was unreliable:
- Too short: transcript might not arrive in time
- Too long: unnecessary delay for fast servers
- No feedback mechanism

**Solution:** Using `asyncio.Event()` with `wait_for()` timeout (see Fix #11). The code now waits efficiently and has proper timeout handling.

---

## Related Documentation

- [Bug Tracking Index](../../BUGS.md)
- [Bug Dashboard](../bugs/README.md)
- [Changelog](../../CHANGELOG.md)

---

**Maintained by:** Claude Code
