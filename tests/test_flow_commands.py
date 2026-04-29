"""Tests for Flow Mode voice command detection."""

import pytest

from whisprbar.flow.commands import detect_command


@pytest.mark.unit
def test_detect_command_only_does_not_keep_literal_command():
    detection = detect_command("mach das professioneller", "de", enabled=True)

    assert detection.text == ""
    assert detection.command_id == "professional"
    assert detection.rewrite_mode == "professional"


@pytest.mark.unit
def test_detect_command_suffix_strips_command_and_sets_rewrite():
    detection = detect_command(
        "hallo team wir treffen uns morgen make this shorter",
        "en",
        enabled=True,
    )

    assert detection.text == "hallo team wir treffen uns morgen"
    assert detection.command_id == "shorter"
    assert detection.rewrite_mode == "shorter"


@pytest.mark.unit
def test_detect_german_command_suffix_with_punctuation():
    detection = detect_command("das ist viel zu lang, mach das kürzer.", "de", enabled=True)

    assert detection.text == "das ist viel zu lang"
    assert detection.command_id == "shorter"
    assert detection.rewrite_mode == "shorter"


@pytest.mark.unit
def test_detect_german_list_alias_from_misheard_phrase():
    detection = detect_command("eins äpfel zwei birnen als leiste.", "de", enabled=True)

    assert detection.text == "eins äpfel zwei birnen"
    assert detection.command_id == "list"
    assert detection.rewrite_mode == "list"


@pytest.mark.unit
def test_non_command_text_is_left_unchanged():
    detection = detect_command("this is normal text", "en", enabled=True)

    assert detection.text == "this is normal text"
    assert detection.command_id is None
    assert detection.rewrite_mode is None


@pytest.mark.unit
def test_commands_disabled_leaves_text_unchanged():
    detection = detect_command("clipboard only", "en", enabled=False)

    assert detection.text == "clipboard only"
    assert detection.command_id is None
    assert detection.paste_policy is None


@pytest.mark.unit
def test_clipboard_only_command_sets_paste_policy():
    detection = detect_command("nur in die zwischenablage", "de", enabled=True)

    assert detection.text == ""
    assert detection.command_id == "clipboard_only"
    assert detection.paste_policy is not None
    assert detection.paste_policy.clipboard_only is True


@pytest.mark.unit
def test_press_enter_only_matches_at_end():
    detection = detect_command("bitte bestätige drücke enter", "de", enabled=True)

    assert detection.text == "bitte bestätige"
    assert detection.command_id == "press_enter"
    assert detection.paste_policy is not None
    assert detection.paste_policy.press_enter_after_paste is True


@pytest.mark.unit
def test_new_line_command_appends_newline():
    detection = detect_command("new line", "en", enabled=True)

    assert detection.text == ""
    assert detection.command_id == "new_line"
    assert detection.paste_policy is not None
    assert detection.paste_policy.add_newline is True
