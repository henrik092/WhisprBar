# Settings UX Redesign Design

Date: 2026-04-29
Branch: `codex/wispr-flow-parity`

## Goal

Redesign the WhisprBar settings window so it feels modern, coherent, and easier to use as Flow Mode grows. The chosen direction is the refined **B** concept: a soft-dark, sidebar-based settings system where every settings page follows the same visual structure, and the Flow page gets richer controls for dictionary, commands, snippets, profiles, and rewrite.

The window should still behave like a practical desktop settings tool. It should not become a marketing page or decorative dashboard.

## Non-Goals

- Do not replace GTK with a web UI in this pass.
- Do not change config keys or storage formats unless required for the UI components.
- Do not redesign the tray menu or recording indicator again.
- Do not add new Flow behavior beyond exposing existing controls more clearly.
- Do not remove the existing settings functionality.

## User Experience

The settings window should use a consistent app-like layout:

- top title bar with `WhisprBar Settings`, `Cancel`, and `Save Changes`
- left sidebar navigation instead of the current tab strip
- right content area with a page title, short description, and grouped controls
- soft-dark visual style matching the new Flow Bar direction
- compact controls that remain readable on normal desktop sizes

Pages:

- `General`: theme, language, hotkeys, auto-paste, notifications
- `Recording`: input device, VAD, noise reduction, audio feedback, recording limits
- `Transcription`: backend, API keys, models, post-processing
- `Flow`: Flow mode, smart formatting, dictionary, snippets, commands, rewrite, profiles
- `Privacy`: history storage, auto-delete, clipboard/history behavior
- `Advanced`: indicator, overlay, chunking, diagnostics-oriented technical settings

Flow should be the strongest page visually, but not the only modern page. All pages should use the same section-row pattern.

## Architecture

Keep the implementation in GTK 3 for compatibility with the current Linux desktop app.

The current `whisprbar/ui/settings.py` is large and should not keep accumulating all UI code in one function. The redesign should introduce small helper builders inside the existing UI package. The first implementation can remain conservative, but the direction should be:

- reusable sidebar/page shell
- reusable section component
- reusable setting row component
- reusable editor-table component for dictionary and snippets

The public entry point remains:

- `open_settings_window(cfg, state, on_save=None)`

This avoids touching tray callbacks and hotkey behavior.

## Components

### Settings Shell

The shell owns:

- GTK window
- title/header row
- sidebar navigation
- stacked content area
- bottom or top-right save/cancel actions

Sidebar navigation should switch pages without losing unsaved field state.

### Setting Sections

Each page contains sections with:

- short heading
- optional small helper text
- rows with label, optional description, and right-aligned control

Rows should support switches, combo boxes, spin buttons, text entries, buttons, sliders, and hotkey capture controls.

### Dictionary Editor

The Flow page includes an editable table backed by `/home/rik/.config/whisprbar/dictionary.json`.

Required behavior:

- load existing `spoken`/`written` entries
- add an empty row
- edit cells inline
- remove selected row
- save non-empty entries only
- preserve the same JSON format used by the Flow pipeline

The existing `Open Dictionary File` fallback may remain, but it should be secondary.

### Snippets Editor

Use the same table pattern as dictionary, but for `/home/rik/.config/whisprbar/snippets.json`.

Required behavior:

- load `trigger`/`text`
- add/edit/remove rows
- save valid rows
- preserve the existing snippets format

If this is too much for the first implementation slice, dictionary should ship first and snippets can follow immediately after.

## Data Flow

1. `open_settings_window()` loads values from `cfg` and the Flow JSON files.
2. UI controls update local unsaved widget state.
3. `Save Changes` validates hotkey conflicts and gathers all page values.
4. Main config values are written through `save_config()`.
5. API keys are written through the existing env file helpers.
6. Dictionary/snippets editors write their JSON files through reusable Flow persistence helpers.
7. Device index and Wayland notices keep existing behavior.
8. The window closes after successful save.

Cancel closes without writing config or JSON editor changes.

## Error Handling

- Invalid dictionary/snippet JSON should not crash settings. Show an empty editor state or fallback row and keep the file-open button available.
- If saving dictionary/snippets fails, notify the user and do not close the settings window.
- Hotkey conflicts keep the current behavior: show notification and block save.
- GTK unavailable behavior remains unchanged.
- Missing optional dependencies should still disable or hide dependent controls as today.

## Visual Rules

- Use a restrained dark neutral base with blue/cyan accents.
- Avoid card-heavy dashboard clutter; cards are for grouped settings and tables only.
- Sidebar labels must be short and scannable.
- Section descriptions should be short and practical.
- Long labels must not overflow; descriptions wrap inside their row.
- Buttons should use concise command labels.
- Keep enough density for a real settings tool.

## Testing

Automated tests:

- dictionary save/load persists non-empty rows and skips incomplete rows
- snippets save/load if snippets editor is implemented
- settings module imports cleanly
- focused Flow pipeline tests still pass after dictionary changes
- full pytest suite passes

Manual tests:

- open settings window from the running app
- navigate all sidebar pages
- edit a normal config setting and verify it persists after save/reopen
- add/edit/remove a dictionary entry from the Flow page
- verify `/home/rik/.config/whisprbar/dictionary.json` changes
- dictate a phrase that uses the new dictionary entry
- cancel after editing and verify no file/config changes are written
- verify hotkey conflict handling still blocks save

## Acceptance Criteria

- Settings window uses the refined B visual direction.
- All existing settings remain reachable.
- Flow page exposes dictionary editing clearly.
- Save/cancel behavior remains predictable.
- Existing WhisprBar runtime behavior is unchanged unless settings are saved.
- Full pytest suite passes.
