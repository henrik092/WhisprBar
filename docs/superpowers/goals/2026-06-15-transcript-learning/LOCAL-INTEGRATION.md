# Local Integration Notes

Date: 2026-06-15

These reports were copied back from the transcript-learning analysis worktree so the local `main` checkout keeps the agent findings next to the code that now uses them.

## Integrated Into Local Main

- The transcript analysis reports are now available under this goal directory.
- The Learning Inbox recommendation has been partially implemented in local `main` through `whisprbar/flow/learning_inbox.py` and the Settings WebView review controls.
- Browser MCP snapshots and local settings screenshots/previews are ignored by `.gitignore` so they do not stay visible as repo work.

## Still Open Product Work

- Add aggregate-only quality stats to History, especially raw/final change rate and dictionary/snippet hit counts.
- Add cleanup controls for JSONL and SQLite transcript data by age/source.
- Expand Learning Inbox beyond conservative dictionary candidates when the review flow has been proven.
- Add snippet suggestions only behind explicit user review.
- Decide whether transcript text should keep being duplicated in metadata JSON.

## Still Open Data Hygiene Work

- Make JSONL cleanup reliably enforce the documented recent-history cap across app restarts.
- Restrict transcript/history/database file permissions to owner-only read/write.
- Normalize imported-row metadata so analytics do not have to treat missing backend/profile/language as ambiguous live-write failures.

These are recorded as follow-up findings, not blockers for the current Learning Inbox merge.
