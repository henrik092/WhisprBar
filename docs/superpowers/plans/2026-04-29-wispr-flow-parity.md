# Wispr Flow Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn WhisprBar into a Linux-first dictation tool with Wispr Flow-class capabilities: fast dictation, smart cleanup, app-aware style profiles, local dictionary, snippets, voice commands, history, and a strong test story without adding account, SaaS, or team-sync complexity.

**Architecture:** Keep the existing recording, backend, tray, paste, and settings foundations. Add a focused `whisprbar/flow/` package that owns the post-transcription pipeline: active-app context, profile selection, dictionary replacement, snippet expansion, command detection, rewrite provider routing, and final output metadata. Integrate that pipeline into `whisprbar/main.py` behind configuration flags so the current simple dictation path remains available.

**Tech Stack:** Python 3.12, GTK 3, existing WhisprBar config/history/paste modules, Deepgram/OpenAI/ElevenLabs/faster-whisper/sherpa backends, optional OpenAI-compatible rewrite endpoint, pytest.

---

## Scope

### Build

- Flow Mode as a new optional feature group, enabled by `flow_mode_enabled`.
- A deterministic local text pipeline for cleanup, dictionary, snippets, and commands.
- Optional AI rewrite for style and command execution through an OpenAI-compatible provider.
- App-aware profiles based on active X11 window metadata, with safe Wayland fallback.
- Settings UI entries for Flow Mode, rewrite mode, context awareness, dictionary, snippets, and profile defaults.
- Test coverage for each new boundary plus end-to-end pipeline behavior.

### Do Not Build

- Wispr account login, subscription logic, cloud sync, team snippets, enterprise controls, mobile clients, or cross-device state sync.
- Deep OS accessibility-tree reading like macOS/Windows Flow context awareness. Linux implementation starts with active app/window class and title.
- Real-time text insertion while speaking. WhisprBar may show progress/preview, but insertion remains after recording stops unless a backend already supports stable streaming.

## Baseline State

- Working branch: `codex/wispr-flow-parity`
- Worktree: `/home/rik/WhisprBar/.claude/worktrees/wispr-flow-parity`
- Baseline test command: `/home/rik/WhisprBar/.venv/bin/pytest`
- Baseline result before any implementation: `1 failed, 230 passed, 4 skipped`
- Known baseline failure: `tests/test_events.py::TestEventBus::test_emit_on_main_thread_fallback`

The first implementation task must fix or quarantine the baseline failure with a deterministic test update. Do not start feature work until the baseline suite is green.

## File Map

- Modify `whisprbar/config.py`: add default keys for Flow Mode, rewrite, profiles, dictionary, snippets, and command mode.
- Modify `whisprbar/config_types.py`: add typed config dataclasses for Flow settings.
- Modify `whisprbar/main.py`: replace the direct `text -> history -> paste` path with `text -> FlowPipeline -> history -> paste`.
- Modify `whisprbar/paste.py`: accept paste policy metadata from profiles while keeping existing behavior as default.
- Modify `whisprbar/transcription/postprocess.py`: keep low-level cleanup but delegate advanced Flow cleanup to the new pipeline.
- Create `whisprbar/flow/__init__.py`: public exports.
- Create `whisprbar/flow/models.py`: dataclasses for context, profile, pipeline input/output, dictionary entries, snippets, commands.
- Create `whisprbar/flow/context.py`: active window/app detection for X11 and safe fallback for Wayland/unknown sessions.
- Create `whisprbar/flow/profiles.py`: built-in profile matching and config override resolution.
- Create `whisprbar/flow/dictionary.py`: load/save/apply dictionary entries.
- Create `whisprbar/flow/snippets.py`: load/save/apply snippet expansions.
- Create `whisprbar/flow/commands.py`: detect explicit command utterances and map them to rewrite actions.
- Create `whisprbar/flow/rewrite.py`: provider interface, no-op provider, OpenAI-compatible provider, prompt building, timeout/error handling.
- Create `whisprbar/flow/pipeline.py`: orchestration of local cleanup, dictionary, snippets, command handling, rewrite, and final output metadata.
- Modify `whisprbar/ui/settings.py`: add Flow tab and management rows.
- Modify `whisprbar/ui/history.py`: display raw/final metadata where available without breaking older history entries.
- Modify `whisprbar/utils.py`: extend `write_history()` to accept optional metadata.
- Test files:
  - `tests/test_events.py`
  - `tests/test_flow_models.py`
  - `tests/test_flow_context.py`
  - `tests/test_flow_profiles.py`
  - `tests/test_flow_dictionary.py`
  - `tests/test_flow_snippets.py`
  - `tests/test_flow_commands.py`
  - `tests/test_flow_rewrite.py`
  - `tests/test_flow_pipeline.py`
  - `tests/test_main_flow_integration.py`
  - `tests/test_config.py`
  - `tests/test_config_types.py`
  - `tests/test_paste.py`
  - `tests/test_utils.py`

---

## Task 1: Stabilize Baseline Tests

**Files:**
- Modify: `whisprbar/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Reproduce the known failure**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_events.py::TestEventBus::test_emit_on_main_thread_fallback -v
```

Expected before fix: FAIL because `GLib.idle_add()` schedules asynchronously when `gi.repository.GLib` exists, so the test's immediate assertion sees `[]`.

- [ ] **Step 2: Decide the intended contract**

Use this contract:

- If GLib is unavailable, `emit_on_main_thread()` emits synchronously.
- If GLib is available, `emit_on_main_thread()` schedules via `GLib.idle_add()` and returns immediately.
- Tests must verify scheduling with a mocked GLib rather than assuming synchronous delivery in environments with GTK installed.

- [ ] **Step 3: Update tests**

Add one test that injects unavailable GLib/import failure and expects direct synchronous emit. Add another test that mocks `GLib.idle_add()` and executes the callback immediately, proving the scheduling path works without requiring a real GTK loop.

- [ ] **Step 4: Run focused tests**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_events.py -v
```

Expected: all event tests pass.

- [ ] **Step 5: Run full baseline**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/pytest
```

Expected: `231 passed, 4 skipped` or better.

- [ ] **Step 6: Commit baseline fix**

```bash
git add whisprbar/events.py tests/test_events.py
git commit -m "fix: stabilize event bus main-thread tests"
```

---

## Task 2: Add Flow Configuration

**Files:**
- Modify: `whisprbar/config.py`
- Modify: `whisprbar/config_types.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_config_types.py`

- [ ] **Step 1: Add failing tests for default config keys**

Assert these defaults:

```python
{
    "flow_mode_enabled": False,
    "flow_rewrite_enabled": False,
    "flow_rewrite_provider": "none",
    "flow_rewrite_model": "",
    "flow_rewrite_timeout_seconds": 12.0,
    "flow_context_awareness_enabled": True,
    "flow_command_mode_enabled": True,
    "flow_dictionary_enabled": True,
    "flow_snippets_enabled": True,
    "flow_default_profile": "default",
    "flow_profiles": {},
}
```

- [ ] **Step 2: Implement defaults and validation**

Add the keys to `DEFAULT_CFG`. Clamp `flow_rewrite_timeout_seconds` to `1.0..60.0`. If `flow_rewrite_provider` is not one of `none`, `openai_compatible`, set it to `none`.

- [ ] **Step 3: Add typed config**

Add:

```python
@dataclass(frozen=True)
class FlowConfig:
    flow_mode_enabled: bool = False
    flow_rewrite_enabled: bool = False
    flow_rewrite_provider: str = "none"
    flow_rewrite_model: str = ""
    flow_rewrite_timeout_seconds: float = 12.0
    flow_context_awareness_enabled: bool = True
    flow_command_mode_enabled: bool = True
    flow_dictionary_enabled: bool = True
    flow_snippets_enabled: bool = True
    flow_default_profile: str = "default"
    flow_profiles: Dict[str, Any] = field(default_factory=dict)
```

Wire it into `AppConfig.from_dict()` and `AppConfig.to_dict()`.

- [ ] **Step 4: Run config tests**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_config.py tests/test_config_types.py -v
```

- [ ] **Step 5: Commit**

```bash
git add whisprbar/config.py whisprbar/config_types.py tests/test_config.py tests/test_config_types.py
git commit -m "feat: add flow mode configuration"
```

---

## Task 3: Create Flow Data Models

**Files:**
- Create: `whisprbar/flow/__init__.py`
- Create: `whisprbar/flow/models.py`
- Create: `tests/test_flow_models.py`

- [ ] **Step 1: Write model tests**

Cover:

- `AppContext` defaults to unknown app, unknown title, session from config/runtime.
- `FlowProfile` supports style, paste policy, rewrite mode, and command allowances.
- `FlowInput` preserves raw transcript and language.
- `FlowOutput` preserves raw text, final text, metadata, command result, snippet hits, dictionary hits, profile id, and rewrite status.

- [ ] **Step 2: Implement dataclasses**

Use frozen dataclasses where possible:

```python
@dataclass(frozen=True)
class AppContext:
    session_type: str
    app_class: str = ""
    app_name: str = ""
    window_title: str = ""

@dataclass(frozen=True)
class FlowProfile:
    profile_id: str
    label: str
    style: str = "plain"
    rewrite_mode: str = "none"
    paste_sequence: Optional[str] = None
    add_space: Optional[bool] = None
    add_newline: Optional[bool] = None

@dataclass(frozen=True)
class FlowInput:
    text: str
    language: str
    context: AppContext

@dataclass(frozen=True)
class FlowOutput:
    raw_text: str
    final_text: str
    profile_id: str
    rewrite_status: str = "not_requested"
    command: Optional[str] = None
    dictionary_hits: Tuple[str, ...] = ()
    snippet_hits: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 3: Export public classes**

Expose the model classes in `whisprbar/flow/__init__.py`.

- [ ] **Step 4: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_models.py -v
git add whisprbar/flow/__init__.py whisprbar/flow/models.py tests/test_flow_models.py
git commit -m "feat: add flow pipeline models"
```

---

## Task 4: Active App Context Detection

**Files:**
- Create: `whisprbar/flow/context.py`
- Create: `tests/test_flow_context.py`

- [ ] **Step 1: Write tests for context detection**

Cover:

- Wayland returns `AppContext(session_type="wayland")` without trying X11 tools.
- Missing `xdotool` returns safe unknown context.
- X11 with mocked `xdotool getactivewindow`, `xdotool getwindowname`, and `xprop WM_CLASS` returns class and title.
- Timeouts return safe unknown context.

- [ ] **Step 2: Implement detection**

Implement `detect_app_context(session_type: Optional[str] = None) -> AppContext`. Reuse the style of `paste.detect_auto_paste_sequence()`: short subprocess timeout, no hard failure, debug logging only.

- [ ] **Step 3: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_context.py -v
git add whisprbar/flow/context.py tests/test_flow_context.py
git commit -m "feat: detect app context for flow mode"
```

---

## Task 5: Built-In Profiles

**Files:**
- Create: `whisprbar/flow/profiles.py`
- Create: `tests/test_flow_profiles.py`

- [ ] **Step 1: Write profile matching tests**

Cover these built-ins:

- `terminal`: app class/title contains terminal-like keywords, no rewrite, `ctrl_shift_v`.
- `chat`: Slack/Discord/Telegram/Signal/WhatsApp style, concise casual rewrite when enabled.
- `email`: Thunderbird/Evolution/webmail title keywords, professional rewrite when enabled.
- `notes`: Obsidian/Notion/Logseq, structured clean rewrite when enabled.
- `editor`: Code/JetBrains/Sublime/Vim/Emacs, no rewrite by default.
- `default`: clean rewrite when enabled, existing paste behavior.

- [ ] **Step 2: Implement built-ins and override merge**

Add `resolve_profile(context, cfg) -> FlowProfile`. Merge user overrides from `cfg["flow_profiles"]` by profile id, but ignore unknown keys.

- [ ] **Step 3: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_profiles.py -v
git add whisprbar/flow/profiles.py tests/test_flow_profiles.py
git commit -m "feat: add flow app profiles"
```

---

## Task 6: Local Dictionary

**Files:**
- Create: `whisprbar/flow/dictionary.py`
- Create: `tests/test_flow_dictionary.py`

- [ ] **Step 1: Define storage**

Use `~/.config/whisprbar/dictionary.json` with this shape:

```json
[
  {"spoken": "whisper bar", "written": "WhisprBar"},
  {"spoken": "wispr flow", "written": "Wispr Flow"}
]
```

- [ ] **Step 2: Write tests**

Cover:

- Missing file returns empty entries.
- Invalid JSON logs and returns empty entries.
- Case-insensitive whole-phrase replacement.
- Longer phrases win before shorter phrases.
- Hits are returned for history/debug metadata.

- [ ] **Step 3: Implement loader and applier**

Implement these exact public functions:

```python
load_dictionary(path: Optional[Path] = None) -> List[DictionaryEntry]
apply_dictionary(text: str, entries: Sequence[DictionaryEntry]) -> Tuple[str, Tuple[str, ...]]
```

- [ ] **Step 4: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_dictionary.py -v
git add whisprbar/flow/dictionary.py tests/test_flow_dictionary.py
git commit -m "feat: add flow dictionary corrections"
```

---

## Task 7: Snippets

**Files:**
- Create: `whisprbar/flow/snippets.py`
- Create: `tests/test_flow_snippets.py`

- [ ] **Step 1: Define storage**

Use `~/.config/whisprbar/snippets.json`:

```json
[
  {"trigger": "my email signature", "text": "Best regards,\nRik"},
  {"trigger": "meeting link", "text": "https://example.test/meeting"}
]
```

- [ ] **Step 2: Write tests**

Cover:

- Missing/invalid file behavior.
- Exact trigger replacement inside a longer sentence.
- Trigger-only match ignores trailing punctuation.
- Dictionary and snippets reject ambiguous duplicate triggers in validation helper.
- Snippet hits are returned.

- [ ] **Step 3: Implement loader, validator, and applier**

Implement these exact public functions:

```python
load_snippets(path: Optional[Path] = None) -> List[Snippet]
validate_snippets(snippets: Sequence[Snippet]) -> Tuple[Snippet, ...]
apply_snippets(text: str, snippets: Sequence[Snippet]) -> Tuple[str, Tuple[str, ...]]
```

- [ ] **Step 4: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_snippets.py -v
git add whisprbar/flow/snippets.py tests/test_flow_snippets.py
git commit -m "feat: add spoken snippet expansion"
```

---

## Task 8: Voice Command Detection

**Files:**
- Create: `whisprbar/flow/commands.py`
- Create: `tests/test_flow_commands.py`

- [ ] **Step 1: Define initial commands**

Supported command utterances:

- German:
  - `mach das professioneller`
  - `mach das kürzer`
  - `formatiere das als liste`
  - `übersetze das ins englische`
  - `nur in die zwischenablage`
- English:
  - `make this more professional`
  - `make this shorter`
  - `format this as a list`
  - `translate this to english`
  - `clipboard only`

- [ ] **Step 2: Write tests**

Cover:

- Command-only dictation creates a command result and no literal pasted command.
- Dictation text plus command suffix strips the command and applies command metadata.
- Non-command text is left unchanged.
- Commands are disabled when `flow_command_mode_enabled` is false.

- [ ] **Step 3: Implement command parser**

Implement this exact public function:

```python
detect_command(text: str, language: str, enabled: bool = True) -> CommandDetection
```

Return cleaned text, command id, rewrite mode, and paste policy override.

- [ ] **Step 4: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_commands.py -v
git add whisprbar/flow/commands.py tests/test_flow_commands.py
git commit -m "feat: detect flow voice commands"
```

---

## Task 9: Rewrite Provider

**Files:**
- Create: `whisprbar/flow/rewrite.py`
- Create: `tests/test_flow_rewrite.py`

- [ ] **Step 1: Write no-op provider tests**

Cover:

- Provider `none` returns original text and status `not_requested`.
- Empty text never calls a provider.
- Provider exceptions return original text and status `failed`.
- Timeout returns original text and status `timeout`.

- [ ] **Step 2: Define prompt contract**

The prompt must include:

- Language.
- Profile style.
- User command/rewrite mode.
- Active app class/title if context awareness is enabled.
- Dictionary terms as must-preserve spellings.
- Instruction to return only final text.

- [ ] **Step 3: Implement OpenAI-compatible provider**

Read endpoint/key from env/config in this order:

- `WHISPRBAR_FLOW_REWRITE_BASE_URL`
- `OPENAI_BASE_URL`
- default OpenAI API base URL
- `WHISPRBAR_FLOW_REWRITE_API_KEY`
- `OPENAI_API_KEY`

Use `cfg["flow_rewrite_model"]` and timeout from config. If key/model is missing, return original text with status `not_configured`.

- [ ] **Step 4: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_rewrite.py -v
git add whisprbar/flow/rewrite.py tests/test_flow_rewrite.py
git commit -m "feat: add optional flow rewrite provider"
```

---

## Task 10: Flow Pipeline Orchestration

**Files:**
- Create: `whisprbar/flow/pipeline.py`
- Create: `tests/test_flow_pipeline.py`

- [ ] **Step 1: Write pipeline tests**

Cover:

- Flow disabled returns existing postprocessed text behavior.
- Dictionary runs before snippets for corrections.
- Snippets run before rewrite so inserted text can be preserved.
- Command detection can override rewrite mode.
- Rewrite disabled keeps deterministic local final text.
- Rewrite failure keeps local final text.
- Output metadata contains profile, context, dictionary hits, snippet hits, command, rewrite status.

- [ ] **Step 2: Implement `process_flow_text()`**

Signature:

```python
process_flow_text(raw_text: str, language: str, cfg: dict) -> FlowOutput
```

Order:

1. Detect app context when enabled.
2. Resolve profile.
3. Apply existing postprocess cleanup.
4. Apply dictionary if enabled.
5. Apply snippets if enabled.
6. Detect command if enabled.
7. Rewrite if enabled, configured, and profile/command asks for it.
8. Return `FlowOutput`.

- [ ] **Step 3: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_flow_pipeline.py -v
git add whisprbar/flow/pipeline.py tests/test_flow_pipeline.py
git commit -m "feat: add flow text pipeline"
```

---

## Task 11: Main App Integration

**Files:**
- Modify: `whisprbar/main.py`
- Modify: `whisprbar/paste.py`
- Modify: `whisprbar/utils.py`
- Create/Modify: `tests/test_main_flow_integration.py`
- Modify: `tests/test_paste.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1: Write integration tests**

Cover:

- When `flow_mode_enabled` is false, `main.py` writes/pastes the old text path.
- When enabled, `process_flow_text()` output final text is written to history and pasted.
- Raw transcript is preserved in history metadata.
- Profile paste override changes paste sequence for one operation without mutating global `cfg`.
- Clipboard-only command skips key injection.

- [ ] **Step 2: Extend history metadata**

Change `write_history(text, duration, word_count, metadata=None)` and preserve backwards compatibility for callers with three arguments.

- [ ] **Step 3: Extend paste API**

Add optional policy argument:

```python
perform_auto_paste(text: str, policy: Optional[PastePolicy] = None) -> None
```

The policy can override sequence, add-space, add-newline, and clipboard-only behavior for that paste only.

- [ ] **Step 4: Wire pipeline into `main.py`**

Replace direct handling after `transcribe_audio()`:

- Raw `text` remains for debug.
- `flow_output = process_flow_text(text, cfg.get("language", "de"), cfg)`.
- Display/paste/history use `flow_output.final_text`.
- History metadata includes `flow_output.metadata`.
- Notifications use final text.

- [ ] **Step 5: Run focused tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_main_flow_integration.py tests/test_paste.py tests/test_utils.py -v
git add whisprbar/main.py whisprbar/paste.py whisprbar/utils.py tests/test_main_flow_integration.py tests/test_paste.py tests/test_utils.py
git commit -m "feat: integrate flow pipeline into dictation path"
```

---

## Task 12: Settings UI

**Files:**
- Modify: `whisprbar/ui/settings.py`
- Create: `tests/test_settings_flow_config.py` if practical without GTK runtime, otherwise document manual test steps in `docs/superpowers/plans/2026-04-29-wispr-flow-parity.md` completion notes.

- [ ] **Step 1: Add Flow tab**

Add a `Flow` tab with:

- Flow Mode switch.
- Context Awareness switch.
- Dictionary switch.
- Snippets switch.
- Command Mode switch.
- Rewrite switch.
- Rewrite Provider combo: None, OpenAI-compatible.
- Rewrite Model text field.
- Rewrite Timeout spin control.
- Default Profile combo.

- [ ] **Step 2: Add dictionary/snippet file shortcuts**

Add buttons:

- Open Dictionary File
- Open Snippets File

If file is missing, create starter JSON with examples and open it in the default editor.

- [ ] **Step 3: Persist config**

Wire save path to existing `on_save()` behavior and keep hotkey/settings behavior unchanged.

- [ ] **Step 4: Manual UI verification**

Run:

```bash
WHISPRBAR_DEBUG=1 /home/rik/WhisprBar/.venv/bin/python whisprbar.py
```

Open Settings from tray or F10. Verify the Flow tab opens, saves values, and restart preserves values in `~/.config/whisprbar.json`.

- [ ] **Step 5: Commit**

```bash
git add whisprbar/ui/settings.py tests/test_settings_flow_config.py
git commit -m "feat: add flow settings"
```

If no GTK-safe automated test is added, omit `tests/test_settings_flow_config.py` from `git add` and include the manual verification evidence in the commit body.

---

## Task 13: History UI Metadata

**Files:**
- Modify: `whisprbar/ui/history.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1: Write history metadata tests**

Cover:

- Old JSONL entries without metadata still read.
- New entries preserve raw text, profile id, command, rewrite status, dictionary hits, and snippet hits.

- [ ] **Step 2: Update history viewer**

Show final text as the main entry. Add compact metadata line when available:

```text
Flow: email | rewrite: applied | command: professional
```

Do not show raw transcript by default in the compact list.

- [ ] **Step 3: Run tests and commit**

```bash
/home/rik/WhisprBar/.venv/bin/pytest tests/test_utils.py -v
git add whisprbar/ui/history.py tests/test_utils.py
git commit -m "feat: show flow metadata in history"
```

---

## Task 14: Documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README**

Add a Flow Mode section:

- What it does.
- How it differs from Wispr Flow.
- Cloud vs offline behavior.
- Dictionary/snippet file locations.
- Linux X11/Wayland caveats.

- [ ] **Step 2: Update CLAUDE.md**

Document:

- `whisprbar/flow/` module responsibilities.
- Flow pipeline order.
- Config keys.
- Test commands.

- [ ] **Step 3: Update CHANGELOG**

Add an Unreleased section with Flow Mode features.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md CHANGELOG.md
git commit -m "docs: document flow mode"
```

---

## Task 15: Full Verification

**Files:**
- No code changes unless verification finds defects.

- [ ] **Step 1: Run full automated tests**

```bash
/home/rik/WhisprBar/.venv/bin/pytest
```

Expected: all tests pass. No known baseline failure may remain.

- [ ] **Step 2: Run import sanity**

```bash
/home/rik/WhisprBar/.venv/bin/python -c "from whisprbar.flow.pipeline import process_flow_text; from whisprbar import config, audio, transcription"
```

Expected: no output, exit code 0.

- [ ] **Step 3: Run diagnostics**

```bash
/home/rik/WhisprBar/.venv/bin/python whisprbar.py --diagnose
```

Expected: diagnostics completes. Backend warnings are acceptable if API keys are intentionally missing.

- [ ] **Step 4: Run dry install check**

```bash
./install.sh --dry-run
```

Expected: no install script regression.

- [ ] **Step 5: Manual X11 paste test**

On the Linux Mint desktop:

1. Start app with `WHISPRBAR_DEBUG=1`.
2. Open a text editor.
3. Dictate a normal sentence with Flow Mode off. Verify old behavior.
4. Enable Flow Mode, dictionary, snippets.
5. Dictate a phrase containing a dictionary entry and snippet trigger.
6. Verify final inserted text, history entry, and no duplicate paste.

- [ ] **Step 6: Manual profile test**

Verify at least:

- Terminal gets `ctrl_shift_v` or clipboard-safe behavior.
- Editor profile does not AI-rewrite code-like text by default.
- Email/chat/notes profiles select expected profile metadata.

- [ ] **Step 7: Manual rewrite failure test**

Set provider to `openai_compatible` without a valid key. Dictate text. Expected: local final text still pastes, rewrite status says `not_configured` or `failed`, no data loss.

- [ ] **Step 8: Final review**

Run:

```bash
git status --short
git log --oneline main..HEAD
git diff --stat main...HEAD
```

Expected: all implementation changes are committed on `codex/wispr-flow-parity`; no accidental main-branch pollution.

---

## Rollout Strategy

1. Keep `flow_mode_enabled` default `False` until all tests and manual checks pass.
2. Merge the branch only after baseline, focused, full, and manual desktop checks are complete.
3. After merge, enable Flow Mode manually on the local machine and dogfood it for normal German/English dictation.
4. If stable, consider flipping local default config to enabled. Do not flip repository default until enough usage confirms no regression for existing users.

## Acceptance Criteria

- Branch remains separate from `main`.
- Full pytest suite passes.
- Existing non-Flow dictation behavior is unchanged with Flow Mode disabled.
- Flow Mode can:
  - apply dictionary corrections,
  - expand snippets,
  - detect app context on X11,
  - select app profiles,
  - execute basic spoken commands,
  - optionally rewrite with an OpenAI-compatible provider,
  - preserve raw and final text in history metadata,
  - degrade gracefully when rewrite/context/paste support is unavailable.
- Manual desktop verification confirms real text insertion works in at least a text editor, terminal, browser field, and notes/editor app.
