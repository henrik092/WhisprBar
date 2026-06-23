# Track B Smart Endpointing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop recordings faster and more naturally without cutting off speech.

**Architecture:** Add a small endpointing decision module that combines silence timing, audio energy, manual hotkey release, and live ASR finalization signals. Keep manual stop reliable and make aggressive behavior opt-in until enough latency evidence exists.

**Tech Stack:** Python dataclasses, existing audio recorder state, pytest, VAD monitor data, live ASR session state.

---

## File Structure

- Create `whisprbar/audio/endpointing.py`: endpointing state and decisions.
- Modify `whisprbar/audio/recorder.py`: integrate endpointing without blocking the audio callback.
- Modify `whisprbar/main.py`: allow live finalization to overlap local VAD checks where safe.
- Modify `whisprbar/config.py` and `whisprbar/config_types.py`: add endpointing profile defaults only if needed.
- Modify `whisprbar/ui/settings_webview.py`: expose endpointing profile only after backend behavior is stable.
- Add `tests/test_endpointing.py`.
- Modify `tests/test_audio.py` and `tests/test_main_audio_feedback.py`.

### Task 1: Add Endpointing Decision Model

**Files:**
- Create: `whisprbar/audio/endpointing.py`
- Test: `tests/test_endpointing.py`

- [ ] **Step 1: Write model tests**

Add:

```python
def test_endpointing_keeps_listening_during_short_pause():
    from whisprbar.audio.endpointing import EndpointingState, decide_endpoint

    decision = decide_endpoint(
        EndpointingState(
            speech_seen=True,
            silence_ms=250,
            final_text_seen=False,
            manual_stop=False,
            profile="balanced",
        )
    )

    assert decision.should_stop is False
    assert decision.reason == "continue"
```

and:

```python
def test_endpointing_stops_after_final_text_and_silence():
    from whisprbar.audio.endpointing import EndpointingState, decide_endpoint

    decision = decide_endpoint(
        EndpointingState(
            speech_seen=True,
            silence_ms=900,
            final_text_seen=True,
            manual_stop=False,
            profile="balanced",
        )
    )

    assert decision.should_stop is True
    assert decision.reason == "final_text_and_silence"
```

- [ ] **Step 2: Run failing tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_endpointing.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement model**

Create dataclasses `EndpointingState` and `EndpointingDecision`. Implement `decide_endpoint()` with conservative thresholds: manual stop always stops; no speech never auto-stops; balanced profile stops on final text plus at least 800 ms silence.

- [ ] **Step 4: Run model tests**

Run the same command. Expected: PASS.

### Task 2: Integrate Without Blocking Audio Callback

**Files:**
- Modify: `whisprbar/audio/recorder.py`
- Test: `tests/test_audio.py`

- [ ] **Step 1: Write recorder integration tests**

Add tests proving that endpointing state is updated outside the sounddevice callback and that the callback only copies/queues frames.

- [ ] **Step 2: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio.py::test_recording_callback_forwards_audio_chunks_to_streaming_callback tests\test_audio.py -q
```

Expected: PASS after implementation.

- [ ] **Step 3: Implement integration**

Keep `recording_callback()` limited to queueing frames and level/live callbacks. Put endpointing checks in the existing monitor thread or a new lightweight monitor that observes queued state.

### Task 3: Overlap Live Finalization With Local Audio Checks

**Files:**
- Modify: `whisprbar/main.py`
- Test: `tests/test_main_audio_feedback.py`

- [ ] **Step 1: Write ordering test**

Use the existing style in `tests/test_main_audio_feedback.py` to assert live `finish()` starts before local VAD when both paths are needed. The expected sequence starts with `["finish", "vad"]`.

- [ ] **Step 2: Run the failing test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_main_audio_feedback.py::test_on_recording_stop_starts_live_finish_before_vad -q
```

Expected: FAIL until finalization overlap is implemented.

- [ ] **Step 3: Implement overlap**

Start live session `finish()` in a short background worker at stop time, run VAD/energy checks locally, then join the live result before choosing live text or batch fallback. Ensure no-speech/noise paths cancel or discard live output.

- [ ] **Step 4: Run Track B verifier**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_endpointing.py tests\test_audio.py tests\test_main_audio_feedback.py tests\test_main_flow_integration.py -q
```

Expected: PASS.

### Task 4: Commit Track B

```powershell
git diff --check
git add whisprbar/audio/endpointing.py whisprbar/audio/recorder.py whisprbar/main.py tests/test_endpointing.py tests/test_audio.py tests/test_main_audio_feedback.py
git commit -m "feat: add smart endpointing"
```
