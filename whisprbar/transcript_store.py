"""Durable SQLite storage for completed dictation transcripts."""

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .config import DATA_DIR, cfg


DATABASE_PATH = DATA_DIR / "transcripts.sqlite3"
SCHEMA_VERSION = 1


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def ensure_database(database_path: Path = DATABASE_PATH) -> None:
    """Create the transcript analysis database schema if needed."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                language TEXT,
                text TEXT NOT NULL,
                raw_text TEXT,
                duration_seconds REAL,
                word_count INTEGER,
                backend TEXT,
                profile_id TEXT,
                rewrite_status TEXT,
                metadata_json TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcripts_created_at "
            "ON transcripts(created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcripts_language "
            "ON transcripts(language)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcripts_profile_id "
            "ON transcripts(profile_id)"
        )


def get_transcript_stats(database_path: Path = DATABASE_PATH) -> dict[str, Any]:
    """Return read-only transcript database stats for settings and diagnostics."""
    database_path = Path(database_path)
    stats: dict[str, Any] = {
        "database_path": str(database_path),
        "total": 0,
        "live_sqlite_write": 0,
        "history_jsonl": 0,
        "copyq": 0,
        "oldest_created_at": None,
        "newest_created_at": None,
        "error": None,
    }
    if not database_path.exists():
        return stats

    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        try:
            stats["total"] = int(
                connection.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
            )
            created_range = connection.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM transcripts"
            ).fetchone()
            stats["oldest_created_at"] = created_range[0]
            stats["newest_created_at"] = created_range[1]

            for (metadata_json,) in connection.execute("SELECT metadata_json FROM transcripts"):
                try:
                    metadata = json.loads(metadata_json or "{}")
                except json.JSONDecodeError:
                    metadata = {}
                source = metadata.get("import_source") or "live_sqlite_write"
                if source not in {"live_sqlite_write", "history_jsonl", "copyq"}:
                    source = "live_sqlite_write"
                stats[source] += 1
        finally:
            connection.close()
    except Exception as exc:
        stats["error"] = str(exc)
    return stats


def save_transcript_record(
    transcript: str,
    duration: float,
    word_count: int,
    metadata: Optional[Mapping[str, Any]] = None,
    config: Optional[Mapping[str, Any]] = None,
    database_path: Path = DATABASE_PATH,
    created_at: Optional[str] = None,
) -> Optional[int]:
    """Persist a completed transcript for later analysis.

    Returns the inserted row id. Returns None when storage is disabled or a
    database failure occurs; persistence must not interrupt dictation output.
    """
    config_data = config if config is not None else cfg
    if config_data.get("flow_history_storage") == "never":
        return None

    metadata_payload = dict(metadata or {})
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    database_path = Path(database_path)

    try:
        ensure_database(database_path)
        with _connect(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO transcripts (
                    created_at,
                    language,
                    text,
                    raw_text,
                    duration_seconds,
                    word_count,
                    backend,
                    profile_id,
                    rewrite_status,
                    metadata_json,
                    schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    config_data.get("language"),
                    transcript,
                    metadata_payload.get("raw_text"),
                    round(float(duration), 3),
                    int(word_count),
                    config_data.get("transcription_backend"),
                    metadata_payload.get("profile_id"),
                    metadata_payload.get("rewrite_status"),
                    json.dumps(metadata_payload, ensure_ascii=False, sort_keys=True),
                    SCHEMA_VERSION,
                ),
            )
            if config_data.get("flow_history_storage") == "auto_delete":
                try:
                    retention_hours = int(config_data.get("flow_history_auto_delete_hours", 24))
                except (TypeError, ValueError):
                    retention_hours = 24
                cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, retention_hours))
                connection.execute(
                    "DELETE FROM transcripts WHERE created_at < ?",
                    (cutoff.isoformat(),),
                )
            return int(cursor.lastrowid)
    except Exception as exc:
        print(f"[WARN] Failed to write transcript database: {exc}", file=sys.stderr)
        return None
