# Whispr Flow Simple Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WhisprBar feel like a simple Wispr-Flow-style dictation product: hold hotkey, speak, release, get clean text, with settings grouped around normal user intent.

**Architecture:** Keep the existing WebKit settings window as the production settings entrypoint. Reorganize its generated HTML into Flow, Words, Shortcuts, History, and Advanced pages without changing the config persistence contract. Fix the existing Flow-bar hotkey label regression first so the baseline can become green.

**Tech Stack:** Python 3.12, pytest, WebKit-generated HTML/CSS/JS in `whisprbar/ui/settings_webview.py`, existing i18n dictionary in `whisprbar/i18n.py`.

---

## File Structure

- Modify `whisprbar/hotkeys.py`: format side-specific modifier token strings before consulting runtime pynput maps.
- Modify `tests/test_hotkeys.py`: add a core hotkey-label regression test for direct token strings.
- Keep `tests/test_recording_indicator_flow.py`: existing failing test proves the recording indicator uses the core label behavior.
- Modify `whisprbar/i18n.py`: add simple product-facing page labels for Words, Shortcuts, History, and Flow test copy in German and English.
- Modify `whisprbar/ui/settings_webview.py`: make Flow the first settings page; split everyday pages into Flow, Words, Shortcuts, History; move technical controls and voice-command reference to Advanced; add a Flow test button that previews the Flow bar and tells the user to try the recording hotkey.
- Modify `tests/test_settings_webview.py`: update settings-shell tests and add focused tests for the simple information architecture and Flow test affordance.

### Task 1: Fix Flow-Bar Hotkey Labels

**Files:**
- Modify: `tests/test_hotkeys.py`
- Modify: `whisprbar/hotkeys.py`
- Verify: `tests/test_recording_indicator_flow.py`

- [ ] **Step 1: Write the failing hotkey label test**

Add this test after `test_hotkey_to_label()` in `tests/test_hotkeys.py`:

```python
@pytest.mark.unit
def test_key_to_label_formats_side_specific_token_string():
    """Side-specific modifier tokens should be readable without pynput maps."""
    assert hotkeys.key_to_label("CTRL_R") == "Right Ctrl"
    assert hotkeys.key_to_label("RIGHT_CTRL") == "Right Ctrl"
    assert hotkeys.key_to_label("ALT_L") == "Left Alt"
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_hotkeys.py::test_key_to_label_formats_side_specific_token_string -q
```

Expected: FAIL because `"CTRL_R"` currently formats as `"CTRL_R"` when `SPECIAL_KEY_MAP` does not contain side-specific runtime keys.

- [ ] **Step 3: Implement minimal label normalization**

In `whisprbar/hotkeys.py`, replace the direct string branch inside `key_to_label()` with:

```python
    # Handle direct token strings (used by tray state for configured hotkeys)
    if isinstance(key_obj, str):
        raw_token = key_obj.strip().upper().replace("-", "_").replace(" ", "_")
        raw_token = SPECIAL_KEY_ALIASES.get(raw_token, raw_token)
        if raw_token in SPECIAL_KEY_LABELS:
            return SPECIAL_KEY_LABELS[raw_token]
        token = normalize_key_token(key_obj)
        if token in SPECIAL_KEY_LABELS:
            return SPECIAL_KEY_LABELS[token]
        return token or key_obj.strip().upper() or "F9"
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_hotkeys.py::test_key_to_label_formats_side_specific_token_string tests/test_recording_indicator_flow.py::test_flow_hotkey_label_uses_toggle_binding -q
```

Expected: PASS.

- [ ] **Step 5: Run broader hotkey/indicator tests**

Run:

```bash
.venv/bin/pytest tests/test_hotkeys.py tests/test_recording_indicator_flow.py -q
```

Expected: PASS or skips only for environment-dependent hotkey tests.

### Task 2: Add Simple Settings Vocabulary

**Files:**
- Modify: `whisprbar/i18n.py`
- Modify: `tests/test_settings_webview.py`

- [ ] **Step 1: Write the failing vocabulary/IA test**

Add this test after `test_generate_settings_html_uses_german_ui_when_language_is_german()` in `tests/test_settings_webview.py`:

```python
def test_generate_settings_html_uses_simple_flow_navigation():
    html = generate_settings_html(
        {
            "language": "en",
            "flow_mode_enabled": True,
            "flow_preferred_languages": ["de", "en"],
        },
        dictionary_entries=[],
        snippets=[],
        transcript_stats={"total": 7},
    )

    nav_flow = html.index('data-page="flow"')
    nav_words = html.index('data-page="words"')
    nav_shortcuts = html.index('data-page="shortcuts"')
    nav_history = html.index('data-page="history"')
    nav_advanced = html.index('data-page="advanced"')

    assert nav_flow < nav_words < nav_shortcuts < nav_history < nav_advanced
    assert 'data-page="flow" aria-current="page"' in html
    assert 'data-page-id="flow"' in html
    assert 'class="wb-page active" data-page-id="flow"' in html
    assert 'data-page-id="words"' in html
    assert 'data-page-id="shortcuts"' in html
    assert 'data-page-id="history"' in html
    assert "Words" in html
    assert "Shortcuts" in html
    assert "History" in html
    assert "Recording" not in html.split('<nav class="wb-nav"', 1)[1].split("</nav>", 1)[0]
    assert "Transcription" not in html.split('<nav class="wb-nav"', 1)[1].split("</nav>", 1)[0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_settings_webview.py::test_generate_settings_html_uses_simple_flow_navigation -q
```

Expected: FAIL because the current sidebar starts with General, Recording, Transcription, and does not contain Words, Shortcuts, or History pages.

- [ ] **Step 3: Add i18n keys**

In the German dictionary near the existing `settings.analysis` and `settings.privacy` keys in `whisprbar/i18n.py`, add:

```python
        "settings.words": "Wörter",
        "settings.shortcuts": "Kurzbefehle",
        "settings.history": "Verlauf",
        "settings.words_desc": "Eigene Wörter und Textbausteine für saubere Diktate.",
        "settings.shortcuts_desc": "Tasten für Aufnahme, Abbruch und schnelle Aktionen.",
        "settings.history_desc": "Letzte Diktate, Speicherung und lokale Analyse.",
        "settings.flow_test": "Diktat testen",
        "settings.flow_test_desc": "Zeigt die Flow-Leiste und erinnert dich an den Aufnahme-Hotkey.",
        "settings.flow_test_button": "Flow-Leiste testen",
        "settings.flow_test_ready": "Flow-Leiste sichtbar. Halte jetzt deinen Aufnahme-Hotkey zum echten Testen.",
        "settings.everyday": "Alltag",
        "settings.personalization": "Personalisierung",
```

In the English dictionary near the matching keys, add:

```python
        "settings.words": "Words",
        "settings.shortcuts": "Shortcuts",
        "settings.history": "History",
        "settings.words_desc": "Custom words and snippets for clean dictation.",
        "settings.shortcuts_desc": "Keys for recording, canceling, and quick actions.",
        "settings.history_desc": "Recent dictations, storage, and local analysis.",
        "settings.flow_test": "Test dictation",
        "settings.flow_test_desc": "Shows the Flow bar and reminds you of the recording hotkey.",
        "settings.flow_test_button": "Test Flow bar",
        "settings.flow_test_ready": "Flow bar is visible. Hold your recording hotkey now for a real test.",
        "settings.everyday": "Everyday",
        "settings.personalization": "Personalization",
```

- [ ] **Step 4: Run the vocabulary/IA test again**

Run:

```bash
.venv/bin/pytest tests/test_settings_webview.py::test_generate_settings_html_uses_simple_flow_navigation -q
```

Expected: still FAIL because the HTML structure has not moved yet, but no untranslated `settings.words` or `settings.shortcuts` text should appear once Task 3 is implemented.

### Task 3: Reorganize Settings Into Flow, Words, Shortcuts, History, Advanced

**Files:**
- Modify: `whisprbar/ui/settings_webview.py`
- Modify: `tests/test_settings_webview.py`

- [ ] **Step 1: Update existing shell tests for the new first page**

In `tests/test_settings_webview.py`, change `test_generate_settings_html_contains_selected_settings_shell()` assertions from:

```python
    assert "data-page=\"general\"" in html
    assert "data-page=\"flow\"" in html
```

to:

```python
    assert "data-page=\"flow\"" in html
    assert "data-page=\"words\"" in html
    assert "data-page=\"shortcuts\"" in html
    assert "data-page=\"history\"" in html
    assert "data-page=\"advanced\"" in html
```

In `test_generate_settings_html_uses_english_ui_when_language_is_english()`, replace:

```python
    assert "Recording" in html
    assert "Transcription" in html
    assert "Privacy" in html
```

with:

```python
    assert "Flow" in html
    assert "Words" in html
    assert "Shortcuts" in html
    assert "History" in html
```

In `test_generate_settings_html_uses_german_ui_when_language_is_german()`, replace:

```python
    assert "Aufnahme" in html
    assert "Transkription" in html
    assert "Datenschutz" in html
```

with:

```python
    assert "Flow" in html
    assert "Wörter" in html
    assert "Kurzbefehle" in html
    assert "Verlauf" in html
```

- [ ] **Step 2: Run updated settings tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_settings_webview.py::test_generate_settings_html_contains_selected_settings_shell tests/test_settings_webview.py::test_generate_settings_html_uses_english_ui_when_language_is_english tests/test_settings_webview.py::test_generate_settings_html_uses_german_ui_when_language_is_german tests/test_settings_webview.py::test_generate_settings_html_uses_simple_flow_navigation -q
```

Expected: FAIL because the generator still emits the old page structure.

- [ ] **Step 3: Update command and analysis tests to match the simpler page model**

In `test_generate_settings_html_shows_voice_commands_from_command_specs()`, replace:

```python
    assert "data-page=\"voice-commands\"" in html
    assert "data-page-id=\"voice-commands\"" in html
```

with:

```python
    assert "data-page=\"voice-commands\"" not in html
    assert "data-page-id=\"voice-commands\"" not in html
    assert "data-page-id=\"advanced\"" in html
```

Keep the existing assertions for `"Sprachbefehle"`, `"KI-Bearbeitung"`, `"Einfüge- und Steuerbefehle"`, `"correct my english"`, `"mach das menschlicher"`, `"drücke enter"`, `"Nutzt AI-Umschreiben"`, and `"Keine KI"` so command content is still verified.

In `test_generate_settings_html_shows_analysis_database_stats()`, replace:

```python
    assert 'data-page="analysis"' in html
    assert 'data-page-id="analysis"' in html
    assert "Analyse" in html
```

with:

```python
    assert 'data-page="analysis"' not in html
    assert 'data-page-id="analysis"' not in html
    assert 'data-page-id="history"' in html
    assert "History" in html or "Verlauf" in html
```

Keep the existing assertions for `"153"`, `"Live gespeichert"`, `"Alter Verlauf"`, `"CopyQ-Import"`, and the database path.

In `test_generate_settings_html_preserves_empty_transcript_stats()`, replace:

```python
    assert 'data-page="analysis"' in html
```

with:

```python
    assert 'data-page-id="history"' in html
```

- [ ] **Step 4: Split Words and History rows**

Replace the current `privacy_rows = (` block with two focused row groups:

```python
    words_toggle_rows = (
        _switch(
            "flow_dictionary_enabled",
            tr("settings.dictionary"),
            tr("setting.dictionary_desc"),
            config.get("flow_dictionary_enabled", True),
        )
        + _switch(
            "flow_snippets_enabled",
            tr("settings.snippets"),
            tr("setting.snippets_desc"),
            config.get("flow_snippets_enabled", True),
        )
    )

    history_storage_rows = (
        _select(
            "flow_history_storage",
            tr("setting.history_storage"),
            tr("setting.history_storage_desc"),
            [
                ("normal", tr("option.normal")),
                ("auto_delete", tr("option.auto_delete_24h")),
                ("never", tr("option.never_store")),
            ],
            config.get("flow_history_storage", "normal"),
        )
        + _number_field(
            "flow_history_auto_delete_hours",
            tr("setting.auto_delete_hours"),
            tr("setting.auto_delete_hours_desc"),
            config.get("flow_history_auto_delete_hours", 24),
            minimum=1,
            maximum=720,
            step=1,
            unit="h",
            visible_when="flow_history_storage=auto_delete",
        )
    )
```

- [ ] **Step 5: Add a Flow test row**

In `whisprbar/ui/settings_webview.py`, after `flow_controls_rows` is defined, add:

```python
    flow_test_rows = """
      <div class="wb-row">
        <span class="wb-row-label">
          <b>{flow_test}</b>
          <span>{flow_test_desc}</span>
        </span>
        <button class="wb-button compact" type="button" data-flow-test>{flow_test_button}</button>
      </div>
    """.format(
        flow_test=escape(tr("settings.flow_test")),
        flow_test_desc=escape(tr("settings.flow_test_desc")),
        flow_test_button=escape(tr("settings.flow_test_button")),
    )
```

- [ ] **Step 6: Replace the sidebar navigation**

In the `<nav class="wb-nav">` block inside `generate_settings_html()`, replace the old buttons with:

```python
        <button class="wb-nav-item active" type="button" data-page="flow" aria-current="page"><span class="wb-icon"></span><span>{escape(tr("settings.flow"))}</span><span class="wb-count">4</span></button>
        <button class="wb-nav-item" type="button" data-page="words"><span class="wb-icon"></span><span>{escape(tr("settings.words"))}</span><span class="wb-count">2</span></button>
        <button class="wb-nav-item" type="button" data-page="shortcuts"><span class="wb-icon"></span><span>{escape(tr("settings.shortcuts"))}</span><span class="wb-count">1</span></button>
        <button class="wb-nav-item" type="button" data-page="history"><span class="wb-icon"></span><span>{escape(tr("settings.history"))}</span><span class="wb-count">{escape(_stat_value(transcript_stats.get("total", 0)))}</span></button>
        <button class="wb-nav-item" type="button" data-page="advanced"><span class="wb-icon"></span><span>{escape(tr("settings.advanced"))}</span><span class="wb-count">8</span></button>
```

- [ ] **Step 7: Replace the page sections**

Inside `<main class="wb-main">`, replace the old General, Recording, Transcription, Flow, Voice commands, Privacy, Analysis, and Advanced sections with these five pages:

```python
      <section class="wb-page active" data-page-id="flow">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.flow"))}</h2><p>{escape(tr("settings.flow_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.flow_ready"))}</span>
        </div>
        <div class="wb-layout">
          <div class="wb-stack">
            {_section(tr("settings.flow_mode"), tr("settings.everyday"), flow_primary_rows, hero=True)}
            {_section(tr("settings.profiles"), tr("settings.context"), flow_controls_rows)}
          </div>
          <div class="wb-stack">
            {_section(tr("settings.flow_test"), tr("settings.local_preview"), flow_test_rows, hero=True)}
          </div>
        </div>
      </section>

      <section class="wb-page" data-page-id="words">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.words"))}</h2><p>{escape(tr("settings.words_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.personalization"))}</span>
        </div>
        <div class="wb-layout">
          <div class="wb-stack">
            {_section(tr("settings.personalization"), tr("settings.history_local_helpers"), words_toggle_rows, hero=True)}
          </div>
          <div class="wb-stack">
            <section class="wb-section">
              <div class="wb-section-head"><h3>{escape(tr("settings.dictionary"))}</h3><span>{escape(tr("settings.spoken_written"))}</span></div>
              <div class="wb-table" data-table="dictionary">
                <div class="wb-table-head"><span>{escape(tr("settings.recognized"))}</span><span>{escape(tr("settings.insert_as"))}</span><span></span></div>
                {dictionary_rows}
              </div>
              <div class="wb-table-actions"><button class="wb-button compact" type="button" data-add-row="dictionary">{escape(tr("settings.add_dictionary_row"))}</button></div>
            </section>
            <section class="wb-section">
              <div class="wb-section-head"><h3>{escape(tr("settings.snippets"))}</h3><span>{escape(tr("settings.trigger_text"))}</span></div>
              <div class="wb-table" data-table="snippets">
                <div class="wb-table-head"><span>{escape(tr("settings.trigger"))}</span><span>{escape(tr("settings.text"))}</span><span></span></div>
                {snippet_rows}
              </div>
              <div class="wb-table-actions"><button class="wb-button compact" type="button" data-add-row="snippets">{escape(tr("settings.add_snippet_row"))}</button></div>
            </section>
          </div>
        </div>
      </section>

      <section class="wb-page" data-page-id="shortcuts">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.shortcuts"))}</h2><p>{escape(tr("settings.shortcuts_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.hotkeys"))}</span>
        </div>
        <div class="wb-stack">
          {_section(tr("settings.hotkeys"), tr("settings.all_actions"), hotkey_rows, hero=True)}
        </div>
      </section>

      <section class="wb-page" data-page-id="history">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.history"))}</h2><p>{escape(tr("settings.history_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.local_database"))}</span>
        </div>
        <div class="wb-stack">
          {_section(tr("settings.storage"), tr("settings.history_local_helpers"), history_storage_rows, hero=True)}
          <section class="wb-section wb-hero">
            <div class="wb-section-head"><h3>{escape(tr("settings.analysis_collection"))}</h3><span>{escape(tr("settings.analysis_collection_desc"))}</span></div>
            <div class="wb-stat-list">{analysis_rows}</div>
          </section>
          <section class="wb-section"><div class="wb-note">{escape(tr("settings.analysis_note"))}</div></section>
        </div>
      </section>

      <section class="wb-page" data-page-id="advanced">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.advanced"))}</h2><p>{escape(tr("settings.advanced_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.expert"))}</span>
        </div>
        <div class="wb-stack">
          {_section(tr("settings.app_behavior"), tr("settings.daily_use"), general_rows, hero=True)}
          {_section(tr("settings.capture"), tr("settings.input_feedback"), recording_rows)}
          {_section(tr("settings.engine"), tr("setting.backend"), transcription_rows)}
          {_section(tr("settings.api_keys"), tr("settings.local_env_file"), api_rows)}
          {_section(tr("settings.post_processing"), tr("settings.cleanup"), postprocess_rows)}
          {_section(tr("settings.ai_rewrite"), tr("settings.optional"), rewrite_rows)}
          {_section(tr("settings.silence_handling"), tr("settings.expert_vad"), vad_rows)}
          {_section(tr("settings.runtime"), tr("settings.technical"), advanced_rows)}
          {_section(tr("settings.indicator"), tr("settings.flow_bar"), indicator_rows)}
          {_section(tr("settings.overlay"), tr("settings.floating_transcript"), overlay_rows)}
          <section class="wb-section">
            <div class="wb-section-head"><h3>{escape(tr("settings.ai_commands"))}</h3><span>{escape(tr("settings.uses_ai_rewrite"))}</span></div>
            <div class="wb-command-list">
              <div class="wb-command-head"><span>{escape(tr("settings.command_phrase"))}</span><span>{escape(tr("settings.command_action"))}</span><span>{escape(tr("settings.command_requirement"))}</span></div>
              {ai_command_rows}
            </div>
          </section>
          <section class="wb-section">
            <div class="wb-section-head"><h3>{escape(tr("settings.paste_commands"))}</h3><span>{escape(tr("settings.no_ai"))}</span></div>
            <div class="wb-command-list">
              <div class="wb-command-head"><span>{escape(tr("settings.command_phrase"))}</span><span>{escape(tr("settings.command_action"))}</span><span>{escape(tr("settings.command_requirement"))}</span></div>
              {local_command_rows}
            </div>
          </section>
          <section class="wb-section"><div class="wb-note">{escape(tr("settings.voice_commands_note"))}</div></section>
          <section class="wb-section"><div class="wb-note">{escape(tr("settings.advanced_note"))}</div></section>
        </div>
      </section>
```

- [ ] **Step 8: Run settings tests**

Run:

```bash
.venv/bin/pytest tests/test_settings_webview.py -q
```

Expected: PASS. The settings tests should verify that command-related rows still render inside `advanced` and analysis stats still render inside `history`, without standalone `voice-commands` or `analysis` pages.

### Task 4: Wire the Flow Test Button

**Files:**
- Modify: `tests/test_settings_webview.py`
- Modify: `whisprbar/ui/settings_webview.py`

- [ ] **Step 1: Write the failing Flow test affordance test**

Add this test near the dynamic visibility tests in `tests/test_settings_webview.py`:

```python
def test_generate_settings_html_wires_flow_test_button_to_preview_message():
    html = generate_settings_html(
        {"language": "en", "flow_mode_enabled": True},
        dictionary_entries=[],
        snippets=[],
    )

    assert "data-flow-test" in html
    assert "Test Flow bar" in html
    assert "action: 'flow_test'" in html
    assert "settings.flow_test_ready" not in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_settings_webview.py::test_generate_settings_html_wires_flow_test_button_to_preview_message -q
```

Expected: FAIL because there is no `data-flow-test` handler yet.

- [ ] **Step 3: Add JavaScript message handling**

In the document click handler in `generate_settings_html()`, after the capture-hotkey branch, add:

```javascript
    const flowTestButton = event.target.closest('[data-flow-test]');
    if (flowTestButton) {
      postSettingsMessage({ action: 'flow_test', payload: collectPayload() });
      return;
    }
```

- [ ] **Step 4: Add Python message handling**

In `on_settings_message()` in `whisprbar/ui/settings_webview.py`, after the `preview_indicator` branch, add:

```python
        if action == "flow_test":
            payload = data.get("payload") if isinstance(data.get("payload"), Mapping) else {}
            handle_preview_indicator(payload)
            _set_webview_message(webview, t("settings.flow_test_ready", config), "ok")
            return
```

- [ ] **Step 5: Run focused test**

Run:

```bash
.venv/bin/pytest tests/test_settings_webview.py::test_generate_settings_html_wires_flow_test_button_to_preview_message -q
```

Expected: PASS.

### Task 5: Verification and Manual UI Evidence

**Files:**
- Verify modified runtime and tests.
- Write no repository artifact for manual inspection unless the user explicitly asks for one.

- [ ] **Step 1: Run focused test groups**

Run:

```bash
.venv/bin/pytest tests/test_hotkeys.py tests/test_recording_indicator_flow.py tests/test_settings_webview.py -q
```

Expected: PASS or environment-dependent hotkey skips only.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: PASS. The original `CTRL_R`/`Right Ctrl` failure must be gone.

- [ ] **Step 3: Run compile check**

Run:

```bash
.venv/bin/python -m compileall -q whisprbar tests
```

Expected: PASS with no output.

- [ ] **Step 4: Inspect settings HTML without launching the full tray app**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from whisprbar.ui.settings_webview import generate_settings_html

html = generate_settings_html(
    {
        "language": "en",
        "flow_mode_enabled": True,
        "hotkeys": {"toggle_recording": "CTRL_R"},
        "hotkey": "CTRL_R",
    },
    dictionary_entries=[],
    snippets=[],
    transcript_stats={"total": 0},
)
path = Path("/tmp/whisprbar-simple-flow-settings.html")
path.write_text(html, encoding="utf-8")
print(path)
PY
```

Expected: prints `/tmp/whisprbar-simple-flow-settings.html`.

Open the generated file in a browser or in-app browser and confirm:

- the first page is Flow;
- sidebar order is Flow, Words, Shortcuts, History, Advanced;
- technical controls are in Advanced;
- Words contains dictionary and snippets;
- Shortcuts contains hotkeys;
- History contains analysis stats.

- [ ] **Step 5: Record final evidence**

Add final verification results to the closing response:

```text
Focused tests: PASS
Full tests: PASS
Compileall: PASS
Manual/UI inspection: PASS, generated /tmp/whisprbar-simple-flow-settings.html
```
