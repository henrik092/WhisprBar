# BUG-E13: Generic Error Messages

**Status:** Open
**Priority:** LOW
**Module:** Multiple locations
**Impact:** Poor user experience when errors occur

---

## Problem Statement

Error messages are too technical or generic. Users see "Transcription failed" without helpful context.

---

## Technical Details

**Current behavior:**
- Connection fails → "ElevenLabs async transcription failed: ..."
- User sees nothing or generic error

**Better approach:**
- Connection fails → "ElevenLabs: Check your internet connection"
- Auth fails → "ElevenLabs: Invalid API key"
- Timeout → "ElevenLabs: Server taking too long, try again"

---

## Proposed Solution

Add user-friendly error messages with `notify()` calls for common failure modes.

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
