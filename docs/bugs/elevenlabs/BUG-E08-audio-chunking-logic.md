# BUG-E08: Audio Chunking Calculation Wrong

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/transcription.py:572-578`
**Impact:** Incorrect chunk sizes, potential data issues

---

## Problem Statement

The audio chunking slices base64 string by byte count (32000), but base64 expands data by ~33%. This means chunks are actually ~0.75 seconds instead of 1 second.

---

## Technical Details

**Current Code:**
```python
# transcription.py:572-578
chunk_size = 32000  # "1 second = 32000 bytes at 16kHz"
for i in range(0, len(audio_base64), chunk_size):
    chunk = audio_base64[i : i + chunk_size]  # Slicing base64 string!
```

**Math:**
- Raw audio: 16000 samples/sec * 2 bytes = 32000 bytes/sec
- Base64 expansion: 32000 * 4/3 = ~42667 chars/sec
- Current code: 32000 base64 chars = ~24000 raw bytes = ~0.75 sec

---

## Proposed Solution

**Fixed Code:**
```python
# Calculate based on raw audio, not base64
samples_per_second = 16000
bytes_per_sample = 2
bytes_per_second = samples_per_second * bytes_per_sample

# Base64 expansion factor
chunk_raw_bytes = bytes_per_second  # 1 second
chunk_base64_chars = int(chunk_raw_bytes * 4 / 3) + 4  # +4 for padding

for i in range(0, len(audio_base64), chunk_base64_chars):
    chunk = audio_base64[i : i + chunk_base64_chars]
```

---

## Fix Tracking

- [x] Bug report created
- [ ] Fix implemented
- [ ] Merged to main

---

**Created:** 2025-12-07
