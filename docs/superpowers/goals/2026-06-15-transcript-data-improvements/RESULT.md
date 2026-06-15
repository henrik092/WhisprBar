# Result: Transcript Data Improvements

Date: 2026-06-15

## Implemented

- JSONL history now enforces the documented 30-entry cap after every normal write, so app restarts cannot leave an oversized recent-history file around.
- Local transcript storage paths are repaired to private owner-only permissions where supported:
  - data directory: `700`;
  - JSONL history: `600`;
  - SQLite database and sidecars: `600`.
- Settings History stats now include aggregate-only totals for words, duration, words per minute, raw/final changes, dictionary-hit rows, and snippet-hit rows.
- Settings History now has confirm-gated cleanup controls for CopyQ imports, JSONL history, and SQLite transcript rows. The backend requires the exact phrase `DELETE TRANSCRIPTS`.
- Learning Inbox now supports body-free `snippet_hint` candidates for repeated short outputs in review-safe profiles. Approval records review state only; it does not create snippets automatically.
- New transcript writes treat `text` and `raw_text` columns as canonical content fields and strip `raw_text` / `final_text` from metadata JSON to reduce duplicate private text.

## Privacy Policy

Transcript bodies remain local. New aggregate stats and Learning Inbox previews do not render transcript bodies. Cleanup tests use temporary files only. Real local transcript deletion remains behind explicit UI confirmation.

## Deferred

- Rich snippet creation remains deferred until there is a dedicated review flow where the user explicitly chooses trigger and body.
- Existing historical SQLite/JSONL rows are not migrated in place; readers remain compatible with legacy metadata containing duplicated text.
- No cloud/account learning was added.
