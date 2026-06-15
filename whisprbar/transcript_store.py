"""Durable SQLite storage for completed dictation transcripts."""

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .config import DATA_DIR, HIST_FILE, cfg


DATABASE_PATH = DATA_DIR / "transcripts.sqlite3"
SCHEMA_VERSION = 1
CONTENT_METADATA_KEYS = {"raw_text", "final_text"}
CONFIRM_DELETE_PHRASE = "DELETE TRANSCRIPTS"


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _chmod_private(path: Path) -> None:
    try:
        if path.exists():
            path.chmod(0o600)
    except OSError:
        pass


def _chmod_private_dir(path: Path) -> None:
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _repair_sqlite_permissions(database_path: Path) -> None:
    _chmod_private_dir(database_path.parent)
    _chmod_private(database_path)
    _chmod_private(database_path.with_name(f"{database_path.name}-wal"))
    _chmod_private(database_path.with_name(f"{database_path.name}-shm"))


def _content_free_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in metadata.items()
        if str(key) not in CONTENT_METADATA_KEYS
    }


def ensure_database(database_path: Path = DATABASE_PATH) -> None:
    """Create the transcript analysis database schema if needed."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_private_dir(database_path.parent)
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
    _repair_sqlite_permissions(database_path)


def get_transcript_stats(database_path: Path = DATABASE_PATH) -> dict[str, Any]:
    """Return read-only transcript database stats for settings and diagnostics."""
    database_path = Path(database_path)
    stats: dict[str, Any] = {
        "database_path": str(database_path),
        "total": 0,
        "live_sqlite_write": 0,
        "history_jsonl": 0,
        "copyq": 0,
        "word_count": 0,
        "duration_seconds": 0.0,
        "words_per_minute": 0.0,
        "raw_final_changed": 0,
        "dictionary_hit_rows": 0,
        "snippet_hit_rows": 0,
        "languages": {},
        "backends": {},
        "profiles": {},
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
            aggregate = connection.execute(
                """
                SELECT
                    COALESCE(SUM(word_count), 0),
                    COALESCE(SUM(duration_seconds), 0),
                    SUM(CASE WHEN raw_text IS NOT NULL AND raw_text != text THEN 1 ELSE 0 END)
                FROM transcripts
                """
            ).fetchone()
            stats["word_count"] = int(aggregate[0] or 0)
            stats["duration_seconds"] = round(float(aggregate[1] or 0.0), 3)
            stats["raw_final_changed"] = int(aggregate[2] or 0)
            if stats["duration_seconds"]:
                stats["words_per_minute"] = round(
                    int(stats["word_count"]) / (float(stats["duration_seconds"]) / 60.0),
                    1,
                )

            for field, key in (
                ("language", "languages"),
                ("backend", "backends"),
                ("profile_id", "profiles"),
            ):
                counts: dict[str, int] = {}
                for value, count in connection.execute(
                    f"SELECT COALESCE(NULLIF({field}, ''), 'unknown'), COUNT(*) "
                    "FROM transcripts GROUP BY COALESCE(NULLIF(" + field + ", ''), 'unknown')"
                ):
                    counts[str(value)] = int(count)
                stats[key] = counts

            for (metadata_json,) in connection.execute("SELECT metadata_json FROM transcripts"):
                try:
                    metadata = json.loads(metadata_json or "{}")
                except json.JSONDecodeError:
                    metadata = {}
                if not isinstance(metadata, dict):
                    metadata = {}
                source = metadata.get("import_source") or "live_sqlite_write"
                if source not in {"live_sqlite_write", "history_jsonl", "copyq"}:
                    source = "live_sqlite_write"
                stats[source] += 1
                if metadata.get("dictionary_hits"):
                    stats["dictionary_hit_rows"] += 1
                if metadata.get("snippet_hits"):
                    stats["snippet_hit_rows"] += 1
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
    raw_text = metadata_payload.get("raw_text")
    stored_metadata = _content_free_metadata(metadata_payload)
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
                    raw_text,
                    round(float(duration), 3),
                    int(word_count),
                    config_data.get("transcription_backend"),
                    metadata_payload.get("profile_id"),
                    metadata_payload.get("rewrite_status"),
                    json.dumps(stored_metadata, ensure_ascii=False, sort_keys=True),
                    SCHEMA_VERSION,
                ),
            )
            _repair_sqlite_permissions(database_path)
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


def _copyq_row_ids(connection: sqlite3.Connection) -> list[int]:
    row_ids: list[int] = []
    for row_id, metadata_json in connection.execute("SELECT id, metadata_json FROM transcripts"):
        try:
            metadata = json.loads(metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if isinstance(metadata, dict) and metadata.get("import_source") == "copyq":
            row_ids.append(int(row_id))
    return row_ids


def _history_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def preview_transcript_cleanup(
    *,
    database_path: Path = DATABASE_PATH,
    history_path: Path = HIST_FILE,
    scope: str,
) -> dict[str, Any]:
    """Return body-free counts for a transcript cleanup action."""
    database_path = Path(database_path)
    history_path = Path(history_path)
    sqlite_rows = 0
    history_rows = 0
    if database_path.exists() and scope in {"sqlite_all", "copyq"}:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        try:
            if scope == "sqlite_all":
                sqlite_rows = int(connection.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0])
            elif scope == "copyq":
                sqlite_rows = len(_copyq_row_ids(connection))
        finally:
            connection.close()
    if scope == "history_all":
        history_rows = len(_history_rows(history_path))
    return {"scope": scope, "sqlite_rows": sqlite_rows, "history_rows": history_rows}


def cleanup_transcript_data(
    *,
    database_path: Path = DATABASE_PATH,
    history_path: Path = HIST_FILE,
    scope: str,
    confirm_phrase: str,
) -> dict[str, Any]:
    """Delete selected local transcript data only after explicit confirmation."""
    result: dict[str, Any] = {
        "ok": False,
        "scope": scope,
        "deleted_sqlite_rows": 0,
        "deleted_history_rows": 0,
        "error": None,
    }
    if confirm_phrase != CONFIRM_DELETE_PHRASE:
        result["error"] = "confirmation required"
        return result

    database_path = Path(database_path)
    history_path = Path(history_path)
    try:
        if scope in {"sqlite_all", "copyq"} and database_path.exists():
            ensure_database(database_path)
            with _connect(database_path) as connection:
                if scope == "sqlite_all":
                    before = int(connection.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0])
                    connection.execute("DELETE FROM transcripts")
                    result["deleted_sqlite_rows"] = before
                else:
                    row_ids = _copyq_row_ids(connection)
                    if row_ids:
                        placeholders = ",".join("?" for _ in row_ids)
                        connection.execute(
                            f"DELETE FROM transcripts WHERE id IN ({placeholders})",
                            row_ids,
                        )
                    result["deleted_sqlite_rows"] = len(row_ids)
            _repair_sqlite_permissions(database_path)
        elif scope == "history_all":
            rows = _history_rows(history_path)
            history_path.parent.mkdir(parents=True, exist_ok=True)
            _chmod_private_dir(history_path.parent)
            history_path.write_text("", encoding="utf-8")
            _chmod_private(history_path)
            result["deleted_history_rows"] = len(rows)
        else:
            result["error"] = f"unknown cleanup scope: {scope}"
            return result
    except Exception as exc:
        result["error"] = str(exc)
        return result
    result["ok"] = True
    return result
