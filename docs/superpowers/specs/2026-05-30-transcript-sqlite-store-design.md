# Transcript SQLite Store Design

Status: Implemented before local documentation integration on 2026-06-15. Kept as historical design context.

## Goal

WhisprBar must persist every successful dictation as structured data that is easy to analyze later with scripts and AI models.

## Scope

The feature stores text transcripts and metadata only. It does not store raw audio files. Failed, empty, too-short, or no-speech recordings remain outside the database because they do not produce a successful transcript.

## Architecture

Add a small storage module, `whisprbar/transcript_store.py`, backed by SQLite in `~/.local/share/whisprbar/transcripts.sqlite3`. The current JSONL history remains in place for existing history UI behavior and short recent-history workflows. SQLite becomes the durable analysis store.

`whisprbar/main.py` already creates the complete dictation record in `dispatch_transcript_text()`: raw text, final text, duration, word count, language, Flow metadata, and paste policy context. After `write_history()` succeeds, the same data will be written to the SQLite store through a focused helper.

## Data Model

The database has one `transcripts` table:

- `id`: integer primary key
- `created_at`: UTC ISO timestamp
- `language`: config language at write time
- `text`: final text after Flow processing
- `raw_text`: backend transcript before Flow processing when available
- `duration_seconds`: post-VAD audio duration
- `word_count`: final text word count
- `backend`: selected transcription backend
- `profile_id`: Flow profile when available
- `rewrite_status`: Flow rewrite result when available
- `metadata_json`: complete metadata JSON for future model analysis
- `schema_version`: integer schema marker

Indexes on `created_at`, `language`, and `profile_id` keep later analysis queries simple.

## Privacy

The existing privacy setting `flow_history_storage = "never"` disables this database write too. This keeps "never store" meaning literal across both JSONL and SQLite storage.

## Error Handling

Database failures are logged as warnings and must not break paste, clipboard, overlay, or tray behavior. The user should still get the transcription result even if the analysis database is unavailable.

## Testing

Tests cover database creation, inserted structured fields, JSON metadata preservation, privacy opt-out behavior, and the main dispatch path calling the SQLite persistence helper with the final transcript.
