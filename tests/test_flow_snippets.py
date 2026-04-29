"""Tests for Flow Mode snippets."""

import json

import pytest

from whisprbar.flow.models import Snippet
from whisprbar.flow.snippets import apply_snippets, load_snippets, save_snippets, validate_snippets


@pytest.mark.unit
def test_load_snippets_missing_file_returns_empty(tmp_path):
    assert load_snippets(tmp_path / "missing.json") == []


@pytest.mark.unit
def test_load_snippets_invalid_json_returns_empty(tmp_path):
    path = tmp_path / "snippets.json"
    path.write_text("{broken", encoding="utf-8")

    assert load_snippets(path) == []


@pytest.mark.unit
def test_load_snippets_reads_entries(tmp_path):
    path = tmp_path / "snippets.json"
    path.write_text(
        json.dumps([{"trigger": "my signature", "text": "Best regards"}]),
        encoding="utf-8",
    )

    assert load_snippets(path) == [Snippet(trigger="my signature", text="Best regards")]


@pytest.mark.unit
def test_save_snippets_persists_non_empty_entries(tmp_path):
    path = tmp_path / "snippets.json"

    save_snippets(
        [
            Snippet(trigger=" meeting link ", text=" https://example.test/meeting "),
            Snippet(trigger="", text="ignored"),
            Snippet(trigger="ignored", text=""),
        ],
        path,
    )

    assert json.loads(path.read_text(encoding="utf-8")) == [
        {"trigger": "meeting link", "text": "https://example.test/meeting"}
    ]
    assert load_snippets(path) == [
        Snippet(trigger="meeting link", text="https://example.test/meeting")
    ]


@pytest.mark.unit
def test_apply_snippets_replaces_trigger_in_sentence():
    text, hits = apply_snippets(
        "please add my signature now",
        [Snippet(trigger="my signature", text="Best regards")],
    )

    assert text == "please add Best regards now"
    assert hits == ("my signature",)


@pytest.mark.unit
def test_apply_snippets_handles_trigger_only_with_punctuation():
    text, hits = apply_snippets(
        "meeting link.",
        [Snippet(trigger="meeting link", text="https://example.test/meeting")],
    )

    assert text == "https://example.test/meeting."
    assert hits == ("meeting link",)


@pytest.mark.unit
def test_validate_snippets_rejects_duplicate_triggers():
    with pytest.raises(ValueError, match="duplicate snippet trigger"):
        validate_snippets([
            Snippet(trigger="Signature", text="A"),
            Snippet(trigger="signature", text="B"),
        ])
