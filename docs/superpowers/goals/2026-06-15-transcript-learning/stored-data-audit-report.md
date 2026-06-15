# Stored Data Audit: WhisprBar Transcript History

Date: 2026-06-15

Scope:

- `~/.local/share/whisprbar/history.jsonl`
- `~/.local/share/whisprbar/transcripts.sqlite3`

Privacy note: this report contains aggregate metrics only. It does not include transcript bodies. Duplicate examples are represented only by length/count/hash shape.

## Executive Summary

- JSONL history is valid and complete for its current 42 entries, with range 2026-06-14 13:08:43 UTC to 2026-06-15 16:20:51 UTC.
- SQLite contains 434 transcript rows, with range 2026-05-27 14:30:09 UTC to 2026-06-15 16:20:51 UTC.
- SQLite stores both final text and raw text for every row. `text` is always the final text; `raw_text` differs in 56 rows, mostly explained by local formatting metadata such as chat-period trimming and punctuation-word replacement.
- The current JSONL entries are all represented in SQLite by transcript text, but timestamps do not match exactly because JSONL and SQLite writes happen separately.
- The durable database has three source cohorts: 287 live SQLite writes, 34 older JSONL imports, and 113 CopyQ imports.
- Two actionable product/privacy issues stand out:
  - JSONL history has 42 entries despite `write_history()` documenting a 30-entry cap. Cleanup depends on an in-memory every-10-writes counter, so short sessions can leave the file above the cap.
  - Transcript files and database backups are group/world-readable (`history.jsonl` mode `664`, SQLite and backups mode `644`) even though they contain private dictation content.

## File Inventory

| Path | Size | Mode | Observation |
| --- | ---: | --- | --- |
| `~/.local/share/whisprbar/history.jsonl` | 29,716 bytes | `664` | Plaintext JSONL transcript history; group-writable and world-readable. |
| `~/.local/share/whisprbar/transcripts.sqlite3` | 524,288 bytes | `644` | Durable SQLite transcript database; world-readable. |
| `~/.local/share/whisprbar/transcripts.sqlite3.bak-20260530-104631` | 20,480 bytes | `644` | Backup copy; likely contains private transcript data. |
| `~/.local/share/whisprbar/transcripts.sqlite3.bak-copyq-20260530-105029` | 20,480 bytes | `644` | Backup copy; likely contains private transcript data. |

SQLite integrity check returned `ok`. The database uses WAL journal mode; no live `-wal` or `-shm` file was present during the audit.

## JSONL History

### Counts and Date Range

- Lines: 42
- Valid JSON entries: 42
- Invalid JSON entries: 0
- Blank lines: 0
- Date range: 2026-06-14 13:08:43 UTC to 2026-06-15 16:20:51 UTC

### Schema and Completeness

All 42 entries have non-empty values for:

- `timestamp`
- `language`
- `text`
- `duration_seconds`
- `word_count`
- `metadata`

Metadata completeness is strong. All 42 entries include:

- `context`
- `dictionary_hits`
- `final_text`
- `profile_id`
- `profile_style`
- `raw_text`
- `rewrite_status`
- `snippet_hits`

Additional metadata:

- `chat_period_trimmed`: 4 entries

### Distributions

Language:

- `de`: 42

Profile:

- `editor`: 29
- `terminal`: 6
- `chat`: 5
- `default`: 2

Rewrite status:

- `not_requested`: 42

This is expected with the current profile overrides: `default`, `chat`, `email`, and `notes` are configured with `rewrite_mode: none`, and `editor`/`terminal` are also non-rewrite profiles.

### Duration and Size

Duration seconds:

- Min: 1.856
- Median: 6.28
- Mean: 9.376
- Max: 33.63
- Zero or negative durations: 0

Final text size:

- Character length: min 14, median 69.5, mean 95.6, max 387
- Word count: min 2, median 11.5, mean 16.0, max 59
- Stored `word_count` mismatches: 0

### Raw vs Final Availability

- `metadata.raw_text` present: 42
- `metadata.final_text` present: 42
- `metadata.final_text` differs from top-level `text`: 0
- `metadata.raw_text` differs from top-level `text`: 4

Interpretation: JSONL retains both raw and final text. The top-level `text` is final output. The 4 raw/final differences are explained by Flow/local formatting metadata.

### Duplicate and Noise Signals

- Exact duplicate final texts: 0 groups
- Normalized duplicate final texts: 0 groups
- Empty transcript entries: 0
- Text length <= 3 characters: 0
- One-word entries: 0

No JSONL-level duplicate/noise issue was found.

## SQLite Transcript Store

### Schema

Table: `transcripts`

Columns:

- `id INTEGER PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `language TEXT`
- `text TEXT NOT NULL`
- `raw_text TEXT`
- `duration_seconds REAL`
- `word_count INTEGER`
- `backend TEXT`
- `profile_id TEXT`
- `rewrite_status TEXT`
- `metadata_json TEXT NOT NULL`
- `schema_version INTEGER NOT NULL`

Indexes:

- `idx_transcripts_created_at`
- `idx_transcripts_language`
- `idx_transcripts_profile_id`

Schema version:

- `1`: 434 rows

### Counts and Date Range

- Rows: 434
- ID range: 1 to 434
- Date range: 2026-05-27 14:30:09 UTC to 2026-06-15 16:20:51 UTC
- Bad `created_at` values: 0
- Metadata JSON parse failures: 0
- Metadata JSON non-dict payloads: 0

### Source Cohorts

From `metadata_json.import_source`:

| Source | Rows | Date range | Notes |
| --- | ---: | --- | --- |
| `live_sqlite_write` | 287 | 2026-05-30 08:42:34 UTC to 2026-06-15 16:20:51 UTC | Normal app writes; backend/profile/rewrite metadata present. |
| `history_jsonl` | 34 | 2026-05-27 14:30:09 UTC to 2026-05-30 08:23:02 UTC | Imported older JSONL rows; backend missing, but profile/rewrite metadata present. |
| `copyq` | 113 | single import timestamp 2026-05-30 08:50:29 UTC | Imported clipboard candidates; zero duration and missing backend/profile/rewrite are expected for this cohort. |

The 42 current JSONL entries all match SQLite rows by final-text hash, but none match SQLite `created_at` exactly. This is expected because JSONL and SQLite assign timestamps independently during live writes.

### Field Completeness

Non-empty SQLite fields:

| Field | Rows |
| --- | ---: |
| `id` | 434 |
| `created_at` | 434 |
| `text` | 434 |
| `raw_text` | 434 |
| `duration_seconds` | 434 |
| `word_count` | 434 |
| `metadata_json` | 434 |
| `schema_version` | 434 |
| `language` | 433 |
| `profile_id` | 321 |
| `rewrite_status` | 321 |
| `backend` | 287 |

Interpretation:

- Missing `backend` on 147 rows is expected for imported rows: 34 JSONL imports and 113 CopyQ imports.
- Missing `profile_id` and `rewrite_status` on 113 rows is expected for CopyQ imports.
- One missing `language` value exists in the CopyQ import cohort. This is low severity but worth normalizing to `unknown` or the active language during import if these rows will power analytics.

### Metadata Completeness

All 434 rows have valid `metadata_json`.

Metadata keys present:

- `raw_text`: 434
- `final_text`: 434
- `context`: 321
- `dictionary_hits`: 321
- `profile_id`: 321
- `profile_style`: 321
- `rewrite_status`: 321
- `snippet_hits`: 321
- `import_source`: 147
- `candidate_reason`: 113
- `copyq_row`: 113
- `copyq_text_had_trailing_space`: 113
- `timestamp_source`: 113
- `chat_period_trimmed`: 53
- `history_timestamp`: 34
- `punctuation_words`: 4

CopyQ import metadata:

- `candidate_reason`: `plain_text_natural_language_trailing_whisprbar_space` on 113 rows
- `timestamp_source`: `import_time_no_copyq_timestamp` on 113 rows
- `copyq_text_had_trailing_space`: true on 113 rows

### Language, Backend, Profile, Rewrite Distribution

Language:

- `de`: 431
- `en`: 2
- missing: 1

Backend:

- `deepgram`: 287
- missing: 147

Profile:

- `editor`: 223
- `chat`: 64
- `default`: 21
- `terminal`: 13
- missing: 113

Rewrite status:

- `not_requested`: 321
- missing: 113

The rewrite distribution is expected given current Flow profile overrides and import rows. It does mean this dataset currently has no successful AI rewrite examples for learning raw-to-rewritten behavior.

### Duration and Size

Duration seconds:

- Min: 0.0
- Median: 5.568
- Mean: 9.354
- Max: 95.87
- Zero duration rows: 113

The 113 zero-duration rows are exactly the CopyQ import cohort and should not be treated as failed recordings.

Final text size:

- Character length: min 6, median 98.5, mean 141.2, max 991
- Word count: min 1, median 17, mean 23.8, max 170
- Stored `word_count` mismatches: 0

### Raw vs Final Availability

- `text` present: 434
- `raw_text` column present: 434
- `metadata.raw_text` present: 434
- `metadata.final_text` present: 434
- `metadata.final_text` differs from `text`: 0
- `raw_text` column differs from `text`: 56
- `metadata.raw_text` differs from `text`: 56

Raw/final differences by metadata signal:

- `chat_period_trimmed`: 51
- `chat_period_trimmed` plus `punctuation_words`: 2
- `punctuation_words`: 2
- no explicit Flow metadata flag: 1

Interpretation: most raw/final differences are expected local Flow formatting. The single unflagged raw/final difference is likely basic postprocessing such as capitalization/spacing, which is expected but not explicitly tracked in metadata.

### Duplicate and Noise Signals

SQLite exact duplicate final texts:

- Duplicate groups: 1
- Duplicate rows in duplicate groups: 4
- Shape of the duplicate group: count 4, 13 characters, 2 words, SHA-256 prefix `25917eb62ba0`

SQLite normalized duplicate final texts:

- Duplicate groups: 1
- Duplicate rows in duplicate groups: 4

Noise indicators:

- Empty text rows: 0
- Text length <= 3 characters: 0
- One-word entries: 2
- Zero-duration rows: 113, all CopyQ imports
- Duplicate timestamps: 113 rows, all CopyQ imports sharing the import timestamp

Interpretation: no strong live-recording noise pattern was found. The only exact duplicate is small and repeated four times; it may be a legitimate repeated phrase rather than a storage bug. CopyQ zero durations and duplicate timestamps are expected import artifacts, not live transcription failures.

## Actionable Bugs and Product Issues

### 1. JSONL cleanup does not reliably enforce the documented 30-entry cap

Severity: medium privacy/storage issue.

Evidence:

- Current JSONL entries: 42.
- `write_history()` documents that history keeps only the last 30 entries.
- Cleanup only runs after `_history_write_count >= 10`, and `_history_write_count` is process-local memory.

Impact:

- If WhisprBar restarts before the counter reaches 10 writes, cleanup may not run.
- The plaintext JSONL file can grow beyond the documented cap, increasing privacy exposure.

Recommended fix:

- Run `cleanup_history(max_entries=30)` on startup or after every write, or compute the cleanup threshold from file state instead of a process-local counter.
- If performance is a concern, a safe compromise is to clean when the file has more than 30 lines, not merely every tenth write in the current process.

### 2. Transcript files and backups are too permissive for private dictation data

Severity: medium privacy issue on multi-user systems.

Evidence:

- `history.jsonl`: mode `664`
- `transcripts.sqlite3`: mode `644`
- database backups: mode `644`

Impact:

- Dictation history is readable by other local users.
- `history.jsonl` is also group-writable.

Recommended fix:

- Create transcript/history/database files with mode `600`.
- Create directories with restrictive permissions where practical.
- Apply the same mode to SQLite backups.
- Consider a startup repair/migration that chmods existing WhisprBar transcript storage files to `600`.

### 3. Metadata duplicates private text in multiple places

Severity: low-to-medium privacy/storage issue.

Evidence:

- SQLite stores final text in `text` and again in `metadata_json.final_text`.
- SQLite stores raw text in `raw_text` and again in `metadata_json.raw_text`.
- JSONL stores top-level `text`, `metadata.final_text`, and `metadata.raw_text`.

Impact:

- More copies of private text exist than necessary.
- Future deletion/redaction logic has to clear several fields.

Recommended fix:

- Keep structured columns as canonical storage.
- Store only non-content metadata in `metadata_json`, or make text duplication a deliberate schema decision documented in the privacy/settings UI.

### 4. Imported rows should use explicit placeholder metadata

Severity: low data-quality issue.

Evidence:

- CopyQ imports have missing `backend`, `profile_id`, and `rewrite_status`.
- One CopyQ row has missing `language`.

Impact:

- Analytics must special-case missing values.
- Missing values can be mistaken for live-write failures.

Recommended fix:

- For imports, use explicit values such as `backend: imported_copyq`, `profile_id: imported`, `rewrite_status: not_applicable`, and `language: unknown` when no better value exists.

## Expected Behavior / Non-Issues

- SQLite has far more rows than JSONL because it is the durable analysis store; JSONL is the recent history surface.
- Missing backend on old JSONL import rows is expected because the historical JSONL entries did not preserve backend at import time.
- CopyQ rows having zero duration is expected because they are clipboard imports, not recordings.
- CopyQ rows sharing a single timestamp is expected because metadata says `timestamp_source: import_time_no_copyq_timestamp`.
- `rewrite_status: not_requested` is expected for current rows because active Flow profile overrides set rewrite modes to `none`.
- JSONL and SQLite live-write timestamps differ by tiny amounts because each store assigns its own timestamp during the same dispatch.

## Data Usefulness

Strong signals for future transcript learning:

- Raw/final pairs are available for all 434 SQLite rows.
- Profile metadata is available for 321 rows.
- Language is available for 433 rows.
- Backend is available for all 287 live SQLite writes.
- Word counts and durations are internally consistent.
- The database has no invalid JSON metadata and passes integrity check.

Limits:

- There are no applied AI rewrite examples in this dataset.
- CopyQ imports need special handling because they are clipboard-derived, have no recording duration, and lack live context metadata.
- JSONL is recent-only and should not be treated as the canonical full dataset.

## Recommended Next Steps

1. Fix JSONL cleanup so the 30-entry cap is actually enforced across app restarts.
2. Restrict file permissions for transcript history, SQLite database, and transcript database backups to owner-only read/write.
3. Decide whether raw/final text should remain duplicated in `metadata_json`; if not, migrate future writes to content-free metadata.
4. Make import metadata explicit instead of missing where possible.
5. For learning workflows, use SQLite as the source of truth and filter by `import_source` so live dictations, JSONL imports, and CopyQ imports are analyzed separately.
