"""Tests for integrating Flow pipeline into main dictation path."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from whisprbar.flow.models import FlowOutput, PastePolicy


@pytest.fixture(autouse=True)
def isolate_transcript_database(monkeypatch):
    """Keep main-flow tests from writing to the user's real transcript DB."""
    from whisprbar import main

    monkeypatch.setattr(main, "save_transcript_record", MagicMock())


@pytest.mark.unit
def test_dispatch_transcript_uses_flow_final_text(monkeypatch):
    from whisprbar import main

    flow_output = FlowOutput(
        raw_text="raw text",
        final_text="Final text",
        profile_id="email",
        rewrite_status="applied",
        metadata={"raw_text": "raw text", "profile_id": "email"},
        paste_policy=PastePolicy(sequence="clipboard"),
    )
    monkeypatch.setattr(main, "process_flow_text", lambda text, language, cfg: flow_output)
    mock_history = MagicMock()
    mock_paste = MagicMock()
    monkeypatch.setattr(main, "write_history", mock_history)
    monkeypatch.setattr(main, "auto_paste", mock_paste)
    main.cfg["auto_paste_enabled"] = True
    main.cfg["language"] = "en"

    result = main.dispatch_transcript_text("raw text", output_seconds=2.0)

    assert result == flow_output
    assert main.state.last_transcript == "Final text"
    mock_history.assert_called_once()
    assert mock_history.call_args.args[:3] == ("Final text", 2.0, 2)
    assert mock_history.call_args.kwargs["metadata"]["profile_id"] == "email"
    mock_paste.assert_called_once_with("Final text", policy=flow_output.paste_policy)


@pytest.mark.unit
def test_dispatch_transcript_persists_analysis_record(monkeypatch):
    from whisprbar import main

    flow_output = FlowOutput(
        raw_text="raw text",
        final_text="Final text",
        profile_id="email",
        rewrite_status="applied",
        metadata={"raw_text": "raw text", "profile_id": "email", "rewrite_status": "applied"},
        paste_policy=PastePolicy(sequence="clipboard"),
    )
    mock_store = MagicMock()
    monkeypatch.setattr(main, "process_flow_text", lambda text, language, cfg: flow_output)
    monkeypatch.setattr(main, "write_history", MagicMock())
    monkeypatch.setattr(main, "save_transcript_record", mock_store, raising=False)
    monkeypatch.setattr(main, "auto_paste", MagicMock())
    main.cfg["auto_paste_enabled"] = True
    main.cfg["language"] = "en"
    main.cfg["transcription_backend"] = "deepgram"

    main.dispatch_transcript_text("raw text", output_seconds=2.0)

    mock_store.assert_called_once()
    assert mock_store.call_args.args[:3] == ("Final text", 2.0, 2)
    assert mock_store.call_args.kwargs["metadata"]["raw_text"] == "raw text"
    assert mock_store.call_args.kwargs["metadata"]["profile_id"] == "email"
    assert mock_store.call_args.kwargs["metadata"]["rewrite_status"] == "applied"
    assert mock_store.call_args.kwargs["config"] is main.cfg


@pytest.mark.unit
def test_dispatch_transcript_persists_latency_metadata(monkeypatch):
    from whisprbar import main

    monotonic_values = iter([10.0, 10.125, 20.0, 20.01])
    flow_output = FlowOutput(
        raw_text="raw text",
        final_text="Final text",
        profile_id="default",
        metadata={"raw_text": "raw text"},
    )
    mock_store = MagicMock()

    monkeypatch.setattr(main.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(main, "process_flow_text", lambda text, language, cfg: flow_output)
    monkeypatch.setattr(main, "write_history", MagicMock())
    monkeypatch.setattr(main, "save_transcript_record", mock_store, raising=False)
    monkeypatch.setattr(main, "copy_to_clipboard", MagicMock(return_value=True))
    main.cfg["auto_paste_enabled"] = False
    main.cfg["language"] = "en"

    main.dispatch_transcript_text(
        "raw text",
        output_seconds=1.0,
        runtime_metadata={"transcribe_ms": 42.0, "audio_process_ms": 12.5},
    )

    metadata = mock_store.call_args.kwargs["metadata"]
    assert metadata["flow_ms"] == pytest.approx(125.0)
    assert metadata["paste_ms"] == pytest.approx(10.0)
    assert metadata["transcribe_ms"] == 42.0
    assert metadata["audio_process_ms"] == 12.5


@pytest.mark.unit
def test_dispatch_transcript_copies_when_auto_paste_disabled(monkeypatch):
    from whisprbar import main

    flow_output = FlowOutput(raw_text="hello", final_text="Hello", profile_id="default")
    monkeypatch.setattr(main, "process_flow_text", lambda text, language, cfg: flow_output)
    monkeypatch.setattr(main, "write_history", MagicMock())
    mock_copy = MagicMock(return_value=True)
    monkeypatch.setattr(main, "copy_to_clipboard", mock_copy)
    main.cfg["auto_paste_enabled"] = False
    main.cfg["language"] = "en"

    main.dispatch_transcript_text("hello", output_seconds=1.0)

    mock_copy.assert_called_once_with("Hello")


@pytest.mark.unit
def test_dispatch_transcript_uses_german_status_labels(monkeypatch):
    from whisprbar import main

    flow_output = FlowOutput(raw_text="hallo", final_text="Hallo Welt", profile_id="default")
    overlay_updates = []
    phases = []
    mock_notify = MagicMock()

    monkeypatch.setattr(main, "process_flow_text", lambda text, language, cfg: flow_output)
    monkeypatch.setattr(main, "write_history", MagicMock())
    monkeypatch.setattr(main, "copy_to_clipboard", MagicMock(return_value=True))
    monkeypatch.setattr(main, "notify", mock_notify)
    main.cfg["auto_paste_enabled"] = False
    main.cfg["language"] = "de"

    main.dispatch_transcript_text(
        "hallo",
        output_seconds=1.0,
        update_overlay_func=lambda text, status: overlay_updates.append((text, status)),
        show_indicator_func=lambda phase, cfg, info="": phases.append((phase, info)),
    )

    assert overlay_updates == [("Hallo Welt", "Fertig")]
    assert phases == [("complete", "(2 Wörter · 2.0 W/s)")]
    mock_notify.assert_called_once_with("Transkription: Hallo Welt...")


@pytest.mark.unit
def test_dispatch_transcript_shows_paste_before_done(monkeypatch):
    from whisprbar import main

    phases = []
    flow_output = FlowOutput(raw_text="raw", final_text="Final text", profile_id="default")
    monkeypatch.setattr(main, "process_flow_text", lambda text, language, cfg: flow_output)
    monkeypatch.setattr(main, "write_history", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "auto_paste", lambda *_args, **_kwargs: None)
    main.cfg["auto_paste_enabled"] = True
    main.cfg["language"] = "en"

    main.dispatch_transcript_text(
        "raw",
        output_seconds=1.0,
        show_indicator_func=lambda phase, cfg, info="": phases.append((phase, info)),
    )

    assert [phase for phase, _info in phases] == ["pasting", "complete"]


@pytest.mark.unit
def test_transcribe_processed_audio_prefers_claimed_live_session(monkeypatch):
    """Stop processing should finish its claimed streaming session before batch ASR."""
    from whisprbar import main

    class FakeSession:
        def __init__(self):
            self.finished = False

        def finish(self):
            self.finished = True
            return "live transcript"

    session = FakeSession()
    monkeypatch.setattr(main, "_active_live_transcription_session", session, raising=False)
    live_finish = main._start_live_transcription_finish()

    def fail_batch(_processed, _language):
        raise AssertionError("batch transcription should not run when live session has text")

    monkeypatch.setattr(main, "transcribe_audio", fail_batch)

    text, elapsed_ms = main._transcribe_processed_audio(
        np.ones(16000, dtype=np.float32),
        "en",
        live_finish=live_finish,
    )

    assert text == "live transcript"
    assert elapsed_ms >= 0
    assert session.finished is True
    assert main._active_live_transcription_session is None


@pytest.mark.unit
def test_start_live_transcription_session_stores_backend_session(monkeypatch):
    """Recording start should create a live session when the backend supports it."""
    from whisprbar import main

    class FakeSession:
        pass

    class FakeTranscriber:
        def __init__(self):
            self.languages = []

        def start_streaming(self, language):
            self.languages.append(language)
            return session

    session = FakeSession()
    transcriber = FakeTranscriber()
    monkeypatch.setattr(main, "get_transcriber", lambda: transcriber)
    monkeypatch.setitem(main.cfg, "language", "en")
    monkeypatch.setattr(main, "_active_live_transcription_session", None, raising=False)

    main._start_live_transcription_session()

    assert transcriber.languages == ["en"]
    assert main._active_live_transcription_session is session


@pytest.mark.unit
def test_push_live_audio_chunk_forwards_to_active_session(monkeypatch):
    """Captured audio frames should be sent to the active live backend session."""
    from whisprbar import main

    received = []

    class FakeSession:
        def push_audio(self, audio):
            received.append(audio)

    frame = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)
    session = FakeSession()
    monkeypatch.setattr(main, "_active_live_transcription_session", session, raising=False)

    main._push_live_audio_chunk(frame)

    assert len(received) == 1
    np.testing.assert_array_equal(received[0], np.array([0.1, 0.2, 0.3], dtype=np.float32))
    assert received[0] is not frame
