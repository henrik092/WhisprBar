# Dictionary Learner Report

Date: 2026-06-15

Lane: Dictionary Learner

## Scope

Inspected local private data only:

- `/home/rik/.local/share/whisprbar/history.jsonl`
- `/home/rik/.local/share/whisprbar/transcripts.sqlite3`
- `/home/rik/.config/whisprbar/dictionary.json`

No transcript records were edited. No transcript bodies are included in this report.

## Data Snapshot

| Source | Count | Range / Notes |
| --- | ---: | --- |
| JSONL history | 42 valid rows | 2026-06-14T13:08:43Z to 2026-06-15T16:20:51Z |
| SQLite transcripts | 434 rows | 2026-05-27T14:30:09Z to 2026-06-15T16:20:51Z |
| SQLite raw/final differences | 56 rows | Mostly punctuation/formatting deletes or sentence cleanup, not stable phrase replacements |
| Current dictionary | 4 entries | Existing WhisprBar variants preserved |

Current dictionary entries already cover these WhisprBar variants:

- `Vispaba` -> `WhisprBar`
- `Whisperbar` -> `WhisprBar`
- `Whisper Bar` -> `WhisprBar`
- `Wispr Bar` -> `WhisprBar`

## Automatic Additions

None.

Reason: no new candidate met the GOAL threshold for automatic insertion. The raw-to-final analysis found no short phrase replacement recurring across multiple rows, and no new obvious WhisprBar/project/product-name misrecognition variant was present in raw text.

Because the dictionary was not changed, no backup file was created.

## Review-Only Candidates

These are not automatic additions because the stored data shows intended product names already written correctly, or only suggests speculative future style protection rather than an observed recognition mistake.

| Candidate | Evidence count | Why review-only |
| --- | ---: | --- |
| `codex` -> `Codex` | 13 rows already contain `Codex` | Repeated product term, but no observed lowercase `codex` or raw-to-final correction. |
| `github` -> `GitHub` | 12 rows already contain `GitHub`; 15 total final occurrences | Repeated product term, but no observed lowercase `github` or raw-to-final correction. |
| `openai` -> `OpenAI` | 2 rows already contain `OpenAI` | Product term, but low count and no observed lowercase `openai` correction. |
| `git hub` -> `GitHub` | 0 observed raw rows; 12 rows contain `GitHub` | Plausible speech split, but speculative in this dataset. |
| `open ai` -> `OpenAI` | 0 observed raw rows; 2 rows contain `OpenAI` | Plausible speech split, but speculative in this dataset. |

## Rejected Candidate Classes

- Sentence-level raw/final rewrites: rejected because dictionary entries should be short, stable phrase replacements.
- One-off replacement spans: rejected because there were no repeated short phrase substitutions, and one-off private or contextual phrases are too risky.
- Common words such as `flow`: rejected because they are ambiguous outside WhisprBar Flow and could damage normal dictation.
- Existing WhisprBar variants: already present, preserved without duplication.

## Recommendation

Leave the dictionary unchanged for now. The useful next step is to add a future suggestion workflow that records explicit user accept/reject decisions for proposed dictionary entries; the current passive transcript data is not enough to safely infer new corrections beyond the existing WhisprBar variants.
