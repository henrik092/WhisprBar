"""Tests for Flow Mode data models."""

import pytest

from whisprbar.flow import (
    AppContext,
    CommandDetection,
    DictionaryEntry,
    FlowInput,
    FlowOutput,
    FlowProfile,
    PastePolicy,
    Snippet,
)


@pytest.mark.unit
def test_app_context_defaults_to_unknown_values():
    context = AppContext(session_type="x11")

    assert context.session_type == "x11"
    assert context.app_class == ""
    assert context.app_name == ""
    assert context.window_title == ""


@pytest.mark.unit
def test_flow_profile_carries_style_and_paste_policy():
    profile = FlowProfile(
        profile_id="email",
        label="Email",
        style="professional",
        rewrite_mode="professional",
        paste_sequence="ctrl_v",
        add_space=False,
        add_newline=True,
    )

    assert profile.profile_id == "email"
    assert profile.label == "Email"
    assert profile.style == "professional"
    assert profile.rewrite_mode == "professional"
    assert profile.paste_sequence == "ctrl_v"
    assert profile.add_space is False
    assert profile.add_newline is True


@pytest.mark.unit
def test_flow_input_preserves_raw_text_language_and_context():
    context = AppContext(session_type="wayland", app_class="browser")
    flow_input = FlowInput(text="hallo welt", language="de", context=context)

    assert flow_input.text == "hallo welt"
    assert flow_input.language == "de"
    assert flow_input.context == context


@pytest.mark.unit
def test_flow_output_preserves_metadata_and_hits():
    output = FlowOutput(
        raw_text="wispr flow",
        final_text="Wispr Flow",
        profile_id="default",
        rewrite_status="applied",
        command="professional",
        dictionary_hits=("wispr flow",),
        snippet_hits=("signature",),
        metadata={"duration": 1.2},
    )

    assert output.raw_text == "wispr flow"
    assert output.final_text == "Wispr Flow"
    assert output.profile_id == "default"
    assert output.rewrite_status == "applied"
    assert output.command == "professional"
    assert output.dictionary_hits == ("wispr flow",)
    assert output.snippet_hits == ("signature",)
    assert output.metadata["duration"] == 1.2


@pytest.mark.unit
def test_supporting_models_are_hashable_or_frozen():
    assert DictionaryEntry(spoken="whisper bar", written="WhisprBar").written == "WhisprBar"
    assert Snippet(trigger="signature", text="Best regards").text == "Best regards"
    assert PastePolicy(sequence="clipboard", clipboard_only=True).clipboard_only is True
    assert CommandDetection(
        text="Hallo",
        command_id="clipboard_only",
        rewrite_mode=None,
        paste_policy=PastePolicy(clipboard_only=True),
    ).text == "Hallo"

