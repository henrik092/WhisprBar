"""Tests for durable transcript database storage."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from whisprbar.transcript_store import get_transcript_stats, save_transcript_record


def _transcript_rows(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = []
        for row in connection.execute("SELECT * FROM transcripts ORDER BY id"):
            payload = dict(row)
            payload["metadata"] = json.loads(payload["metadata_json"])
            rows.append(payload)
        return rows
    finally:
        connection.close()


@pytest.mark.unit
def test_save_transcript_record_creates_analysis_row(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"

    row_id = save_transcript_record(
        "Final text",
        1.25,
        2,
        metadata={
            "raw_text": "raw text",
            "profile_id": "email",
            "rewrite_status": "applied",
            "final_text": "Final text",
        },
        config={"language": "en", "transcription_backend": "openai"},
        database_path=database_path,
        created_at="2026-05-30T10:00:00+00:00",
    )

    assert row_id == 1
    rows = _transcript_rows(database_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["created_at"] == "2026-05-30T10:00:00+00:00"
    assert row["language"] == "en"
    assert row["text"] == "Final text"
    assert row["raw_text"] == "raw text"
    assert row["duration_seconds"] == 1.25
    assert row["word_count"] == 2
    assert row["backend"] == "openai"
    assert row["profile_id"] == "email"
    assert row["rewrite_status"] == "applied"
    assert row["schema_version"] == 1
    assert row["metadata"]["final_text"] == "Final text"


@pytest.mark.unit
def test_save_transcript_record_keeps_complete_metadata_json(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    metadata = {
        "raw_text": "roh",
        "profile_id": "default",
        "nested": {"source": "flow", "flags": ["a", "b"]},
    }

    save_transcript_record(
        "Fertiger Text",
        2.0,
        2,
        metadata=metadata,
        config={"language": "de", "transcription_backend": "deepgram"},
        database_path=database_path,
        created_at="2026-05-30T11:00:00+00:00",
    )

    row = _transcript_rows(database_path)[0]
    assert row["metadata"] == metadata
    assert row["backend"] == "deepgram"


@pytest.mark.unit
def test_save_transcript_record_respects_never_store_privacy(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"

    row_id = save_transcript_record(
        "Private text",
        1.0,
        2,
        config={"language": "en", "flow_history_storage": "never"},
        database_path=database_path,
    )

    assert row_id is None
    assert not database_path.exists()


@pytest.mark.unit
def test_save_transcript_record_prunes_auto_delete_rows(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    now = datetime.now(timezone.utc)

    save_transcript_record(
        "Old text",
        1.0,
        2,
        config={"language": "en", "flow_history_storage": "normal"},
        database_path=database_path,
        created_at=(now - timedelta(hours=2)).isoformat(),
    )
    save_transcript_record(
        "Fresh text",
        1.0,
        2,
        config={
            "language": "en",
            "flow_history_storage": "auto_delete",
            "flow_history_auto_delete_hours": 1,
        },
        database_path=database_path,
        created_at=now.isoformat(),
    )

    rows = _transcript_rows(database_path)
    assert [row["text"] for row in rows] == ["Fresh text"]


@pytest.mark.unit
def test_get_transcript_stats_counts_sources_and_date_range(tmp_path):
    database_path = tmp_path / "transcripts.sqlite3"
    save_transcript_record(
        "Live text",
        1.0,
        2,
        metadata={"raw_text": "Live text"},
        config={"language": "de", "transcription_backend": "deepgram"},
        database_path=database_path,
        created_at="2026-05-30T09:00:00+00:00",
    )
    save_transcript_record(
        "Imported text",
        2.0,
        2,
        metadata={"raw_text": "Imported text", "import_source": "copyq"},
        config={"language": "de"},
        database_path=database_path,
        created_at="2026-05-30T10:00:00+00:00",
    )

    stats = get_transcript_stats(database_path)

    assert stats["total"] == 2
    assert stats["live_sqlite_write"] == 1
    assert stats["copyq"] == 1
    assert stats["history_jsonl"] == 0
    assert stats["oldest_created_at"] == "2026-05-30T09:00:00+00:00"
    assert stats["newest_created_at"] == "2026-05-30T10:00:00+00:00"
    assert stats["database_path"] == str(database_path)
