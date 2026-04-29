"""Tests for Flow Mode dictionary corrections."""

import json

import pytest

from whisprbar.flow.dictionary import apply_dictionary, load_dictionary
from whisprbar.flow.models import DictionaryEntry


@pytest.mark.unit
def test_load_dictionary_missing_file_returns_empty(tmp_path):
    assert load_dictionary(tmp_path / "missing.json") == []


@pytest.mark.unit
def test_load_dictionary_invalid_json_returns_empty(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text("{not json", encoding="utf-8")

    assert load_dictionary(path) == []


@pytest.mark.unit
def test_load_dictionary_reads_entries(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text(
        json.dumps([{"spoken": "whisper bar", "written": "WhisprBar"}]),
        encoding="utf-8",
    )

    assert load_dictionary(path) == [DictionaryEntry(spoken="whisper bar", written="WhisprBar")]


@pytest.mark.unit
def test_apply_dictionary_replaces_case_insensitive_whole_phrase():
    text, hits = apply_dictionary(
        "ich nutze Whisper Bar täglich",
        [DictionaryEntry(spoken="whisper bar", written="WhisprBar")],
    )

    assert text == "ich nutze WhisprBar täglich"
    assert hits == ("whisper bar",)


@pytest.mark.unit
def test_apply_dictionary_longer_phrases_win():
    text, hits = apply_dictionary(
        "wispr flow ist schnell",
        [
            DictionaryEntry(spoken="wispr", written="Wispr"),
            DictionaryEntry(spoken="wispr flow", written="Wispr Flow"),
        ],
    )

    assert text == "Wispr Flow ist schnell"
    assert hits == ("wispr flow",)
