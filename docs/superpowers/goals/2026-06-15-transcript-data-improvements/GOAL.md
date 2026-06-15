# Goal: Transcript Data Improvements

Date: 2026-06-15

## Outcome

Complete and verify the six follow-up improvements identified after the transcript-learning analysis:

1. reliably enforce the JSONL recent-history cap across app restarts;
2. restrict transcript/history/database file permissions to owner-only read/write;
3. show more aggregate History stats, especially raw/final change rate and dictionary/snippet hits;
4. add local cleanup controls for JSONL and SQLite transcript data by age/source;
5. expand the Learning Inbox beyond the current conservative dictionary-only path where safe;
6. decide and document the metadata text-duplication policy, with code changes only when low-risk.

## Baseline

- Main worktree: `/home/rik/WhisprBar`, branch `main`, currently clean and locally ahead of `origin/main`.
- Goal worktree: `/home/rik/.config/superpowers/worktrees/WhisprBar/transcript-data-improvements`, branch `codex/transcript-data-improvements`, created from local `main` at `e0e2d5a`.
- Existing analysis reports live under `docs/superpowers/goals/2026-06-15-transcript-learning/`.
- Current Learning Inbox has no pending local candidates.
- Current local dictionary has 13 entries.

## Constraints

- Treat transcript text as private local data.
- Do not send transcript content to external services.
- Do not delete user history/database records without a separate explicit approval.
- Cleanup UI actions may be implemented, but destructive actions must require confirmation in the app.
- Preserve `flow_history_storage = "never"` as a hard stop for history, SQLite, and learning.
- Keep changes compatible with the existing JSONL and SQLite schema unless a migration is explicitly justified and tested.
- Do not push to GitHub without explicit approval.

## Non-Goals

- No cloud sync, accounts, paid plans, or remote transcript learning.
- No new transcription backend.
- No broad automatic dictionary/snippet creation without local user review.
- No release/tagging work.

## Primary Verifier

Run from the goal worktree using the main checkout virtualenv:

```bash
PYTHONPATH=/home/rik/.config/superpowers/worktrees/WhisprBar/transcript-data-improvements /home/rik/WhisprBar/.venv/bin/pytest -q
```

Completion requires no failures.

## Supporting Checks

```bash
PYTHONPATH=/home/rik/.config/superpowers/worktrees/WhisprBar/transcript-data-improvements /home/rik/WhisprBar/.venv/bin/python -m compileall -q whisprbar tests
git diff --check
```

Also verify:

- targeted tests exist for each changed behavior;
- generated settings HTML contains the new stats/cleanup/review controls where relevant;
- privacy-sensitive files created by tests are mode `600` where the platform supports chmod;
- destructive cleanup actions are confirm-gated in UI or backend;
- reports document what remains intentionally deferred.

## Iteration Loop

1. Inspect the specific subsystem and write/update focused failing tests.
2. Implement the smallest behavior change that satisfies the task.
3. Run targeted tests for that task.
4. Review the change for privacy, backwards compatibility, and UI clarity.
5. Repeat for the next task.
6. Run full verification and record the final result.

## Delegation Map

- Lane A: history retention and file permissions.
- Lane B: aggregate stats and History UI.
- Lane C: cleanup action backend and confirm-gated UI plumbing.
- Lane D: Learning Inbox expansion and metadata duplication policy.
- Parent agent owns integration, conflict resolution, final tests, and final completion proof.

## Approval Gates

Ask before:

- deleting or mutating real local transcript/history data;
- pushing to GitHub;
- changing public defaults for history retention, backend selection, or cloud rewrite behavior;
- making broad automatic learning decisions that add user-visible dictionary or snippet entries without review.

## Blocker Standard

Only mark blocked after the same external blocker prevents progress for three consecutive goal turns and no safe local work remains. Ambiguous product choices should be recorded as deferred, not treated as blockers.

## Completion Proof

Before marking complete, provide:

- commits/changed paths;
- tests and exact pass output;
- local UI or generated-HTML evidence for visible changes;
- documented remaining risks or deferred work;
- confirmation that no real private transcript data was printed or deleted.
