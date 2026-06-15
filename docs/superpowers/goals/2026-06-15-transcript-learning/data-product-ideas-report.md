# Lane 3 Report: Data Product Ideas for Transcript Learning

Date: 2026-06-15

Scope: read-only inspection of WhisprBar Flow dictionary, snippets, transcript store, JSONL history, settings, and stats paths. No source, dictionary, history, or database files were modified. This report intentionally avoids private transcript bodies.

## Current Product Surface

WhisprBar already has the right local primitives for useful personalization:

- `whisprbar/transcript_store.py` stores completed dictations in SQLite with `text`, `raw_text`, `duration_seconds`, `word_count`, `backend`, `profile_id`, `rewrite_status`, and JSON metadata.
- `whisprbar/utils.py` writes a smaller JSONL history with text, language, duration, word count, and Flow metadata.
- `whisprbar/flow/pipeline.py` records local processing metadata, including profile, app context, rewrite status, dictionary hits, snippet hits, smart-formatting/backtrack metadata, raw text, and final text.
- `whisprbar/flow/dictionary.py` and `whisprbar/flow/snippets.py` are simple local JSON-backed replacement systems.
- `whisprbar/ui/settings_webview.py` already exposes Words and History pages with manual dictionary/snippet editing, retention settings, and database counts.
- `whisprbar/flow/stats.py` currently computes basic local stats from history entries.

## Aggregate Data Snapshot

Local data inspected only as metadata and aggregate counts:

- JSONL history: 42 valid entries, 0 invalid lines, range 2026-06-14 to 2026-06-15.
- SQLite transcript store: 434 rows, range 2026-05-27 to 2026-06-15.
- SQLite sources: 287 live writes, 34 history imports, 113 CopyQ imports.
- Languages: 431 German, 2 English, 1 missing.
- Profiles: 223 editor, 64 chat, 21 default, 13 terminal, 113 missing/imported.
- Backend: 287 Deepgram rows, 147 missing/imported.
- Raw/final comparison: raw text present on all 434 rows; 56 rows have raw text different from final text.
- Dictionary hits: 0 rows.
- Snippet hits: 0 rows.
- Dictionary file: 4 entries.
- Snippets file: 0 entries.

Interpretation: the best first product is not automatic behavior change. The best first product is a local review queue that turns raw/final differences and repeated patterns into approve-or-dismiss suggestions.

## Ranked Ideas

| Rank | Idea | Data Source | User Benefit | Usefulness | Effort | Privacy Risk |
|---:|---|---|---|---|---|---|
| 1 | Reviewable dictionary suggestions | SQLite `raw_text` vs `text`, existing dictionary, metadata `dictionary_hits` | Makes recurring project/product names correct without manual hunting | High | Medium | Medium |
| 2 | Local cleanup dashboard | SQLite/history timestamps, source, profile, duration, duplicate hashes, retention config | Lets user see and prune stored private dictation data intentionally | High | Low-Medium | Low |
| 3 | Snippet suggestions from repeated whole messages | SQLite final text fingerprints, word count, profile/context, existing snippets | Turns repeated canned replies/signoffs into spoken shortcuts | Medium-High | Medium | Medium-High |
| 4 | Quality signals and tuning hints | Duration, word count, raw/final diff, backend, language, profile, VAD/audio settings | Shows when dictation is getting worse and which setting might help | Medium-High | Medium | Low-Medium |
| 5 | Profile/style usage report | Metadata context/profile, rewrite status, raw/final length deltas | Makes Flow profile defaults easier to tune per app | Medium | Medium | Low-Medium |
| 6 | Personal preserve-terms list for rewrite prompts | Dictionary entries, approved suggestion terms, rewrite prompt `dictionary_terms` | Keeps names, products, repos, commands stable during optional rewrite | Medium | Low | Low |
| 7 | History-aware settings shortcuts | Current settings page plus aggregate counts and stale-data checks | Surfaces useful actions exactly where data exists | Medium | Low | Low |
| 8 | Local "learning inbox" export | Suggestion candidates plus aggregate evidence, no bodies by default | Gives an auditable review artifact before applying changes | Medium | Low-Medium | Low |
| 9 | Language/profile gap detector | Language/profile distributions and app context | Warns when most rows are German but some contexts should be English or terminal-literal | Low-Medium | Low | Low |
| 10 | Cloud/account learning | Full transcript sync or remote model personalization | Could personalize heavily, but violates current constraints | Out of scope | High | High |

## Top Recommendations

### 1. Add a Local Learning Inbox

Build a new local-only review screen under Settings -> Words, or a separate command, that lists candidate improvements grouped by type:

- dictionary candidates;
- snippet candidates;
- cleanup candidates;
- profile/style hints.

Each item should have `Approve`, `Dismiss`, and `Never suggest this` controls. Do not apply automatically except for narrow high-confidence dictionary cases already allowed by the goal. Store suggestion state separately from transcript bodies, for example `~/.local/share/whisprbar/learning_suggestions.json`.

Why first: it unlocks personalization while keeping the user in control. It also avoids risky automatic edits from private or ambiguous transcript content.

Implementation shape:

- Read candidates from `transcripts.sqlite3` in read-only mode.
- Use hashes/ids for dismissal state.
- Write approved dictionary entries through existing `save_dictionary()`.
- Write approved snippets through existing `save_snippets()`.
- Never include full transcript bodies in the default list; show a short local preview only when the user opens a candidate.

### 2. Build Dictionary Suggestions From Raw-to-Final Evidence

Use rows where `raw_text != text` as the strongest signal. Compare repeated short token/phrase differences across rows, then suggest `{spoken, written}` entries only when:

- the candidate repeats across multiple rows;
- the written form looks like a stable proper noun/product/repo term;
- the phrase is short, not a sentence;
- it is not already covered by the current dictionary.

Data source: SQLite `raw_text`, `text`, `metadata_json`, existing `dictionary.json`.

User benefit: fixes recurring misrecognitions such as app names, product names, project names, and technical terms without requiring the user to remember the exact bad recognition.

Effort: medium. The hard part is conservative diffing and review UX, not storage.

Privacy risk: medium, because deriving candidates requires reading transcript text locally. Keep all processing local and avoid broad previews.

### 3. Add Data Cleanup Controls Before More Learning

The History page already shows database counts and retention mode. Add direct controls:

- delete rows older than N days;
- delete imported CopyQ rows only;
- delete duplicate final-text groups;
- clear SQLite transcript database and JSONL history separately;
- export aggregate-only stats;
- show estimated private data volume by count/date/source, not body text.

Data source: SQLite counts/source metadata, JSONL history count, existing retention settings.

User benefit: makes the database feel transparent and safe. This should exist before adding richer suggestions, because learning makes saved private text more visible and valuable.

Effort: low-medium. The settings UI already renders stats and retention. The missing part is action plumbing plus confirmation.

Privacy risk: low if the UI defaults to counts and source/date filters.

### 4. Suggest Snippets From Repeated Full Outputs

Since snippets are currently empty and snippet hits are zero, good snippet UX can create immediate value. Start with conservative candidates:

- exact or near-exact repeated final outputs;
- repeated short signoffs or reply templates;
- repeated messages inside chat/email profiles;
- exclude one-off long private text and terminal/editor content by default.

Data source: SQLite final text hashes, profile/context metadata, existing snippets.

User benefit: lets the user approve spoken triggers for repeated messages instead of re-dictating them.

Effort: medium. The current snippet engine is already enough; the work is candidate mining and UI.

Privacy risk: medium-high because snippet candidates may be personal. Require explicit approval and never auto-create snippets.

### 5. Add Quality Signals, Not Just Counts

Extend `get_transcript_stats()` or add a sibling read-only analyzer that computes:

- raw-to-final change rate;
- average words per minute by profile/backend/day;
- empty/very short/very long rows;
- duplicate row count;
- rewrite attempted/applied/failed rates;
- dictionary/snippet hit rates;
- imported-vs-live split.

Data source: SQLite aggregate queries and metadata JSON.

User benefit: helps tune recording, VAD, backend, profile, and rewrite settings without reading the private transcript bodies.

Effort: medium. Most metrics are simple aggregates. The current settings History page already has a natural place to display a compact summary.

Privacy risk: low-medium when limited to aggregates.

## Lower-Risk Quick Wins

- Show "Dictionary hits" and "Snippet hits" in History stats. Current aggregate is zero, which is valuable feedback.
- Add "Rows with raw/final changes" to History stats. Current aggregate is 56 of 434.
- Add "Stored by source" actions next to the existing source counts.
- Add a "Review suggestions" button on the Words page only when candidate count is nonzero.
- Add a one-click "Open dictionary/snippets file" equivalent to the GTK settings path if the WebView UI is now the primary settings UI.

## Privacy Guardrails

- Keep all learning local by default.
- Do not send transcript bodies to cloud APIs for learning.
- Make suggestions opt-in and reviewable.
- Separate `dismissed suggestion` state from transcript bodies.
- Prefer aggregate counters on dashboards.
- Show transcript text only inside an explicit local review action.
- Never auto-create snippets from private sentence-like content.
- Keep `flow_history_storage=never` as a hard stop for both JSONL and SQLite learning.
- If `auto_delete` is enabled, suggestion generation should respect the same retention window.

## Suggested Implementation Order

1. Add aggregate-only quality stats to the History page.
2. Add cleanup controls for SQLite/history by age/source.
3. Add local Learning Inbox infrastructure and dismissal state.
4. Add dictionary suggestion mining from raw/final differences.
5. Add snippet suggestion mining from repeated approved-safe outputs.
6. Add profile/style usage hints after dictionary/snippet workflows are proven.

## Out of Scope Unless Explicitly Approved

- Cloud sync.
- Accounts.
- Remote transcript analysis.
- New transcription engines.
- Automatic broad dictionary expansion.
- Automatic snippet creation.
- Any learning path that ignores `flow_history_storage`.

