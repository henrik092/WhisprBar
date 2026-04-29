"""Tests for deterministic Flow Mode formatting."""

import pytest

from whisprbar.flow.formatting import apply_backtrack, apply_smart_formatting
from whisprbar.flow.models import FlowProfile


@pytest.mark.unit
def test_apply_backtrack_removes_english_correction_fragment():
    text, hits = apply_backtrack("send it today scratch that send it tomorrow", "en", True)

    assert text == "send it tomorrow"
    assert hits == ("scratch that",)


@pytest.mark.unit
def test_apply_backtrack_removes_german_correction_fragment():
    text, hits = apply_backtrack("wir treffen uns heute streich das morgen", "de", True)

    assert text == "morgen"
    assert hits == ("streich das",)


@pytest.mark.unit
def test_apply_backtrack_disabled_leaves_text():
    text, hits = apply_backtrack("send it today scratch that tomorrow", "en", False)

    assert text == "send it today scratch that tomorrow"
    assert hits == ()


@pytest.mark.unit
def test_apply_smart_formatting_converts_punctuation_words():
    text, metadata = apply_smart_formatting(
        "hello comma world period",
        "en",
        FlowProfile("default", "Default"),
        {"flow_smart_formatting_enabled": True},
    )

    assert text == "hello, world."
    assert metadata["punctuation_words"] is True


@pytest.mark.unit
def test_apply_smart_formatting_converts_numbered_list_markers():
    text, metadata = apply_smart_formatting(
        "one apples two bananas",
        "en",
        FlowProfile("notes", "Notes", style="structured"),
        {"flow_smart_formatting_enabled": True},
    )

    assert text == "1. apples\n2. bananas"
    assert metadata["list_format"] == "numbered"


@pytest.mark.unit
def test_apply_smart_formatting_chat_removes_final_period():
    text, metadata = apply_smart_formatting(
        "see you soon.",
        "en",
        FlowProfile("chat", "Chat", style="casual"),
        {"flow_smart_formatting_enabled": True},
    )

    assert text == "see you soon"
    assert metadata["chat_period_trimmed"] is True


@pytest.mark.unit
def test_apply_smart_formatting_disabled_keeps_text():
    text, metadata = apply_smart_formatting(
        "hello comma world period",
        "en",
        FlowProfile("default", "Default"),
        {"flow_smart_formatting_enabled": False},
    )

    assert text == "hello comma world period"
    assert metadata == {}
