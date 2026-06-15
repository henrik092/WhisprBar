# Result: Transcript Learning Analysis

Date: 2026-06-15

## Summary

Three lanes analyzed the local WhisprBar transcript data without sending transcript content externally and without including transcript bodies in reports.

## Dictionary Outcome

No dictionary entries were added automatically.

Reason: the current stored data did not prove any new repeated, short, high-confidence raw-to-final misrecognition. The existing dictionary already contains 4 WhisprBar variants and was left unchanged:

- `Vispaba` -> `WhisprBar`
- `Whisperbar` -> `WhisprBar`
- `Whisper Bar` -> `WhisprBar`
- `Wispr Bar` -> `WhisprBar`

Because the dictionary was not changed, no dictionary backup was required.

Review-only candidates:

- `codex` -> `Codex`
- `github` -> `GitHub`
- `openai` -> `OpenAI`
- `git hub` -> `GitHub`
- `open ai` -> `OpenAI`

These should be handled through a future review UI, not automatic insertion.

## Stored Data Findings

- JSONL history: 42 valid entries, 0 invalid lines, range 2026-06-14 to 2026-06-15.
- SQLite transcript store: 434 rows, integrity check ok, range 2026-05-27 to 2026-06-15.
- SQLite source split: 287 live writes, 34 JSONL imports, 113 CopyQ imports.
- Raw/final pairs exist for all SQLite rows.
- 56 raw/final differences are mostly explained by local Flow formatting.
- No strong live-recording duplicate/noise pattern was found.

Actionable concerns:

- JSONL has 42 entries despite the documented 30-entry cap.
- Transcript files and database backups are currently group/world-readable even though they contain private dictation data.

## Product Recommendations

Top recommendation: add a local Learning Inbox with approve/dismiss controls before enabling broader automatic learning.

Recommended order:

1. Add aggregate-only quality stats to History.
2. Add cleanup controls for SQLite/history by age/source.
3. Add local Learning Inbox infrastructure and dismissal state.
4. Add dictionary suggestion mining from raw/final differences.
5. Add snippet suggestion mining from repeated approved-safe outputs.
6. Add profile/style usage hints later.

## Reports

- `dictionary-learner-report.md`
- `stored-data-audit-report.md`
- `data-product-ideas-report.md`

## Verification

- Baseline in this worktree: `.venv/bin/pytest -q` passed with `367 passed, 38 skipped, 10 warnings`.
- Compile check: `.venv/bin/python -m compileall -q whisprbar tests` passed.
- Dictionary load check: `load_dictionary()` returned 4 valid entries.

Final full-suite verification is run after writing this result file.
