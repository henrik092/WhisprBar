"""Tests for safe Flow dictionary learning from transcript history."""

import json
import sqlite3

import pytest

from whisprbar.flow.learning import (
    DictionaryCandidate,
    TranscriptSample,
    apply_safe_dictionary_candidates,
    run_dictionary_learning,
    save_dictionary_candidates,
    suggest_dictionary_candidates,
)
from whisprbar.flow.models import DictionaryEntry


@pytest.mark.unit
def test_suggest_dictionary_candidates_from_repeated_raw_final_replacements():
    samples = [
        TranscriptSample(
            raw_text="ich nutze Whisper Bar jeden Tag",
            text="ich nutze WhisprBar jeden Tag",
        ),
        TranscriptSample(
            raw_text="Whisper Bar ist offen",
            text="WhisprBar ist offen",
        ),
    ]

    candidates = suggest_dictionary_candidates(samples, min_count=2)

    assert [(c.spoken, c.written, c.count) for c in candidates] == [
        ("Whisper Bar", "WhisprBar", 2)
    ]
    assert candidates[0].confidence >= 0.9
    assert candidates[0].auto_apply_eligible is True
    assert len(candidates[0].examples) == 2


@pytest.mark.unit
def test_suggest_dictionary_candidates_skips_existing_dictionary_entries():
    samples = [
        TranscriptSample(raw_text="Whisper Bar", text="WhisprBar"),
        TranscriptSample(raw_text="whisper bar", text="WhisprBar"),
    ]
    existing = [DictionaryEntry(spoken="Whisper Bar", written="WhisprBar")]

    candidates = suggest_dictionary_candidates(samples, existing_entries=existing, min_count=2)

    assert candidates == []


@pytest.mark.unit
def test_suggest_dictionary_candidates_ignores_punctuation_only_cleanup():
    samples = [
        TranscriptSample(raw_text="das geht nicht.", text="das geht nicht"),
        TranscriptSample(raw_text="das geht nicht.", text="das geht nicht"),
    ]

    candidates = suggest_dictionary_candidates(samples, min_count=2)

    assert candidates == []


@pytest.mark.unit
def test_save_dictionary_candidates_writes_reviewable_json(tmp_path):
    path = tmp_path / "dictionary_candidates.json"
    candidate = DictionaryCandidate(
        spoken="Whisper Bar",
        written="WhisprBar",
        count=3,
        confidence=0.96,
        reason="raw_final_replacement",
        examples=("raw → final",),
        auto_apply_eligible=True,
    )

    save_dictionary_candidates([candidate], path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload[0]["spoken"] == "Whisper Bar"
    assert payload[0]["written"] == "WhisprBar"
    assert payload[0]["auto_apply_eligible"] is True
    assert payload[0]["examples"] == ["raw → final"]


@pytest.mark.unit
def test_apply_safe_dictionary_candidates_only_merges_safe_terms(tmp_path):
    dictionary_path = tmp_path / "dictionary.json"
    dictionary_path.write_text("[]\n", encoding="utf-8")
    candidates = [
        DictionaryCandidate(
            spoken="Whisper Bar",
            written="WhisprBar",
            count=3,
            confidence=0.96,
            reason="raw_final_replacement",
            examples=(),
            auto_apply_eligible=True,
        ),
        DictionaryCandidate(
            spoken="mach das bitte",
            written="Mach das bitte",
            count=10,
            confidence=0.99,
            reason="raw_final_replacement",
            examples=(),
            auto_apply_eligible=True,
        ),
    ]

    applied = apply_safe_dictionary_candidates(candidates, dictionary_path=dictionary_path)

    assert applied == [DictionaryEntry(spoken="Whisper Bar", written="WhisprBar")]
    assert json.loads(dictionary_path.read_text(encoding="utf-8")) == [
        {"spoken": "Whisper Bar", "written": "WhisprBar"}
    ]


@pytest.mark.unit
def test_run_dictionary_learning_writes_candidates_and_report_without_mutating_dictionary(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    dictionary_path = tmp_path / "dictionary.json"
    candidates_path = tmp_path / "dictionary_candidates.json"
    report_path = tmp_path / "learning_report.md"
    dictionary_path.write_text("[]\n", encoding="utf-8")

    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE transcripts (
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            language TEXT,
            text TEXT,
            raw_text TEXT,
            backend TEXT,
            profile_id TEXT,
            metadata_json TEXT
        )
        """
    )
    rows = [
        ("2026-06-23T10:00:00+00:00", "de", "ich nutze WhisprBar", "ich nutze Whisper Bar", "faster_whisper", "default", "{}"),
        ("2026-06-23T10:01:00+00:00", "de", "WhisprBar ist schnell", "Whisper Bar ist schnell", "faster_whisper", "default", "{}"),
    ]
    connection.executemany(
        "INSERT INTO transcripts (created_at, language, text, raw_text, backend, profile_id, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    connection.close()

    result = run_dictionary_learning(
        database_path=database_path,
        dictionary_path=dictionary_path,
        candidates_path=candidates_path,
        report_path=report_path,
        min_count=2,
        apply_safe=False,
    )

    assert result["sample_count"] == 2
    assert result["candidate_count"] == 1
    assert result["applied_count"] == 0
    assert json.loads(dictionary_path.read_text(encoding="utf-8")) == []
    assert json.loads(candidates_path.read_text(encoding="utf-8"))[0]["written"] == "WhisprBar"
    assert "WhisprBar" in report_path.read_text(encoding="utf-8")
