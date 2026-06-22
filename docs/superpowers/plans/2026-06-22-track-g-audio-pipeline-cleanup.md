# Track G Audio Pipeline Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce post-stop CPU work and make audio handling easier to reason about without destabilizing recording.

**Architecture:** Extract small, testable audio-quality and processing decisions while keeping the sounddevice callback minimal. Keep batch fallback and current VAD/noise behavior intact until tests prove a safer replacement.

**Tech Stack:** NumPy, existing recorder/VAD/processing modules, pytest.

---

## File Structure

- Create `whisprbar/audio/quality.py`: audio energy and quality gate helpers.
- Modify `whisprbar/audio/processing.py`: keep DSP transforms separate from policy decisions.
- Modify `whisprbar/audio/recorder.py`: keep callback non-blocking and delegate policy to helpers.
- Modify `whisprbar/main.py`: use quality helpers instead of inline energy logic.
- Modify tests: `tests/test_audio.py`, `tests/test_main_audio_feedback.py`, `tests/test_transcription.py`.

### Task 1: Extract Audio Quality Gates

**Files:**
- Create: `whisprbar/audio/quality.py`
- Test: `tests/test_audio.py`

- [ ] **Step 1: Write quality tests**

Add tests for RMS calculation and threshold decision:

```python
def test_audio_quality_detects_low_energy_noise():
    from whisprbar.audio.quality import calculate_rms_energy, is_probably_speech

    audio = np.zeros(16000, dtype=np.float32)

    assert calculate_rms_energy(audio) == 0.0
    assert is_probably_speech(audio, min_audio_energy=0.0008) is False
```

- [ ] **Step 2: Run failing test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio.py::test_audio_quality_detects_low_energy_noise -q
```

Expected: FAIL until `quality.py` exists.

- [ ] **Step 3: Implement helpers**

Implement pure functions with no config imports and no side effects.

### Task 2: Replace Inline Energy Logic

**Files:**
- Modify: `whisprbar/main.py`
- Test: `tests/test_main_audio_feedback.py`

- [ ] **Step 1: Write integration test**

Add a test proving low-energy processed audio cancels live session and does not paste.

- [ ] **Step 2: Implement replacement**

Replace inline RMS logic in `on_recording_stop()` with `calculate_rms_energy()` and `is_probably_speech()`.

- [ ] **Step 3: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio.py tests\test_main_audio_feedback.py -q
```

Expected: PASS.

### Task 3: Guard Callback Performance

**Files:**
- Modify: `tests/test_audio.py`
- Modify: `whisprbar/audio/recorder.py`

- [ ] **Step 1: Add callback test**

Assert `recording_callback()` does not call VAD, noise reduction, transcript functions, or quality gates.

- [ ] **Step 2: Keep callback minimal**

If the test fails, move any policy work out of the callback and into stop/monitor paths.

- [ ] **Step 3: Run Track G verifier**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio.py tests\test_main_audio_feedback.py tests\test_transcription.py -q
```

Expected: PASS.

### Task 4: Commit Track G

```powershell
git diff --check
git add whisprbar/audio/quality.py whisprbar/audio/processing.py whisprbar/audio/recorder.py whisprbar/main.py tests/test_audio.py tests/test_main_audio_feedback.py tests/test_transcription.py
git commit -m "refactor: isolate audio quality gates"
```
