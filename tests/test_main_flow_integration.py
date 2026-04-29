"""Tests for integrating Flow pipeline into main dictation path."""

from unittest.mock import MagicMock

import pytest

from whisprbar.flow.models import FlowOutput, PastePolicy


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

