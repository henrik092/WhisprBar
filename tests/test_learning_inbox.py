"""Tests for local Flow Learning Inbox candidate and state handling."""

import json

import pytest

from whisprbar.flow.learning_inbox import (
    LEARNING_STATE_VERSION,
    LearningCandidate,
    apply_learning_candidate_status,
    get_learning_inbox_summary,
    load_learning_state,
    set_learning_candidate_status,
)
from whisprbar.flow.dictionary import load_dictionary
from whisprbar.flow.models import Snippet
from whisprbar.transcript_store import save_transcript_record


@pytest.mark.unit
def test_learning_inbox_suggests_repeated_short_dictionary_candidates(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    state_path = tmp_path / "learning_inbox.json"
    dictionary_path = tmp_path / "dictionary.json"
    private_body = "github bitte im privaten kundensatz behalten"

    for created_at in ("2026-06-15T10:00:00+00:00", "2026-06-15T10:01:00+00:00"):
        save_transcript_record(
            "GitHub bitte im privaten Kundensatz behalten",
            2.0,
            6,
            metadata={"raw_text": private_body, "profile_id": "editor"},
            config={"language": "de", "transcription_backend": "deepgram"},
            database_path=database_path,
            created_at=created_at,
        )
    save_transcript_record(
        "OpenAI einmalig",
        1.0,
        2,
        metadata={"raw_text": "open ai einmalig", "profile_id": "editor"},
        config={"language": "de", "transcription_backend": "deepgram"},
        database_path=database_path,
        created_at="2026-06-15T10:02:00+00:00",
    )

    summary = get_learning_inbox_summary(
        database_path=database_path,
        state_path=state_path,
        dictionary_path=dictionary_path,
        min_evidence=2,
    )

    assert summary["pending_count"] == 1
    assert summary["total_candidates"] == 1
    assert summary["state_path"] == str(state_path)
    candidate = summary["candidates"][0]
    assert candidate["kind"] == "dictionary"
    assert candidate["spoken"] == "github"
    assert candidate["written"] == "GitHub"
    assert candidate["evidence_count"] == 2
    assert candidate["status"] == "pending"
    assert private_body not in json.dumps(summary, ensure_ascii=False)
    assert "open ai" not in json.dumps(summary, ensure_ascii=False)


@pytest.mark.unit
def test_learning_inbox_state_filters_dismissed_and_never_suggestions(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    state_path = tmp_path / "learning_inbox.json"
    dictionary_path = tmp_path / "dictionary.json"

    for created_at in ("2026-06-15T10:00:00+00:00", "2026-06-15T10:01:00+00:00"):
        save_transcript_record(
            "Codex",
            1.0,
            1,
            metadata={"raw_text": "codex"},
            config={"language": "de", "transcription_backend": "deepgram"},
            database_path=database_path,
            created_at=created_at,
        )

    summary = get_learning_inbox_summary(
        database_path=database_path,
        state_path=state_path,
        dictionary_path=dictionary_path,
        min_evidence=2,
    )
    candidate_id = summary["candidates"][0]["id"]

    set_learning_candidate_status(candidate_id, "never", state_path=state_path)
    updated = get_learning_inbox_summary(
        database_path=database_path,
        state_path=state_path,
        dictionary_path=dictionary_path,
        min_evidence=2,
    )

    assert updated["pending_count"] == 0
    assert updated["never_count"] == 1
    assert updated["candidates"] == []
    assert load_learning_state(state_path)["items"][candidate_id]["status"] == "never"
    assert state_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.unit
def test_learning_candidate_id_is_stable_and_body_free():
    first = LearningCandidate(
        kind="dictionary",
        spoken="github",
        written="GitHub",
        evidence_count=3,
    )
    second = LearningCandidate(
        kind="dictionary",
        spoken="github",
        written="GitHub",
        evidence_count=9,
    )

    assert first.id == second.id
    assert first.to_public_dict() == {
        "id": first.id,
        "kind": "dictionary",
        "spoken": "github",
        "written": "GitHub",
        "evidence_count": 3,
        "status": "pending",
    }
    assert LEARNING_STATE_VERSION == 1


@pytest.mark.unit
def test_approve_learning_candidate_adds_dictionary_entry_and_records_state(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    state_path = tmp_path / "learning_inbox.json"
    dictionary_path = tmp_path / "dictionary.json"

    for created_at in ("2026-06-15T10:00:00+00:00", "2026-06-15T10:01:00+00:00"):
        save_transcript_record(
            "GitHub",
            1.0,
            1,
            metadata={"raw_text": "github"},
            config={"language": "de", "transcription_backend": "deepgram"},
            database_path=database_path,
            created_at=created_at,
        )

    summary = get_learning_inbox_summary(
        database_path=database_path,
        state_path=state_path,
        min_evidence=2,
        dictionary_path=dictionary_path,
    )
    candidate_id = summary["candidates"][0]["id"]

    apply_learning_candidate_status(
        candidate_id,
        "approved",
        database_path=database_path,
        state_path=state_path,
        dictionary_path=dictionary_path,
        min_evidence=2,
    )

    entries = load_dictionary(dictionary_path)
    assert [(entry.spoken, entry.written) for entry in entries] == [("github", "GitHub")]
    state = load_learning_state(state_path)
    assert state["items"][candidate_id]["status"] == "approved"


@pytest.mark.unit
def test_learning_inbox_suggests_repeated_output_without_transcript_body(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    state_path = tmp_path / "learning_inbox.json"
    repeated_private_text = "Bitte diese private Antwort nicht im Vorschlag anzeigen"

    for created_at in ("2026-06-15T10:00:00+00:00", "2026-06-15T10:01:00+00:00"):
        save_transcript_record(
            repeated_private_text,
            1.0,
            8,
            metadata={"raw_text": repeated_private_text, "profile_id": "chat"},
            config={"language": "de", "transcription_backend": "deepgram"},
            database_path=database_path,
            created_at=created_at,
        )

    summary = get_learning_inbox_summary(
        database_path=database_path,
        state_path=state_path,
        existing_snippets=[],
        min_evidence=2,
    )

    candidates = [item for item in summary["candidates"] if item["kind"] == "snippet_hint"]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["evidence_count"] == 2
    assert "Repeated chat output" in candidate["written"]
    assert repeated_private_text not in json.dumps(summary, ensure_ascii=False)


@pytest.mark.unit
def test_learning_inbox_ignores_existing_snippet_text_and_terminal_outputs(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    state_path = tmp_path / "learning_inbox.json"
    repeated_text = "Danke fuer die schnelle Rueckmeldung"

    for profile in ("chat", "chat", "terminal", "terminal"):
        save_transcript_record(
            repeated_text,
            1.0,
            5,
            metadata={"raw_text": repeated_text, "profile_id": profile},
            config={"language": "de", "transcription_backend": "deepgram"},
            database_path=database_path,
        )

    summary = get_learning_inbox_summary(
        database_path=database_path,
        state_path=state_path,
        existing_snippets=[Snippet(trigger="thanks", text=repeated_text)],
        min_evidence=2,
    )

    assert [item for item in summary["candidates"] if item["kind"] == "snippet_hint"] == []


@pytest.mark.unit
def test_learning_state_write_is_atomic_when_replace_fails(tmp_path, monkeypatch):
    state_path = tmp_path / "learning_inbox.json"
    set_learning_candidate_status("old", "never", state_path=state_path)
    original = state_path.read_text(encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr("whisprbar.flow.learning_inbox.os.replace", fail_replace)

    with pytest.raises(OSError):
        set_learning_candidate_status("new", "dismissed", state_path=state_path)

    assert state_path.read_text(encoding="utf-8") == original
