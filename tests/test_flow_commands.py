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
def test_detect_german_longer_command_suffix():
    detection = detect_command("das braucht mehr details mach das länger", "de", enabled=True)

    assert detection.text == "das braucht mehr details"
    assert detection.command_id == "longer"
    assert detection.rewrite_mode == "longer"


@pytest.mark.unit
def test_detect_english_longer_command_suffix():
    detection = detect_command("add a bit of context make this more detailed", "en", enabled=True)

    assert detection.text == "add a bit of context"
    assert detection.command_id == "longer"
    assert detection.rewrite_mode == "longer"


@pytest.mark.unit
def test_detect_german_correct_english_command_suffix():
    detection = detect_command("i has a problem with this sentence korrigiere mein englisch", "de", enabled=True)

    assert detection.text == "i has a problem with this sentence"
    assert detection.command_id == "correct_english"
    assert detection.rewrite_mode == "correct_english"


@pytest.mark.unit
def test_detect_english_correct_my_english_command_suffix():
    detection = detect_command("i has a problem with this sentence correct my english", "en", enabled=True)

    assert detection.text == "i has a problem with this sentence"
    assert detection.command_id == "correct_english"
    assert detection.rewrite_mode == "correct_english"


@pytest.mark.unit
def test_detect_german_humanize_command_suffix():
    detection = detect_command(
        "dieser abschnitt klingt noch sehr nach ki mach das menschlicher",
        "de",
        enabled=True,
    )

    assert detection.text == "dieser abschnitt klingt noch sehr nach ki"
    assert detection.command_id == "humanize"
    assert detection.rewrite_mode == "humanize"


@pytest.mark.unit
def test_detect_english_humanize_command_suffix():
    detection = detect_command(
        "this paragraph sounds like a generic assistant response humanize this",
        "en",
        enabled=True,
    )

    assert detection.text == "this paragraph sounds like a generic assistant response"
    assert detection.command_id == "humanize"
    assert detection.rewrite_mode == "humanize"


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


@pytest.mark.unit
def test_german_next_line_command_alias_appends_newline():
    detection = detect_command("hallo nächste zeile", "de", enabled=True)

    assert detection.text == "hallo"
    assert detection.command_id == "new_line"
    assert detection.paste_policy is not None
    assert detection.paste_policy.add_newline is True
