# BUG-007: Hotkey Listener Deadlock

**Status:** Open
**Priority:** CRITICAL
**Module:** `whisprbar/hotkeys.py:465-475`
**Impact:** Application hangs on shutdown, unresponsive to SIGTERM

---

## Problem Statement

The `HotkeyManager.stop()` method can cause a deadlock between the main thread and the keyboard listener thread. Although an `RLock` is used, it doesn't prevent cross-thread deadlocks.

---

## Technical Details

**Root Cause:** The `stop()` method holds the lock while calling `listener.stop()`, which blocks waiting for the listener thread to terminate. If the listener thread's callback tries to acquire the same lock, deadlock occurs.

**Current Code:**
```python
# hotkeys.py:465-475
def stop(self) -> None:
    """Stop the hotkey listener."""
    with self._lock:  # Main thread acquires lock
        if self._listener:
            self._listener.stop()  # Blocks waiting for listener thread
            # If listener thread is in callback and needs lock → DEADLOCK
            self._listener = None
        self._active_modifiers.clear()
        self._active_tokens.clear()
```

**Why RLock doesn't help:**
- `RLock` (line 301) allows the **same thread** to acquire the lock multiple times
- But this is a **cross-thread** issue:
  - Main thread holds lock → waits for listener thread to stop
  - Listener thread (in callback) → waits for lock
  - Result: DEADLOCK

**Deadlock Scenario:**
```
1. Main thread calls stop()
2. Main thread acquires _lock
3. Main thread calls listener.stop()
4. listener.stop() waits for listener thread to finish current callback
5. Listener thread in on_press/on_release tries to call a method that needs _lock
6. Listener thread waits for _lock
7. DEADLOCK: Main waits for listener, listener waits for lock
```

---

## Reproduction

**Steps:**
1. Start WhisprBar
2. Start recording (press hotkey)
3. While recording, send SIGTERM or call quit
4. Application hangs (may require `kill -9`)

**Alternative:**
1. Rapidly change hotkey settings 5+ times
2. Quit application
3. Process may hang

**Test Case:**
```python
import signal
import threading

def test_listener_stop_deadlock():
    manager = HotkeyManager()
    manager.register("test", ("", "f9"), lambda: None)
    manager.start()

    # Set timeout to detect deadlock
    def timeout_handler(signum, frame):
        raise TimeoutError("Deadlock detected!")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(5)  # 5 second timeout

    try:
        manager.stop()
        signal.alarm(0)  # Cancel alarm
        print("PASS: No deadlock")
    except TimeoutError:
        print("FAIL: Deadlock detected")
```

---

## Proposed Solution

**Approach:** Release lock before calling `listener.stop()` to prevent cross-thread deadlock.

**Fixed Code:**
```python
def stop(self) -> None:
    """Stop the hotkey listener.

    Thread-safe: Can be called from any thread.
    Prevents deadlock by releasing lock before stopping listener.
    """
    # Get reference and clear state while holding lock
    with self._lock:
        listener_to_stop = self._listener
        self._listener = None
        self._active_modifiers.clear()
        self._active_tokens.clear()

    # Stop listener OUTSIDE lock to prevent cross-thread deadlock
    if listener_to_stop:
        listener_to_stop.stop()
```

**Why this works:**
- Lock is released before `listener.stop()` is called
- Listener thread can complete any pending callbacks (including lock acquisition)
- Main thread waits for listener without holding the lock
- No deadlock possible

**Testing:**
- [ ] Unit test: `test_listener_stop_no_deadlock()` - must complete in < 5s
- [ ] Integration test: SIGTERM during recording → clean shutdown < 2s
- [ ] Manual test: Rapid hotkey changes → no hanging

---

## Related Issues

- **Depends on:** None
- **Blocks:** Clean shutdown functionality
- **Related:** Signal handler (already fixed in commit 35e770e)

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
