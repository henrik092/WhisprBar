# Goal: Learn From WhisprBar Transcript History

## Outcome

Analyze the user's saved WhisprBar dictation history and local transcript database to improve the personal Flow experience:

- identify likely recurring misrecognitions and add only high-confidence spoken-to-written corrections to the local Flow dictionary;
- produce a concise data-quality report about what is stored, what looks useful, and what looks risky or noisy;
- propose practical next uses for the saved data that would make WhisprBar simpler, more accurate, or more personally helpful.

## Baseline

Worktree:

`/home/rik/.config/superpowers/worktrees/WhisprBar/transcript-learning-analysis`

Branch:

`codex/transcript-learning-analysis`

Observed local data on 2026-06-15:

- JSONL history: `~/.local/share/whisprbar/history.jsonl`, 42 valid entries.
- SQLite transcript store: `~/.local/share/whisprbar/transcripts.sqlite3`, 434 rows, range 2026-05-27 to 2026-06-15.
- Dictionary: `~/.config/whisprbar/dictionary.json`, 4 existing entries, all WhisprBar variants.
- Snippets: `~/.config/whisprbar/snippets.json`, empty list.
- Baseline tests in this worktree: `.venv/bin/pytest -q` passed with `367 passed, 38 skipped, 10 warnings`.

## Constraints

- Treat transcripts as private local data. Do not print or paste large transcript bodies into chat.
- Do not send transcript content to external services.
- Do not edit history or transcript database content.
- Before changing `~/.config/whisprbar/dictionary.json`, create a timestamped backup next to it.
- Automatically add dictionary entries only when evidence is strong:
  - repeated candidate across multiple transcript rows, or
  - obvious WhisprBar/project/product-name variants, or
  - raw-to-final metadata clearly proves a correction.
- Do not add low-confidence, ambiguous, one-off, private-personal, or sentence-like replacements automatically.
- Put uncertain candidates in a review report instead of the dictionary.
- Keep code changes in the analysis worktree until the user explicitly approves merge/push.

## Delegation Map

### Lane 1: Dictionary Learner

Objective: inspect transcript/history data and current dictionary, identify high-confidence misrecognition corrections, update `~/.config/whisprbar/dictionary.json` with a backup, and write a report of added and rejected candidates.

Verifier:

- backup file exists;
- dictionary remains valid JSON list of `{spoken, written}` objects;
- existing dictionary entries are preserved;
- `load_dictionary()` can read the updated file;
- report explains each automatic addition with evidence counts, without dumping private transcript bodies.

### Lane 2: Stored Data Audit

Objective: analyze what is stored in JSONL and SQLite, including counts, age range, metadata quality, duplicates, raw/final differences, language/backend/profile distribution, and privacy/noise risks.

Verifier:

- report includes counts from both sources;
- no large transcript excerpts are printed;
- findings distinguish actionable bugs from expected behavior and mere observations.

### Lane 3: Data Product Ideas

Objective: propose practical uses for the saved data that would improve WhisprBar, such as adaptive dictionary suggestions, snippet suggestions, style/profile learning, quality checks, or cleanup controls.

Verifier:

- report ranks ideas by usefulness, implementation effort, and privacy risk;
- each idea names the data source it would use and the user-facing benefit;
- recommendations avoid cloud sync/accounts/new engines unless explicitly marked as out of scope.

## Primary Verifier

After integrating the lane results, run in the worktree:

```bash
.venv/bin/pytest -q
```

Completion requires no failures.

## Supporting Checks

Run in the worktree:

```bash
.venv/bin/python -m compileall -q whisprbar tests
.venv/bin/python - <<'PY'
from whisprbar.flow.dictionary import load_dictionary
entries = load_dictionary()
assert all(entry.spoken and entry.written for entry in entries)
print(len(entries))
PY
```

Also verify:

- dictionary backup path;
- final dictionary entry count;
- reports exist under this goal directory;
- any changed repo files are intentional and scoped.

## Iteration Loop

1. Snapshot current data counts and dictionary entries.
2. Dispatch or run the three analysis lanes with disjoint responsibilities.
3. Integrate lane outputs.
4. Apply only high-confidence dictionary additions.
5. Run verifiers.
6. Record completion evidence and remaining review candidates.

## Approval Gates

Ask the user before:

- pushing to GitHub;
- merging the analysis worktree back to `main`;
- deleting any history/database records;
- adding cloud/API-based learning;
- adding broad automatic dictionary entries whose confidence is not clearly high.

## Blocker Standard

Only mark blocked when the transcript files are unreadable, the dictionary cannot be safely backed up/written, or an external user decision is required after repeated attempts. Ambiguous candidates are not blockers; they go into the review report.

## Completion Proof

Before marking complete, provide:

- changed paths, including dictionary backup and updated dictionary if changed;
- added dictionary entries and why they were high confidence;
- path to the data audit report;
- path to the idea report;
- final pytest result;
- final compileall result;
- remaining risks and review-only candidates.
