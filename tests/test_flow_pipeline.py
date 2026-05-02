"""Tests for Flow Mode text pipeline orchestration."""

import pytest

from whisprbar.flow.models import AppContext, DictionaryEntry, Snippet
from whisprbar.flow.pipeline import process_flow_text
from whisprbar.flow.rewrite import RewriteResult


@pytest.mark.unit
def test_process_flow_text_disabled_uses_existing_cleanup(monkeypatch):
    monkeypatch.setattr(
        "whisprbar.flow.pipeline.detect_app_context",
        lambda: AppContext("x11"),
    )

    output = process_flow_text("hello , world", "en", {"flow_mode_enabled": False})

    assert output.raw_text == "hello , world"
    assert output.final_text == "Hello, world"
    assert output.profile_id == "default"
    assert output.rewrite_status == "not_requested"


@pytest.mark.unit
def test_process_flow_text_dictionary_runs_before_snippets(monkeypatch):
    monkeypatch.setattr(
        "whisprbar.flow.pipeline.detect_app_context",
        lambda: AppContext("x11", app_class="obsidian"),
    )
    monkeypatch.setattr(
        "whisprbar.flow.pipeline.load_dictionary",
        lambda: [DictionaryEntry(spoken="signatur", written="signature")],
    )
    monkeypatch.setattr(
        "whisprbar.flow.pipeline.load_snippets",
        lambda: [Snippet(trigger="signature", text="Best regards")],
    )

    output = process_flow_text(
        "signatur",
        "en",
        {"flow_mode_enabled": True, "flow_dictionary_enabled": True, "flow_snippets_enabled": True},
    )

    assert output.final_text == "Best regards"
    assert output.dictionary_hits == ("signatur",)
    assert output.snippet_hits == ("signature",)
    assert output.metadata["profile_id"] == "notes"


@pytest.mark.unit
def test_process_flow_text_command_overrides_rewrite_metadata(monkeypatch):
    monkeypatch.setattr("whisprbar.flow.pipeline.detect_app_context", lambda: AppContext("x11"))
    monkeypatch.setattr("whisprbar.flow.pipeline.load_dictionary", lambda: [])
    monkeypatch.setattr("whisprbar.flow.pipeline.load_snippets", lambda: [])

    output = process_flow_text(
        "team update make this shorter",
        "en",
        {"flow_mode_enabled": True, "flow_command_mode_enabled": True, "flow_rewrite_enabled": False},
    )

    assert output.final_text == "Team update"
    assert output.command == "shorter"
    assert output.metadata["command"] == "shorter"
    assert output.rewrite_status == "not_requested"


@pytest.mark.unit
def test_process_flow_text_rewrite_failure_keeps_local_text(monkeypatch):
    monkeypatch.setattr("whisprbar.flow.pipeline.detect_app_context", lambda: AppContext("x11"))
    monkeypatch.setattr("whisprbar.flow.pipeline.load_dictionary", lambda: [])
    monkeypatch.setattr("whisprbar.flow.pipeline.load_snippets", lambda: [])
    monkeypatch.setattr(
        "whisprbar.flow.pipeline.rewrite_text",
        lambda **kwargs: RewriteResult(text=kwargs["text"], status="failed"),
    )

    output = process_flow_text(
        "hello world",
        "en",
        {"flow_mode_enabled": True, "flow_rewrite_enabled": True, "flow_rewrite_provider": "openai_compatible"},
    )

    assert output.final_text == "Hello world"
    assert output.rewrite_status == "failed"


@pytest.mark.unit
def test_process_flow_text_rewrite_success_uses_rewritten_text(monkeypatch):
    monkeypatch.setattr(
        "whisprbar.flow.pipeline.detect_app_context",
        lambda: AppContext("x11", app_class="thunderbird", window_title="Inbox"),
    )
    monkeypatch.setattr("whisprbar.flow.pipeline.load_dictionary", lambda: [])
    monkeypatch.setattr("whisprbar.flow.pipeline.load_snippets", lambda: [])
    monkeypatch.setattr(
        "whisprbar.flow.pipeline.rewrite_text",
        lambda **kwargs: RewriteResult(text="Dear team,\nHello world", status="applied"),
    )

    output = process_flow_text(
        "hello world",
        "en",
        {"flow_mode_enabled": True, "flow_rewrite_enabled": True, "flow_rewrite_provider": "openai_compatible"},
    )

    assert output.final_text == "Dear team,\nHello world"
    assert output.profile_id == "email"
    assert output.rewrite_status == "applied"
    assert output.metadata["context"]["app_class"] == "thunderbird"


@pytest.mark.unit
def test_process_flow_text_passes_command_rewrite_mode_to_rewriter(monkeypatch):
    monkeypatch.setattr("whisprbar.flow.pipeline.detect_app_context", lambda: AppContext("x11"))
    monkeypatch.setattr("whisprbar.flow.pipeline.load_dictionary", lambda: [])
    monkeypatch.setattr("whisprbar.flow.pipeline.load_snippets", lambda: [])
    captured = {}

    def fake_rewrite_text(**kwargs):
        captured["profile"] = kwargs["profile"]
        captured["command"] = kwargs["command"]
        return RewriteResult(text="I have a problem with this sentence.", status="applied")

    monkeypatch.setattr("whisprbar.flow.pipeline.rewrite_text", fake_rewrite_text)

    output = process_flow_text(
        "i has a problem with this sentence correct my english",
        "en",
        {"flow_mode_enabled": True, "flow_command_mode_enabled": True, "flow_rewrite_enabled": True},
    )

    assert output.final_text == "I have a problem with this sentence."
    assert output.command == "correct_english"
    assert captured["command"] == "correct_english"
    assert captured["profile"].rewrite_mode == "correct_english"


@pytest.mark.unit
def test_process_flow_text_paste_only_command_does_not_trigger_rewrite(monkeypatch):
    monkeypatch.setattr("whisprbar.flow.pipeline.detect_app_context", lambda: AppContext("x11"))
    monkeypatch.setattr("whisprbar.flow.pipeline.load_dictionary", lambda: [])
    monkeypatch.setattr("whisprbar.flow.pipeline.load_snippets", lambda: [])

    def fail_rewrite_text(**kwargs):
        raise AssertionError("paste-only command should not call rewrite_text")

    monkeypatch.setattr("whisprbar.flow.pipeline.rewrite_text", fail_rewrite_text)

    output = process_flow_text(
        "bitte bestätigen drücke enter",
        "de",
        {
            "flow_mode_enabled": True,
            "flow_command_mode_enabled": True,
            "flow_rewrite_enabled": True,
            "flow_profiles": {"default": {"rewrite_mode": "none"}},
        },
    )

    assert output.final_text == "Bitte bestätigen"
    assert output.command == "press_enter"
    assert output.paste_policy is not None
    assert output.paste_policy.press_enter_after_paste is True
    assert output.rewrite_status == "not_requested"
