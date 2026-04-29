# Flow Bar UX Design

Date: 2026-04-29
Branch: `codex/wispr-flow-parity`

## Goal

Flow Mode should feel visually distinct from classic WhisprBar while keeping the existing dictation path stable. The first UX pass will replace the current recording indicator only when `flow_mode_enabled` is true.

The chosen direction is **A2.1 Soft Dark**: a compact floating pill with a softer dark background, subtle blue/green accents, clear state labels, a timer during listening, and a small hotkey hint.

## Non-Goals

- Do not redesign the settings window.
- Do not add large live transcript text to the bar.
- Do not change transcription backends, VAD, or audio capture behavior.
- Do not replace the existing classic indicator when Flow Mode is off.
- Do not expand spoken command behavior in this pass.

## User Experience

When Flow Mode is enabled, the bar should be compact, calm, and visibly different from the old red/orange WhisprBar indicator.

States:

- `Listening`: dark soft pill, subtle wave/line animation, timer, hotkey label such as `Right Ctrl`
- `Processing`: short label and calm progress animation while audio is prepared
- `Transcribing`: short label and progress animation while backend transcription runs
- `Rewriting`: shown only when Flow rewrite is enabled and a rewrite pass is requested
- `Pasting`: short label while paste policy is applied
- `Done`: brief success state with word count
- `Error`: brief readable error state

The bar should avoid looking like a modal or command palette. It should stay lightweight enough to sit over any app without blocking work.

## Architecture

Extend `whisprbar/ui/recording_indicator.py` rather than creating a new UI subsystem.

The existing `RecordingIndicator` will choose a renderer based on configuration:

- Classic renderer for `flow_mode_enabled == False`
- Flow renderer for `flow_mode_enabled == True`

This keeps the public API stable:

- `show_recording_indicator(phase, cfg, info="")`
- `hide_recording_indicator()`
- `set_recording_indicator_audio_level(level)`
- `reset_recording_indicator()`

The Flow renderer will reuse the same GTK popup, drawing area, animation timer, opacity, positioning, and drag behavior. Only drawing/layout changes.

## Components

### Phase Labels

Add a small internal mapping from phase to Flow label:

- `recording` -> `Listening`
- `processing` -> `Processing`
- `transcribing` -> `Transcribing`
- `pasting` -> `Pasting`
- `complete` -> `Done`
- `error` -> `Error`

Add a new UI phase for rewrite if needed:

- `rewriting` -> `Rewriting`

### Hotkey Label

The bar should display the active recording binding in human-readable form, using `hotkey_to_label()`. For the current local config, `CTRL_R` should display as `Right Ctrl`.

If the label cannot be resolved, hide the hint rather than showing a broken string.

### Flow Drawing

The Flow renderer draws:

- rounded soft-dark pill background
- small accent badge or accent line
- subtle wave/line animation using existing audio-level smoothing
- status label
- timer for `Listening`
- hotkey hint for `Listening`
- compact status icon or dot for non-listening phases

The visual palette should be dark neutral with restrained blue/green accents. Avoid returning to the old red/orange dominant recording palette.

## Data Flow

1. `main.py` calls `show_recording_indicator()` with the existing phases.
2. `RecordingIndicator` reads `cfg["flow_mode_enabled"]`.
3. If Flow Mode is active, `_on_draw()` routes to Flow drawing helpers.
4. Audio levels continue to arrive through `set_audio_level()`.
5. Completion and error states keep the existing auto-hide behavior.

For the rewrite state, `main.py` should show `PHASE_REWRITING` only when a rewrite pass is actually requested. If that proves too invasive for this pass, the state can be omitted initially while preserving the drawing support.

## Error Handling

- If GTK is unavailable, behavior remains unchanged: no indicator is shown.
- If hotkey label resolution fails, omit the hotkey text.
- If Flow Mode is disabled, classic rendering must be byte-for-byte compatible in behavior even if helper functions are reorganized.
- If a new rewrite phase is unsupported by older paths, it must degrade to a generic processing/transcribing visual.

## Testing

Automated tests:

- Flow label mapping resolves `CTRL_R` to `Right Ctrl`.
- Flow Mode chooses the Flow drawing path while non-Flow mode keeps classic behavior.
- New rewrite phase constants do not break existing phase handling.
- Existing full test suite remains green.

Manual tests:

- Start local branch app with Flow Mode enabled.
- Dictate using the current `Right Ctrl` activation key.
- Verify the bar visually differs from the classic indicator.
- Verify `Listening`, `Processing`, `Transcribing`, `Pasting`, and `Done` are visible in the normal path.
- Verify Flow Mode disabled returns to the old indicator style.

## Acceptance Criteria

- Flow Mode has a visibly distinct Soft Dark compact bar.
- The current activation key is visible during listening.
- Existing recording and paste behavior is not changed.
- Existing classic indicator still works when Flow Mode is off.
- Full pytest suite passes.
