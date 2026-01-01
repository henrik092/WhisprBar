# BUG-010: Circular Import Risk

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/transcription.py:1-30`
**Impact:** Fragile architecture, potential ImportError in future changes

---

## Problem Statement

The `transcription.py` module imports functions from `audio.py`, creating a potential circular import if `audio.py` ever imports from `transcription.py`.

---

## Technical Details

**Root Cause:** Direct import of audio functions in transcription module.

**Current Code:**
```python
# transcription.py:26-27
from .audio import apply_vad, apply_noise_reduction, SAMPLE_RATE, CHANNELS
```

**Risk Analysis:**
- Currently works because `audio.py` doesn't import from `transcription.py`
- If future features require `audio.py` to use transcription (e.g., batch processing), circular import will occur
- Comment at lines 24-25 says "no circular import exists" but doesn't prevent future issues

**Import Chain:**
```
transcription.py
    └── imports from audio.py
        └── If audio.py ever imports from transcription.py → CIRCULAR!
```

---

## Reproduction

**Steps:**
1. Add any import from `transcription.py` in `audio.py`
2. Run `python -c "from whisprbar.transcription import transcribe_audio"`
3. Get `ImportError: cannot import name 'X' from partially initialized module`

**Test Case:**
```python
import sys
import importlib

def test_no_circular_imports():
    """Test that modules can be imported in any order."""
    modules = [
        "whisprbar.config",
        "whisprbar.audio",
        "whisprbar.transcription",
        "whisprbar.main"
    ]

    for order in itertools.permutations(modules):
        # Clear module cache
        for mod in modules:
            if mod in sys.modules:
                del sys.modules[mod]

        # Try importing in this order
        try:
            for mod in order:
                importlib.import_module(mod)
        except ImportError as e:
            print(f"FAIL: Order {order} failed: {e}")
            return False

    print("PASS: No circular imports")
    return True
```

---

## Proposed Solution

**Approach:** Use lazy imports within functions instead of module-level imports.

**Fixed Code:**
```python
# transcription.py - Remove module-level import
# OLD:
# from .audio import apply_vad, apply_noise_reduction, SAMPLE_RATE, CHANNELS

# NEW: Constants can stay at module level
SAMPLE_RATE = 16000  # Or import from config
CHANNELS = 1

def transcribe_audio(audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio using selected backend."""
    # Lazy import inside function - breaks circular dependency
    from .audio import apply_vad, apply_noise_reduction

    # ... rest of function ...
```

**Alternative:** Dependency injection
```python
def transcribe_audio(
    audio: np.ndarray,
    language: str = "de",
    preprocessor: Optional[Callable] = None
) -> Optional[str]:
    """Transcribe audio with optional preprocessing."""
    if preprocessor:
        audio = preprocessor(audio)
    # ...
```

**Testing:**
- [ ] Unit test: All import orders work
- [ ] Integration test: Application starts normally
- [ ] Static analysis: No circular dependencies

---

## Related Issues

- **Depends on:** None
- **Blocks:** None
- **Related:** Module architecture

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
