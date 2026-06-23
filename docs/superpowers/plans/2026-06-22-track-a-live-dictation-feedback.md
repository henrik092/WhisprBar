# Track A Live Dictation Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show useful live transcript feedback while the user is still speaking, without pasting interim text prematurely.

**Architecture:** Add a generic live transcript update contract to the transcription base layer, emit interim/final updates from Deepgram first, and route updates through `main.py` into the existing recording indicator/live overlay. Keep committed paste behavior driven only by final live session text or batch fallback.

**Tech Stack:** Python dataclasses, pytest, existing `StreamingTranscriptionSession`, Deepgram WebSocket messages, existing recording indicator and overlay helpers.

---

## File Structure

- Modify `whisprbar/transcription/base.py`: add a live update dataclass and callback type.
- Modify `whisprbar/transcription/deepgram.py`: emit interim and final transcript updates from `_handle_message()`.
- Modify `whisprbar/transcription/elevenlabs.py`: emit committed final updates when available; interim can remain unsupported initially.
- Modify `whisprbar/main.py`: pass a live update callback into `start_streaming()` and update UI state.
- Modify `whisprbar/ui/recording_indicator.py`: expose a lightweight live-text update path if no current method exists.
- Modify `tests/test_deepgram.py`, `tests/test_transcription.py`, `tests/test_main_flow_integration.py`, and `tests/test_recording_indicator_flow.py`.

### Task 1: Define The Live Update Contract

**Files:**
- Modify: `whisprbar/transcription/base.py`
- Test: `tests/test_transcription.py`

- [ ] **Step 1: Write the failing base-contract test**

Add a test named `test_live_transcript_update_contract_is_importable()`:

```python
def test_live_transcript_update_contract_is_importable():
    from whisprbar.transcription import LiveTranscriptUpdate

    update = LiveTranscriptUpdate(
        text="hello",
        is_final=False,
        backend="deepgram",
        received_at_monotonic=12.5,
    )

    assert update.text == "hello"
    assert update.is_final is False
    assert update.backend == "deepgram"
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcription.py::test_live_transcript_update_contract_is_importable -q
```

Expected: FAIL because `LiveTranscriptUpdate` does not exist yet.

- [ ] **Step 3: Implement the contract**

Add to `whisprbar/transcription/base.py`:

```python
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class LiveTranscriptUpdate:
    text: str
    is_final: bool
    backend: str
    received_at_monotonic: float


LiveTranscriptCallback = Callable[[LiveTranscriptUpdate], None]
```

Export both names from `whisprbar/transcription/__init__.py`.

- [ ] **Step 4: Run the test again**

Run the same focused command. Expected: PASS.

### Task 2: Emit Deepgram Interim Updates

**Files:**
- Modify: `whisprbar/transcription/deepgram.py`
- Test: `tests/test_deepgram.py`

- [ ] **Step 1: Write the failing Deepgram interim test**

Add `test_deepgram_realtime_session_emits_interim_updates()` with a fake callback:

```python
def test_deepgram_realtime_session_emits_interim_updates(monkeypatch):
    from whisprbar.transcription import LiveTranscriptUpdate

    monkeypatch.setattr(DeepgramRealtimeSession, "_run_thread", lambda self: None)
    received = []
    session = DeepgramRealtimeSession(
        "test-key",
        "wss://api.deepgram.com/v1/listen",
        on_update=received.append,
    )
    event = type("Event", (), {"set": lambda self: None})()

    session._handle_message(
        json.dumps({
            "type": "Results",
            "is_final": False,
            "channel": {"alternatives": [{"transcript": "live words"}]},
        }),
        event,
    )

    assert isinstance(received[0], LiveTranscriptUpdate)
    assert received[0].text == "live words"
    assert received[0].is_final is False
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_deepgram.py::test_deepgram_realtime_session_emits_interim_updates -q
```

Expected: FAIL because `DeepgramRealtimeSession` does not accept `on_update` yet.

- [ ] **Step 3: Implement Deepgram update emission**

Change `DeepgramRealtimeSession.__init__()` to accept `on_update: Optional[LiveTranscriptCallback] = None`, store it, and call it inside `_handle_message()` for any non-empty transcript. Use `is_final = bool(data.get("is_final", False))`. Continue appending to `_result_parts` only when `is_final` is true.

- [ ] **Step 4: Run Deepgram tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_deepgram.py -q
```

Expected: PASS.

### Task 3: Route Live Updates To The UI

**Files:**
- Modify: `whisprbar/main.py`
- Modify: `whisprbar/ui/recording_indicator.py`
- Test: `tests/test_main_flow_integration.py`
- Test: `tests/test_recording_indicator_flow.py`

- [ ] **Step 1: Write the failing main callback test**

Add `test_start_live_transcription_session_passes_update_callback()` in `tests/test_main_flow_integration.py`. Use a fake transcriber whose `start_streaming(language, on_update=None)` stores the callback. Assert the callback is callable and calling it does not paste text.

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_main_flow_integration.py::test_start_live_transcription_session_passes_update_callback -q
```

Expected: FAIL because `main._start_live_transcription_session()` currently passes only language.

- [ ] **Step 3: Implement update routing**

In `main.py`, add `_handle_live_transcript_update(update)` that stores the latest interim text in process state and updates the overlay/indicator only. It must not call `dispatch_transcript_text()`, `auto_paste()`, or `copy_to_clipboard()`.

- [ ] **Step 4: Add an indicator-facing test**

In `tests/test_recording_indicator_flow.py`, add a test proving the indicator can display a short live transcript preview without changing the phase to complete.

- [ ] **Step 5: Run Track A verifier**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_deepgram.py tests\test_transcription.py tests\test_main_flow_integration.py tests\test_recording_indicator_flow.py -q
```

Expected: PASS.

### Task 4: Commit Track A

- [ ] **Step 1: Run patch hygiene**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 2: Commit**

```powershell
git add whisprbar/transcription/base.py whisprbar/transcription/__init__.py whisprbar/transcription/deepgram.py whisprbar/transcription/elevenlabs.py whisprbar/main.py whisprbar/ui/recording_indicator.py tests/test_deepgram.py tests/test_transcription.py tests/test_main_flow_integration.py tests/test_recording_indicator_flow.py
git commit -m "feat: show live dictation feedback"
```
