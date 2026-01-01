# BUG-011: Ignored Language Parameter

**Status:** Open
**Priority:** MEDIUM
**Module:** `whisprbar/transcription.py:280-461`
**Impact:** Streaming transcriber ignores user's language preference

---

## Problem Statement

The `StreamingTranscriber` (sherpa-onnx) accepts a `language` parameter in its `transcribe()` method but doesn't use it for recognition. The model is initialized once with a fixed language, ignoring subsequent transcribe calls with different languages.

---

## Technical Details

**Root Cause:** Language parameter accepted but not passed to recognizer.

**Current Code:**
```python
# transcription.py:374-431
def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio using sherpa-onnx.

    Args:
        audio: Audio data as float32 numpy array
        language: Language code (currently not used by sherpa-onnx)  # <-- Admits it!
    """
    # ... language parameter is never used ...
```

**Model Initialization:**
```python
# transcription.py:362
# Model initialized once with config, language not configurable per-call
```

**Silent Failure:**
- User sets language to "en" in settings
- Streaming backend still uses whatever language model was loaded
- No error, just wrong results

---

## Reproduction

**Steps:**
1. Set transcription backend to "streaming" (sherpa-onnx)
2. Set language to "en" (English)
3. Record German speech
4. Transcription may still work in German (depending on model)

**Test Case:**
```python
def test_language_parameter_used():
    """Verify language parameter affects transcription."""
    transcriber = StreamingTranscriber()

    # Create test audio (silence is fine for this test)
    audio = np.zeros(16000, dtype=np.float32)

    # Mock the recognizer to capture calls
    with patch.object(transcriber, 'recognizer') as mock_rec:
        transcriber.transcribe(audio, language="de")
        # Assert language was passed
        # (Implementation-specific verification)

        transcriber.transcribe(audio, language="en")
        # Assert language changed
```

---

## Proposed Solution

**Approach:** Either use the language parameter or document the limitation clearly.

**Option A: Use Language Parameter**
```python
def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio using sherpa-onnx.

    Args:
        audio: Audio data
        language: Language code for recognition
    """
    # Reinitialize recognizer if language changed
    if self._current_language != language:
        self._init_recognizer(language)
        self._current_language = language

    # ... rest of transcription ...
```

**Option B: Document Limitation**
```python
def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio using sherpa-onnx.

    Note:
        Language parameter is ignored. sherpa-onnx uses a multi-language
        model that auto-detects language. To force a specific language,
        use a different backend (OpenAI or ElevenLabs).
    """
    # Log warning if language specified
    if language != "de":
        debug(f"Warning: StreamingTranscriber ignores language='{language}'")
```

**Option C: Raise Error**
```python
def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
    if language not in self._supported_languages:
        raise ValueError(
            f"StreamingTranscriber doesn't support language '{language}'. "
            f"Use OpenAI or ElevenLabs backend for this language."
        )
```

**Recommended:** Option A if sherpa-onnx supports language switching, otherwise Option B.

**Testing:**
- [ ] Unit test: Verify language parameter is used/documented
- [ ] Integration test: DE vs EN produce expected behavior
- [ ] Manual test: User gets feedback if language unsupported

---

## Related Issues

- **Depends on:** None
- **Blocks:** None
- **Related:** ElevenLabs language handling

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
