# BUG-E10: Missing Config Schema for ElevenLabs

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/config.py`
**Impact:** Hardcoded values, no user customization

---

## Problem Statement

ElevenLabs-specific options (model_id, language, etc.) are hardcoded. Users cannot customize ElevenLabs settings.

---

## Technical Details

**Current Code:**
```python
# transcription.py:549 - Hardcoded model
model_id="scribe_v2_realtime"
```

**Missing from DEFAULT_CFG:**
- `elevenlabs_model_id`
- `elevenlabs_language`
- `elevenlabs_timeout`

---

## Proposed Solution

**Add to config.py:**
```python
DEFAULT_CFG = {
    # ... existing ...
    "elevenlabs_model_id": "scribe_v2_realtime",
    "elevenlabs_timeout": 10.0,
}
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
