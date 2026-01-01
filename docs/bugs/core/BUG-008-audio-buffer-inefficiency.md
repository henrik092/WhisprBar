# BUG-008: Audio Buffer Inefficiency

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/audio.py:148-235`
**Impact:** O(n) operations in VAD monitor, potential slowdown on long recordings

---

## Problem Statement

The VAD auto-stop monitor uses a `List` for the audio buffer with `pop(0)` operations, which are O(n) in Python. This causes inefficiency during long recordings.

**Note:** This is NOT a memory leak. The buffer is properly bounded by trimming logic at lines 188-193 and cleared in the `finally` block at line 233.

---

## Technical Details

**Root Cause:** Using `list.pop(0)` for FIFO behavior instead of `collections.deque`.

**Current Code:**
```python
# audio.py:162
audio_buffer: List[np.ndarray] = []

# audio.py:182
audio_buffer.append(chunk)

# audio.py:192 - O(n) operation!
removed = audio_buffer.pop(0)
```

**Performance Analysis:**
- `list.append()` - O(1) amortized
- `list.pop(0)` - O(n) - shifts all elements!
- For 1000 chunks: 1000 pop(0) = ~500,000 operations

**Buffer is bounded (not a leak):**
```python
# audio.py:188-193 - Trimming logic exists
if audio_buffer:
    total_samples = sum(chunk.shape[0] for chunk in audio_buffer)
    while total_samples > buffer_samples and len(audio_buffer) > 1:
        removed = audio_buffer.pop(0)
        total_samples -= removed.shape[0]

# audio.py:233 - Cleared on exit
finally:
    audio_buffer.clear()
```

---

## Reproduction

**Steps:**
1. Enable VAD auto-stop
2. Record for 5+ minutes
3. Monitor CPU usage - may increase over time

**Test Case:**
```python
import time
from collections import deque

def benchmark_list_vs_deque():
    # List with pop(0)
    lst = []
    start = time.time()
    for i in range(10000):
        lst.append(i)
        if len(lst) > 100:
            lst.pop(0)
    list_time = time.time() - start

    # Deque with popleft()
    dq = deque(maxlen=100)
    start = time.time()
    for i in range(10000):
        dq.append(i)
        # Auto-removes oldest when maxlen exceeded
    deque_time = time.time() - start

    print(f"List: {list_time:.4f}s, Deque: {deque_time:.4f}s")
    print(f"Deque is {list_time/deque_time:.1f}x faster")
```

---

## Proposed Solution

**Approach:** Replace `List` with `collections.deque(maxlen=...)` for O(1) operations.

**Fixed Code:**
```python
from collections import deque

def vad_auto_stop_monitor() -> None:
    """Monitor recording and auto-stop after sustained silence."""
    if not cfg.get("vad_auto_stop_enabled") or not VAD_AVAILABLE:
        return

    silence_threshold = max(0.5, float(cfg.get("vad_auto_stop_silence_seconds", 2.0)))
    check_interval = 0.5
    buffer_seconds = silence_threshold + 1.0
    buffer_samples = int(SAMPLE_RATE * buffer_seconds)

    # Use deque with maxlen for O(1) operations and auto-bounding
    max_chunks = int(buffer_samples / BLOCK_SIZE) + 1
    audio_buffer = deque(maxlen=max_chunks)

    # ... rest of function unchanged ...

    # No need for manual trimming - deque handles it automatically
    # No need for finally clear - deque auto-discards on append
```

**Benefits:**
- `deque.append()` - O(1)
- `deque.popleft()` - O(1)
- `maxlen` auto-bounds size - no manual trimming needed
- Cleaner code, fewer edge cases

**Testing:**
- [ ] Unit test: Verify deque operations are O(1)
- [ ] Integration test: Long recording performance stable
- [ ] Manual test: CPU usage stays constant during 10min recording

---

## Related Issues

- **Depends on:** None
- **Blocks:** None
- **Related:** VAD queue design (by design, not a bug)

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Tests written
- [ ] Code reviewed
- [ ] Merged to main
- [ ] Verified in production

---

**Created:** 2025-12-07
**Last Updated:** 2025-12-07
