"""Experimental WebKit settings window for WhisprBar.

This module is intentionally parallel to the production GTK 3 settings dialog.
It lets us evaluate a more modern HTML/CSS settings surface without changing
the existing save path yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import sys
import threading
from typing import Any, Callable, Iterable, Mapping, Optional

from whisprbar.audio import list_input_devices, update_device_index
from whisprbar.config import get_env_value, save_config, save_env_file_value
from whisprbar.flow.commands import COMMAND_SPECS, CommandSpec
from whisprbar.flow.dictionary import load_dictionary, save_dictionary
from whisprbar.flow.models import DictionaryEntry, Snippet
from whisprbar.flow.snippets import load_snippets, save_snippets
from whisprbar.hotkey_actions import HOTKEY_SETTINGS_LABELS
from whisprbar.hotkeys import cancel_hotkey_capture, capture_hotkey
from whisprbar.i18n import get_language, hotkey_action_labels, t
from whisprbar.paste import PASTE_OPTIONS, is_wayland_session
from whisprbar.ui_hotkeys import (
    build_hotkey_conflict_message,
    build_pending_hotkeys,
    get_hotkey_conflicts_for_actions,
)
from whisprbar.utils import APP_NAME, notify

_settings_webview_window = None
_settings_webview_lock = threading.Lock()


def _present_settings_window(window: object) -> None:
    """Bring the settings window forward without pinning it permanently."""
    try:
        from gi.repository import GLib, Gtk

        if hasattr(window, "set_keep_above"):
            window.set_keep_above(True)
        if hasattr(window, "present_with_time"):
            window.present_with_time(Gtk.get_current_event_time())
        elif hasattr(window, "present"):
            window.present()

        def release_keep_above() -> bool:
            try:
                if hasattr(window, "set_keep_above"):
                    window.set_keep_above(False)
            except Exception:
                pass
            return False

        GLib.timeout_add(600, release_keep_above)
    except Exception:
        try:
            if hasattr(window, "present"):
                window.present()
        except Exception:
            pass


@dataclass(frozen=True)
class SettingsApplyResult:
    """Result for applying a settings payload from the WebKit UI."""

    ok: bool
    message: str = ""


def _checked(value: object) -> str:
    return " checked" if bool(value) else ""


def _option(value: str, label: str, active_value: object) -> str:
    selected = " selected" if str(active_value) == value else ""
    return f'<option value="{escape(value)}"{selected}>{escape(label)}</option>'


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "checked"}
    return bool(value)


def _int_value(value: object, default: int) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _float_value(value: object, default: float, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return default


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _clamp_float(value: float, lower: float, upper: float, digits: int = 2) -> float:
    return round(max(lower, min(upper, value)), digits)


def _setting(settings: Mapping[str, object], key: str, default: object) -> object:
    return settings[key] if key in settings else default


def _switch(name: str, label: str, description: str, active: object) -> str:
    return f"""
      <label class="wb-row">
        <span class="wb-row-label">
          <b>{escape(label)}</b>
          <span>{escape(description)}</span>
        </span>
        <input class="wb-switch-input" type="checkbox" name="{escape(name)}"{_checked(active)}>
      </label>
    """


def _select(name: str, label: str, description: str, options: Iterable[tuple[str, str]], active: object) -> str:
    option_html = "\n".join(_option(value, text, active) for value, text in options)
    return f"""
      <label class="wb-row">
        <span class="wb-row-label">
          <b>{escape(label)}</b>
          <span>{escape(description)}</span>
        </span>
        <select name="{escape(name)}">{option_html}</select>
      </label>
    """


def _field(name: str, label: str, description: str, value: object, input_type: str = "text") -> str:
    return f"""
      <label class="wb-row">
        <span class="wb-row-label">
          <b>{escape(label)}</b>
          <span>{escape(description)}</span>
        </span>
        <input type="{escape(input_type)}" name="{escape(name)}" value="{escape(str(value or ''))}">
      </label>
    """


def _textarea(name: str, label: str, description: str, value: object) -> str:
    return f"""
      <label class="wb-row wb-row-tall">
        <span class="wb-row-label">
          <b>{escape(label)}</b>
          <span>{escape(description)}</span>
        </span>
        <textarea name="{escape(name)}">{escape(str(value or ""))}</textarea>
      </label>
    """


def _section(title: str, helper: str, rows: str, hero: bool = False) -> str:
    hero_class = " wb-hero" if hero else ""
    return f"""
      <section class="wb-section{hero_class}">
        <div class="wb-section-head">
          <h3>{escape(title)}</h3>
          <span>{escape(helper)}</span>
        </div>
        {rows}
      </section>
    """


def _dictionary_rows(dictionary_entries: Iterable[DictionaryEntry]) -> str:
    rows = []
    for entry in dictionary_entries:
        rows.append(
            """
            <div class="wb-table-row">
              <input data-col="spoken" value="{spoken}">
              <input data-col="written" value="{written}">
              <button type="button" data-remove-row>-</button>
            </div>
            """.format(
                spoken=escape(entry.spoken),
                written=escape(entry.written),
            )
        )
    if not rows:
        rows.append(
            """
            <div class="wb-table-row">
              <input data-col="spoken" placeholder="whisper bar">
              <input data-col="written" placeholder="WhisprBar">
              <button type="button" data-remove-row>-</button>
            </div>
            """
        )
    return "\n".join(rows)


def _snippet_rows(snippets: Iterable[Snippet]) -> str:
    rows = []
    for snippet in snippets:
        rows.append(
            """
            <div class="wb-table-row">
              <input data-col="trigger" value="{trigger}">
              <input data-col="text" value="{text}">
              <button type="button" data-remove-row>-</button>
            </div>
            """.format(
                trigger=escape(snippet.trigger),
                text=escape(snippet.text),
            )
        )
    if not rows:
        rows.append(
            """
            <div class="wb-table-row">
              <input data-col="trigger" placeholder="my signature">
              <input data-col="text" placeholder="Best regards, Rik">
              <button type="button" data-remove-row>-</button>
            </div>
            """
        )
    return "\n".join(rows)


def _hotkey_rows(config: Mapping[str, object]) -> str:
    hotkeys = config.get("hotkeys") if isinstance(config.get("hotkeys"), dict) else {}
    rows = []
    labels = hotkey_action_labels(config)
    for action_id, label in labels.items():
        current = ""
        if isinstance(hotkeys, dict):
            current = str(hotkeys.get(action_id) or "")
        rows.append(
            f"""
            <div class="wb-row wb-hotkey-row" data-hotkey-action="{escape(action_id)}">
              <span class="wb-row-label">
                <b>{escape(label)}</b>
                <span>{escape(action_id)}</span>
              </span>
              <span class="wb-inline-controls">
                <input name="hotkey:{escape(action_id)}" value="{escape(current)}" placeholder="{escape(t("settings.not_set", config))}">
                <button class="wb-button compact" type="button" data-capture-hotkey="{escape(action_id)}">{escape(t("settings.capture_hotkey", config))}</button>
              </span>
            </div>
            """
        )
    return "\n".join(rows)


def _command_action_label(command_id: str, config: Mapping[str, object]) -> str:
    labels = {
        "professional": t("voice_command.professional", config),
        "shorter": t("voice_command.shorter", config),
        "longer": t("voice_command.longer", config),
        "list": t("voice_command.list", config),
        "translate_english": t("voice_command.translate_english", config),
        "correct_english": t("voice_command.correct_english", config),
        "humanize": t("voice_command.humanize", config),
        "clipboard_only": t("voice_command.clipboard_only", config),
        "press_enter": t("voice_command.press_enter", config),
        "new_line": t("voice_command.new_line", config),
    }
    return labels.get(command_id, command_id.replace("_", " "))


def _command_requirement(spec: CommandSpec, config: Mapping[str, object]) -> str:
    parts = [
        t("settings.uses_ai_rewrite", config)
        if spec.rewrite_mode
        else t("settings.no_ai", config)
    ]
    if spec.command_id == "press_enter":
        parts.append(t("settings.requires_press_enter", config))
    return " · ".join(parts)


def _voice_command_rows(command_specs: Iterable[CommandSpec], config: Mapping[str, object]) -> str:
    rows = []
    for spec in command_specs:
        kind = "ai" if spec.rewrite_mode else "local"
        rows.append(
            f"""
            <div class="wb-command-row" data-command-kind="{escape(kind)}">
              <code>{escape(spec.phrase)}</code>
              <span>{escape(_command_action_label(spec.command_id, config))}</span>
              <span>{escape(_command_requirement(spec, config))}</span>
            </div>
            """
        )
    return "\n".join(rows)


def _device_options(
    devices: Iterable[Mapping[str, object]],
    active_device_name: Optional[object],
    config: Mapping[str, object],
) -> list[tuple[str, str]]:
    options = [("", t("option.system_default", config))]
    active_name = str(active_device_name or "").lower()
    for device in devices:
        name = str(device.get("name") or "")
        if not name:
            continue
        label = name
        if active_name and name.lower() == active_name:
            label = f"{name} ({t('option.active', config)})"
        options.append((name, label))
    return options


def apply_settings_payload(
    config: dict,
    payload: Mapping[str, object],
    *,
    state: Optional[dict] = None,
    save_config_func: Callable[[], None] = save_config,
    save_env_func: Callable[[str, str], None] = save_env_file_value,
    save_dictionary_func: Callable[[Iterable[DictionaryEntry]], None] = save_dictionary,
    save_snippets_func: Callable[[Iterable[Snippet]], None] = save_snippets,
    update_device_func: Callable[[], None] = update_device_index,
    reset_indicator_func: Optional[Callable[[], None]] = None,
    vad_available: bool = True,
    noise_reduction_available: bool = True,
) -> SettingsApplyResult:
    """Apply a JSON-like payload produced by the WebKit settings UI."""

    settings = payload.get("settings")
    hotkeys_payload = payload.get("hotkeys")
    api_keys = payload.get("api_keys")
    dictionary_payload = payload.get("dictionary")
    snippets_payload = payload.get("snippets")
    if not isinstance(settings, Mapping):
        settings = {}
    if not isinstance(hotkeys_payload, Mapping):
        hotkeys_payload = {}
    if not isinstance(api_keys, Mapping):
        api_keys = {}
    if not isinstance(dictionary_payload, list):
        dictionary_payload = []
    if not isinstance(snippets_payload, list):
        snippets_payload = []

    language_config = dict(config)
    language_config.setdefault("language", config.get("language", "de"))
    if isinstance(settings, Mapping) and "language" in settings:
        language_config["language"] = str(settings.get("language") or config.get("language", "de"))
    editable_hotkey_labels = hotkey_action_labels(language_config)

    pending_hotkeys = build_pending_hotkeys(
        config.get("hotkeys", {}),
        editable_hotkey_labels,
    )
    for action_id in editable_hotkey_labels:
        raw_value = hotkeys_payload.get(action_id, pending_hotkeys.get(action_id))
        if raw_value is None:
            pending_hotkeys[action_id] = None
            continue
        clean_value = str(raw_value).strip()
        pending_hotkeys[action_id] = clean_value or None

    conflicts = get_hotkey_conflicts_for_actions(pending_hotkeys, editable_hotkey_labels)
    conflict_message = build_hotkey_conflict_message(conflicts, editable_hotkey_labels, language_config)
    if conflict_message:
        return SettingsApplyResult(False, conflict_message)

    old_indicator = {
        "enabled": config.get("recording_indicator_enabled"),
        "position": config.get("recording_indicator_position"),
        "width": config.get("recording_indicator_width"),
        "height": config.get("recording_indicator_height"),
        "opacity": config.get("recording_indicator_opacity"),
    }

    config["theme_preference"] = str(_setting(settings, "theme_preference", config.get("theme_preference", "auto")) or "auto")
    config["language"] = str(_setting(settings, "language", config.get("language", "de")) or "de")
    config["auto_paste_enabled"] = _bool_value(_setting(settings, "auto_paste_enabled", config.get("auto_paste_enabled", False)))
    config["auto_paste_add_space"] = _bool_value(_setting(settings, "auto_paste_add_space", config.get("auto_paste_add_space", True)))
    config["auto_paste_add_newline"] = _bool_value(_setting(settings, "auto_paste_add_newline", config.get("auto_paste_add_newline", True)))
    config["notifications_enabled"] = _bool_value(_setting(settings, "notifications_enabled", config.get("notifications_enabled", True)))
    config["paste_sequence"] = str(_setting(settings, "paste_sequence", config.get("paste_sequence", "auto")) or "auto")
    config["paste_delay_ms"] = _clamp_int(
        _int_value(_setting(settings, "paste_delay_ms", config.get("paste_delay_ms", 250)), 250),
        0,
        5000,
    )
    config["hotkeys"] = pending_hotkeys.copy()
    config["hotkey"] = config["hotkeys"].get("toggle_recording") or config.get("hotkey", "F9")

    device_name = _setting(settings, "device_name", config.get("device_name"))
    config["device_name"] = str(device_name).strip() if device_name else None
    config["noise_reduction_enabled"] = (
        _bool_value(_setting(settings, "noise_reduction_enabled", config.get("noise_reduction_enabled", True)))
        if noise_reduction_available
        else False
    )
    config["noise_reduction_strength"] = _clamp_float(
        _float_value(
            _setting(settings, "noise_reduction_strength", config.get("noise_reduction_strength", 0.7)),
            0.7,
            1,
        ),
        0.0,
        1.0,
        1,
    )
    config["audio_feedback_enabled"] = _bool_value(_setting(settings, "audio_feedback_enabled", config.get("audio_feedback_enabled", True)))
    config["audio_feedback_volume"] = _clamp_float(
        _float_value(_setting(settings, "audio_feedback_volume", config.get("audio_feedback_volume", 0.3)), 0.3, 1),
        0.0,
        1.0,
        1,
    )

    config["transcription_backend"] = str(_setting(settings, "transcription_backend", config.get("transcription_backend", "openai")) or "openai")
    config["faster_whisper_model"] = str(_setting(settings, "faster_whisper_model", config.get("faster_whisper_model", "medium")) or "medium")
    config["streaming_model"] = str(_setting(settings, "streaming_model", config.get("streaming_model", "tiny")) or "tiny")

    config["use_vad"] = _bool_value(_setting(settings, "use_vad", config.get("use_vad", False))) if vad_available else False
    config["vad_energy_ratio"] = _clamp_float(
        _float_value(_setting(settings, "vad_energy_ratio", config.get("vad_energy_ratio", 0.02)), 0.02, 3),
        0.002,
        0.3,
        3,
    )
    config["vad_bridge_ms"] = _clamp_int(
        _int_value(_setting(settings, "vad_bridge_ms", config.get("vad_bridge_ms", 180)), 180),
        0,
        1000,
    )
    config["vad_min_energy_frames"] = _clamp_int(
        _int_value(_setting(settings, "vad_min_energy_frames", config.get("vad_min_energy_frames", 2)), 2),
        1,
        10,
    )
    config["vad_auto_stop_enabled"] = (
        _bool_value(_setting(settings, "vad_auto_stop_enabled", config.get("vad_auto_stop_enabled", False)))
        and config["use_vad"]
        if vad_available
        else False
    )
    config["vad_auto_stop_silence_seconds"] = _clamp_float(
        _float_value(
            _setting(settings, "vad_auto_stop_silence_seconds", config.get("vad_auto_stop_silence_seconds", 2.0)),
            2.0,
            1,
        ),
        0.5,
        30.0,
        1,
    )
    config["stop_tail_grace_ms"] = _clamp_int(
        _int_value(_setting(settings, "stop_tail_grace_ms", config.get("stop_tail_grace_ms", 500)), 500),
        0,
        2000,
    )
    config["min_audio_energy"] = _clamp_float(
        _float_value(_setting(settings, "min_audio_energy", config.get("min_audio_energy", 0.0008)), 0.0008, 4),
        0.0001,
        0.01,
        4,
    )
    config["postprocess_enabled"] = _bool_value(_setting(settings, "postprocess_enabled", config.get("postprocess_enabled", True)))
    config["postprocess_fix_spacing"] = _bool_value(_setting(settings, "postprocess_fix_spacing", config.get("postprocess_fix_spacing", True))) and config["postprocess_enabled"]
    config["postprocess_fix_capitalization"] = _bool_value(_setting(settings, "postprocess_fix_capitalization", config.get("postprocess_fix_capitalization", True))) and config["postprocess_enabled"]
    config["chunking_enabled"] = _bool_value(_setting(settings, "chunking_enabled", config.get("chunking_enabled", True)))

    config["recording_indicator_enabled"] = _bool_value(_setting(settings, "recording_indicator_enabled", config.get("recording_indicator_enabled", True)))
    config["recording_indicator_position"] = str(_setting(settings, "recording_indicator_position", config.get("recording_indicator_position", "top-center")) or "top-center")
    config["recording_indicator_width"] = _clamp_int(
        _int_value(_setting(settings, "recording_indicator_width", config.get("recording_indicator_width", 240)), 240),
        60,
        600,
    )
    config["recording_indicator_height"] = _clamp_int(
        _int_value(_setting(settings, "recording_indicator_height", config.get("recording_indicator_height", 30)), 30),
        10,
        100,
    )
    config["recording_indicator_opacity"] = _clamp_float(
        _float_value(_setting(settings, "recording_indicator_opacity", config.get("recording_indicator_opacity", 0.85)), 0.85, 2),
        0.3,
        1.0,
        2,
    )

    config["live_overlay_enabled"] = _bool_value(_setting(settings, "live_overlay_enabled", config.get("live_overlay_enabled", False)))
    config["live_overlay_font_size"] = _clamp_int(
        _int_value(_setting(settings, "live_overlay_font_size", config.get("live_overlay_font_size", 14)), 14),
        8,
        32,
    )
    config["live_overlay_opacity"] = _clamp_float(
        _float_value(_setting(settings, "live_overlay_opacity", config.get("live_overlay_opacity", 0.9)), 0.9, 2),
        0.3,
        1.0,
        2,
    )
    config["live_overlay_width"] = _clamp_int(
        _int_value(_setting(settings, "live_overlay_width", config.get("live_overlay_width", 400)), 400),
        200,
        800,
    )
    config["live_overlay_height"] = _clamp_int(
        _int_value(_setting(settings, "live_overlay_height", config.get("live_overlay_height", 150)), 150),
        100,
        400,
    )
    config["live_overlay_display_duration"] = _clamp_float(
        _float_value(
            _setting(settings, "live_overlay_display_duration", config.get("live_overlay_display_duration", 2.0)),
            2.0,
            1,
        ),
        0.5,
        10.0,
        1,
    )

    config["flow_mode_enabled"] = _bool_value(_setting(settings, "flow_mode_enabled", config.get("flow_mode_enabled", False)))
    config["flow_context_awareness_enabled"] = _bool_value(_setting(settings, "flow_context_awareness_enabled", config.get("flow_context_awareness_enabled", True)))
    config["flow_dictionary_enabled"] = _bool_value(_setting(settings, "flow_dictionary_enabled", config.get("flow_dictionary_enabled", True)))
    config["flow_snippets_enabled"] = _bool_value(_setting(settings, "flow_snippets_enabled", config.get("flow_snippets_enabled", True)))
    config["flow_command_mode_enabled"] = _bool_value(_setting(settings, "flow_command_mode_enabled", config.get("flow_command_mode_enabled", True)))
    config["flow_smart_formatting_enabled"] = _bool_value(_setting(settings, "flow_smart_formatting_enabled", config.get("flow_smart_formatting_enabled", True)))
    config["flow_backtrack_enabled"] = _bool_value(_setting(settings, "flow_backtrack_enabled", config.get("flow_backtrack_enabled", True)))
    config["flow_press_enter_enabled"] = _bool_value(_setting(settings, "flow_press_enter_enabled", config.get("flow_press_enter_enabled", False)))
    config["flow_rewrite_enabled"] = _bool_value(_setting(settings, "flow_rewrite_enabled", config.get("flow_rewrite_enabled", False)))
    config["flow_rewrite_provider"] = str(_setting(settings, "flow_rewrite_provider", config.get("flow_rewrite_provider", "none")) or "none")
    config["flow_rewrite_model"] = str(_setting(settings, "flow_rewrite_model", config.get("flow_rewrite_model", "")) or "").strip()
    config["flow_rewrite_timeout_seconds"] = _clamp_float(
        _float_value(
            _setting(settings, "flow_rewrite_timeout_seconds", config.get("flow_rewrite_timeout_seconds", 12.0)),
            12.0,
            1,
        ),
        1.0,
        60.0,
        1,
    )
    config["flow_default_profile"] = str(_setting(settings, "flow_default_profile", config.get("flow_default_profile", "default")) or "default")
    config["flow_history_storage"] = str(_setting(settings, "flow_history_storage", config.get("flow_history_storage", "normal")) or "normal")
    config["flow_history_auto_delete_hours"] = _clamp_int(
        _int_value(
            _setting(settings, "flow_history_auto_delete_hours", config.get("flow_history_auto_delete_hours", 24)),
            24,
        ),
        1,
        720,
    )
    config["flow_recent_copy_seconds"] = _clamp_int(
        _int_value(
            _setting(settings, "flow_recent_copy_seconds", config.get("flow_recent_copy_seconds", 5)),
            5,
        ),
        1,
        30,
    )
    languages_value = str(_setting(settings, "flow_preferred_languages", ", ".join(config.get("flow_preferred_languages", ["de", "en"]))) or "")
    config["flow_preferred_languages"] = [item.strip() for item in languages_value.split(",") if item.strip()] or ["de", "en"]
    config["flow_language_auto_detect"] = _bool_value(_setting(settings, "flow_language_auto_detect", config.get("flow_language_auto_detect", False)))
    config["flow_max_recording_minutes"] = _clamp_int(
        _int_value(
            _setting(settings, "flow_max_recording_minutes", config.get("flow_max_recording_minutes", 20)),
            20,
        ),
        1,
        60,
    )

    for key in ("DEEPGRAM_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        save_env_func(key, str(api_keys.get(key, "") or "").strip())

    dictionary_entries = [
        DictionaryEntry(
            spoken=str(item.get("spoken", "")).strip(),
            written=str(item.get("written", "")).strip(),
        )
        for item in dictionary_payload
        if isinstance(item, Mapping)
        and str(item.get("spoken", "")).strip()
        and str(item.get("written", "")).strip()
    ]
    snippet_entries = [
        Snippet(
            trigger=str(item.get("trigger", "")).strip(),
            text=str(item.get("text", "")).strip(),
        )
        for item in snippets_payload
        if isinstance(item, Mapping)
        and str(item.get("trigger", "")).strip()
        and str(item.get("text", "")).strip()
    ]
    save_dictionary_func(dictionary_entries)
    save_snippets_func(snippet_entries)

    new_indicator = {
        "enabled": config.get("recording_indicator_enabled"),
        "position": config.get("recording_indicator_position"),
        "width": config.get("recording_indicator_width"),
        "height": config.get("recording_indicator_height"),
        "opacity": config.get("recording_indicator_opacity"),
    }
    if old_indicator != new_indicator:
        if reset_indicator_func is None:
            try:
                from whisprbar.ui.recording_indicator import reset_recording_indicator

                reset_recording_indicator()
            except Exception as exc:
                print(f"[WARN] Failed to reset recording indicator: {exc}", file=sys.stderr)
        else:
            reset_indicator_func()

    if config.get("auto_paste_enabled") and state is not None:
        state["wayland_notice_shown"] = False

    save_config_func()
    update_device_func()
    return SettingsApplyResult(True, t("settings.saved", config))


def generate_settings_html(
    config: Mapping[str, object],
    dictionary_entries: Iterable[DictionaryEntry],
    snippets: Iterable[Snippet],
    *,
    devices: Optional[Iterable[Mapping[str, object]]] = None,
    api_keys: Optional[Mapping[str, str]] = None,
) -> str:
    """Generate the experimental WebKit settings HTML."""

    language = get_language(config)
    tr = lambda key: t(key, config)
    dictionary_rows = _dictionary_rows(dictionary_entries)
    snippet_rows = _snippet_rows(snippets)
    preferred_languages = config.get("flow_preferred_languages", ["de", "en"])
    if isinstance(preferred_languages, (list, tuple)):
        preferred_languages_text = ", ".join(str(item) for item in preferred_languages)
    else:
        preferred_languages_text = str(preferred_languages or "")
    api_keys = api_keys or {}
    devices = list(devices or [])
    paste_options = [(value, tr(f"paste.{value}")) for value in PASTE_OPTIONS]

    general_rows = (
        _select(
            "theme_preference",
            tr("setting.theme"),
            tr("setting.theme_desc"),
            [("auto", "Auto"), ("light", tr("option.light")), ("dark", tr("option.dark"))],
            config.get("theme_preference", "auto"),
        )
        + _select(
            "language",
            tr("setting.language"),
            tr("setting.language_desc"),
            [("de", "Deutsch"), ("en", "English")],
            config.get("language", "de"),
        )
        + _switch(
            "auto_paste_enabled",
            tr("setting.auto_paste"),
            tr("setting.auto_paste_desc"),
            config.get("auto_paste_enabled", False),
        )
        + _switch(
            "notifications_enabled",
            tr("setting.notifications"),
            tr("setting.notifications_desc"),
            config.get("notifications_enabled", True),
        )
        + _select(
            "paste_sequence",
            tr("setting.paste_mode"),
            tr("setting.paste_mode_desc"),
            paste_options,
            config.get("paste_sequence", "auto"),
        )
        + _switch(
            "auto_paste_add_space",
            tr("setting.add_trailing_space"),
            tr("setting.add_trailing_space_desc"),
            config.get("auto_paste_add_space", True),
        )
        + _switch(
            "auto_paste_add_newline",
            tr("setting.add_trailing_newline"),
            tr("setting.add_trailing_newline_desc"),
            config.get("auto_paste_add_newline", True),
        )
        + _field(
            "paste_delay_ms",
            tr("setting.paste_delay"),
            tr("setting.paste_delay_desc"),
            config.get("paste_delay_ms", 250),
            "number",
        )
    )
    hotkey_rows = _hotkey_rows(config)

    recording_rows = (
        _select(
            "device_name",
            tr("setting.input_device"),
            tr("setting.input_device_desc"),
            _device_options(devices, config.get("device_name"), config),
            config.get("device_name") or "",
        )
        + _switch(
            "use_vad",
            tr("setting.vad"),
            tr("setting.vad_desc"),
            config.get("use_vad", False),
        )
        + _field(
            "vad_bridge_ms",
            tr("setting.pause_bridge"),
            tr("setting.pause_bridge_desc"),
            config.get("vad_bridge_ms", 180),
            "number",
        )
        + _switch(
            "noise_reduction_enabled",
            tr("setting.noise_reduction"),
            tr("setting.noise_reduction_desc"),
            config.get("noise_reduction_enabled", True),
        )
        + _field(
            "noise_reduction_strength",
            tr("setting.noise_reduction_strength"),
            tr("setting.noise_reduction_strength_desc"),
            config.get("noise_reduction_strength", 0.7),
            "number",
        )
        + _switch(
            "audio_feedback_enabled",
            tr("setting.audio_feedback"),
            tr("setting.audio_feedback_desc"),
            config.get("audio_feedback_enabled", True),
        )
        + _field(
            "audio_feedback_volume",
            tr("setting.audio_feedback_volume"),
            tr("setting.audio_feedback_volume_desc"),
            config.get("audio_feedback_volume", 0.3),
            "number",
        )
    )

    transcription_rows = (
        _select(
            "transcription_backend",
            tr("setting.backend"),
            tr("setting.backend_desc"),
            [
                ("deepgram", "Deepgram Nova-3"),
                ("elevenlabs", "ElevenLabs Scribe v2"),
                ("openai", "OpenAI Whisper"),
                ("faster_whisper", "faster-whisper"),
                ("streaming", "sherpa-onnx"),
            ],
            config.get("transcription_backend", "openai"),
        )
        + _field(
            "faster_whisper_model",
            tr("setting.local_model"),
            tr("setting.local_model_desc"),
            config.get("faster_whisper_model", "medium"),
        )
        + _field(
            "streaming_model",
            tr("setting.streaming_model"),
            tr("setting.streaming_model_desc"),
            config.get("streaming_model", "tiny"),
        )
    )
    api_rows = (
        _field(
            "api:DEEPGRAM_API_KEY",
            "Deepgram API key",
            tr("setting.api_key_desc"),
            api_keys.get("DEEPGRAM_API_KEY", ""),
            "password",
        )
        + _field(
            "api:OPENAI_API_KEY",
            "OpenAI API key",
            tr("setting.api_key_desc"),
            api_keys.get("OPENAI_API_KEY", ""),
            "password",
        )
        + _field(
            "api:ELEVENLABS_API_KEY",
            "ElevenLabs API key",
            tr("setting.api_key_desc"),
            api_keys.get("ELEVENLABS_API_KEY", ""),
            "password",
        )
    )
    postprocess_rows = (
        _switch(
            "postprocess_enabled",
            tr("setting.postprocess"),
            tr("setting.postprocess_desc"),
            config.get("postprocess_enabled", True),
        )
        + _switch(
            "postprocess_fix_spacing",
            tr("setting.fix_spacing"),
            tr("setting.fix_spacing_desc"),
            config.get("postprocess_fix_spacing", True),
        )
        + _switch(
            "postprocess_fix_capitalization",
            tr("setting.fix_capitalization"),
            tr("setting.fix_capitalization_desc"),
            config.get("postprocess_fix_capitalization", True),
        )
    )

    flow_primary_rows = (
        _switch(
            "flow_mode_enabled",
            tr("settings.flow_mode"),
            tr("setting.flow_mode_desc"),
            config.get("flow_mode_enabled", False),
        )
        + _switch(
            "flow_context_awareness_enabled",
            tr("setting.context_awareness"),
            tr("setting.context_awareness_desc"),
            config.get("flow_context_awareness_enabled", True),
        )
        + _switch(
            "flow_smart_formatting_enabled",
            tr("setting.smart_formatting"),
            tr("setting.smart_formatting_desc"),
            config.get("flow_smart_formatting_enabled", True),
        )
        + _switch(
            "flow_backtrack_enabled",
            tr("setting.backtrack"),
            tr("setting.backtrack_desc"),
            config.get("flow_backtrack_enabled", True),
        )
        + _switch(
            "flow_command_mode_enabled",
            tr("setting.command_mode"),
            tr("setting.command_mode_desc"),
            config.get("flow_command_mode_enabled", True),
        )
        + _switch(
            "flow_press_enter_enabled",
            tr("setting.press_enter"),
            tr("setting.press_enter_desc"),
            config.get("flow_press_enter_enabled", False),
        )
    )

    flow_controls_rows = (
        _select(
            "flow_default_profile",
            tr("setting.default_profile"),
            tr("setting.default_profile_desc"),
            [
                ("default", tr("option.default")),
                ("chat", "Chat"),
                ("email", tr("option.email")),
                ("notes", tr("option.notes")),
                ("editor", "Editor"),
                ("terminal", "Terminal"),
            ],
            config.get("flow_default_profile", "default"),
        )
        + _field(
            "flow_preferred_languages",
            tr("setting.preferred_languages"),
            tr("setting.preferred_languages_desc"),
            preferred_languages_text,
        )
        + _field(
            "flow_max_recording_minutes",
            tr("setting.max_recording"),
            tr("setting.max_recording_desc"),
            config.get("flow_max_recording_minutes", 20),
            "number",
        )
        + _field(
            "flow_recent_copy_seconds",
            tr("setting.recent_transcript_window"),
            tr("setting.recent_transcript_window_desc"),
            config.get("flow_recent_copy_seconds", 5),
            "number",
        )
        + _switch(
            "flow_language_auto_detect",
            tr("setting.language_auto_detect"),
            tr("setting.language_auto_detect_desc"),
            config.get("flow_language_auto_detect", False),
        )
    )
    rewrite_rows = (
        _switch(
            "flow_rewrite_enabled",
            tr("settings.ai_rewrite"),
            tr("setting.ai_rewrite_desc"),
            config.get("flow_rewrite_enabled", False),
        )
        + _select(
            "flow_rewrite_provider",
            tr("setting.rewrite_provider"),
            tr("setting.rewrite_provider_desc"),
            [("none", "None"), ("openai_compatible", "OpenAI-compatible")],
            config.get("flow_rewrite_provider", "none"),
        )
        + _field(
            "flow_rewrite_model",
            tr("setting.rewrite_model"),
            tr("setting.rewrite_model_desc"),
            config.get("flow_rewrite_model", ""),
        )
        + _field(
            "flow_rewrite_timeout_seconds",
            tr("setting.rewrite_timeout"),
            tr("setting.rewrite_timeout_desc"),
            config.get("flow_rewrite_timeout_seconds", 12.0),
            "number",
        )
    )
    ai_command_rows = _voice_command_rows(
        (spec for spec in COMMAND_SPECS if spec.rewrite_mode),
        config,
    )
    local_command_rows = _voice_command_rows(
        (spec for spec in COMMAND_SPECS if not spec.rewrite_mode),
        config,
    )

    privacy_rows = (
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
        + _switch(
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
        + _field(
            "flow_history_auto_delete_hours",
            tr("setting.auto_delete_hours"),
            tr("setting.auto_delete_hours_desc"),
            config.get("flow_history_auto_delete_hours", 24),
            "number",
        )
    )

    advanced_rows = (
        _field(
            "min_audio_energy",
            tr("setting.hallucination_guard"),
            tr("setting.hallucination_guard_desc"),
            config.get("min_audio_energy", 0.0008),
            "number",
        )
        + _switch(
            "chunking_enabled",
            tr("setting.chunking"),
            tr("setting.chunking_desc"),
            config.get("chunking_enabled", True),
        )
    )
    vad_rows = (
        _field(
            "vad_energy_ratio",
            tr("setting.vad_sensitivity"),
            tr("setting.vad_sensitivity_desc"),
            config.get("vad_energy_ratio", 0.02),
            "number",
        )
        + _field(
            "vad_min_energy_frames",
            tr("setting.noise_guard_frames"),
            tr("setting.noise_guard_frames_desc"),
            config.get("vad_min_energy_frames", 2),
            "number",
        )
        + _switch(
            "vad_auto_stop_enabled",
            tr("setting.auto_stop_on_silence"),
            tr("setting.auto_stop_on_silence_desc"),
            config.get("vad_auto_stop_enabled", False),
        )
        + _field(
            "vad_auto_stop_silence_seconds",
            tr("setting.silence_duration"),
            tr("setting.silence_duration_desc"),
            config.get("vad_auto_stop_silence_seconds", 2.0),
            "number",
        )
        + _field(
            "stop_tail_grace_ms",
            tr("setting.recording_tail_buffer"),
            tr("setting.recording_tail_buffer_desc"),
            config.get("stop_tail_grace_ms", 500),
            "number",
        )
    )
    indicator_rows = (
        _switch(
            "recording_indicator_enabled",
            tr("setting.flow_indicator"),
            tr("setting.flow_indicator_desc"),
            config.get("recording_indicator_enabled", True),
        )
        + _select(
            "recording_indicator_position",
            tr("setting.indicator_position"),
            tr("setting.indicator_position_desc"),
            [
                ("top-center", tr("option.top_center")),
                ("top-left", tr("option.top_left")),
                ("top-right", tr("option.top_right")),
                ("bottom-center", tr("option.bottom_center")),
                ("draggable", tr("option.draggable")),
            ],
            config.get("recording_indicator_position", "top-center"),
        )
        + _field(
            "recording_indicator_width",
            tr("setting.indicator_width"),
            tr("setting.indicator_width_desc"),
            config.get("recording_indicator_width", 240),
            "number",
        )
        + _field(
            "recording_indicator_height",
            tr("setting.indicator_height"),
            tr("setting.indicator_height_desc"),
            config.get("recording_indicator_height", 30),
            "number",
        )
        + _field(
            "recording_indicator_opacity",
            tr("setting.indicator_opacity"),
            tr("setting.indicator_opacity_desc"),
            config.get("recording_indicator_opacity", 0.85),
            "number",
        )
        + """
      <div class="wb-row">
        <span class="wb-row-label">
          <b>{preview_label}</b>
          <span>{preview_desc}</span>
        </span>
        <button class="wb-button compact" type="button" data-preview-indicator>{preview_button}</button>
      </div>
    """.format(
            preview_label=escape(tr("setting.preview_indicator")),
            preview_desc=escape(tr("setting.preview_indicator_desc")),
            preview_button=escape(tr("setting.preview")),
        )
    )
    overlay_rows = (
        _switch(
            "live_overlay_enabled",
            tr("setting.live_overlay"),
            tr("setting.live_overlay_desc"),
            config.get("live_overlay_enabled", False),
        )
        + _field(
            "live_overlay_font_size",
            tr("setting.overlay_font_size"),
            tr("setting.overlay_font_size_desc"),
            config.get("live_overlay_font_size", 14),
            "number",
        )
        + _field(
            "live_overlay_opacity",
            tr("setting.overlay_opacity"),
            tr("setting.indicator_opacity_desc"),
            config.get("live_overlay_opacity", 0.9),
            "number",
        )
        + _field(
            "live_overlay_width",
            tr("setting.overlay_width"),
            tr("setting.indicator_width_desc"),
            config.get("live_overlay_width", 400),
            "number",
        )
        + _field(
            "live_overlay_height",
            tr("setting.overlay_height"),
            tr("setting.indicator_height_desc"),
            config.get("live_overlay_height", 150),
            "number",
        )
        + _field(
            "live_overlay_display_duration",
            tr("setting.overlay_duration"),
            tr("setting.overlay_duration_desc"),
            config.get("live_overlay_display_duration", 2.0),
            "number",
        )
    )

    return f"""<!doctype html>
<html lang="{escape(language)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(tr("settings.title"))}</title>
<style>
  :root {{
    color-scheme: dark;
    --window-min-width: 1080px;
    --bg: #0d1218;
    --panel: #121a23;
    --panel-2: #101821;
    --card: rgba(255,255,255,0.052);
    --card-strong: rgba(255,255,255,0.068);
    --border: rgba(255,255,255,0.105);
    --muted: #8f9dad;
    --text: #e8f0f7;
    --accent: #67d6ff;
    --accent-2: #7d8cff;
    --hairline: inset 0 0 0 1px rgba(255,255,255,0.075);
    --soft-shadow: 0 18px 60px rgba(0,0,0,0.24);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    background: var(--bg);
    color: var(--text);
    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }}
  button, input, select, textarea {{ font: inherit; }}
  .wb-frame {{
    min-width: var(--window-min-width);
    min-height: 100vh;
    background: var(--bg);
    overflow: hidden;
  }}
  .wb-windowbar {{
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    background: var(--panel);
  }}
  .wb-title {{
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 700;
  }}
  .wb-logo {{
    width: 30px;
    height: 30px;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #061016;
    display: grid;
    place-items: center;
    font-size: 11px;
    font-weight: 800;
    box-shadow: 0 0 0 1px rgba(255,255,255,0.22) inset;
  }}
  .wb-actions {{ display: flex; gap: 8px; }}
  .wb-button {{
    height: 32px;
    border: 0;
    border-radius: 8px;
    padding: 0 14px;
    background: rgba(255,255,255,0.08);
    color: #c8d3de;
    box-shadow: var(--hairline);
    cursor: pointer;
  }}
  .wb-button.primary {{
    background: var(--accent);
    color: #071118;
    font-weight: 700;
    box-shadow: 0 0 0 1px rgba(255,255,255,0.30) inset, 0 8px 22px rgba(103,214,255,0.16);
  }}
  .wb-button:hover {{ background: rgba(255,255,255,0.115); }}
  .wb-button.primary:hover {{ background: #7adeff; }}
  .wb-shell {{
    display: grid;
    grid-template-columns: 218px minmax(0, 1fr);
    height: calc(100vh - 52px);
    min-height: 0;
    overflow: hidden;
  }}
  .wb-sidebar {{
    position: sticky;
    top: 0;
    align-self: start;
    height: calc(100vh - 52px);
    overflow-y: auto;
    padding: 18px 12px;
    background: var(--panel-2);
    border-right: 1px solid rgba(255,255,255,0.08);
  }}
  .wb-nav-label {{
    padding: 8px 10px 10px;
    color: #71808e;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .wb-nav {{ display: grid; gap: 4px; }}
  .wb-nav-item {{
    display: grid;
    grid-template-columns: 20px 1fr auto;
    align-items: center;
    gap: 10px;
    min-height: 40px;
    border: 0;
    border-radius: 9px;
    padding: 0 12px;
    color: #b5c0cc;
    background: transparent;
    text-align: left;
    cursor: pointer;
  }}
  .wb-nav-item:hover {{ background: rgba(255,255,255,0.055); }}
  .wb-nav-item.active {{
    background: linear-gradient(135deg, #223347, #1a2938);
    color: #f6fbff;
    box-shadow: var(--hairline);
  }}
  .wb-icon {{
    width: 10px;
    height: 10px;
    border-radius: 99px;
    background: #536170;
  }}
  .wb-nav-item.active .wb-icon {{ background: var(--accent); }}
  .wb-count {{ font-size: 10px; color: #8fa0af; }}
  .wb-main {{
    padding: 26px 30px 30px;
    background: #0d1218;
    min-height: 0;
    overflow-y: auto;
  }}
  .wb-page {{ display: none; max-width: 1180px; }}
  .wb-page.active {{ display: block; }}
  .wb-page-head {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 16px;
    align-items: start;
    margin-bottom: 22px;
  }}
  .wb-page-head h2 {{ margin: 0 0 6px; font-size: 26px; letter-spacing: 0; }}
  .wb-page-head p {{ margin: 0; color: #9aa8b6; line-height: 1.45; }}
  .wb-status-pill {{
    height: 32px;
    display: flex;
    align-items: center;
    gap: 7px;
    border-radius: 999px;
    padding: 0 12px;
    background: rgba(103, 214, 255, 0.12);
    box-shadow: 0 0 0 1px rgba(103, 214, 255, 0.24) inset;
    color: #bdefff;
    font-size: 12px;
  }}
  .wb-dot {{
    width: 7px;
    height: 7px;
    border-radius: 99px;
    background: var(--accent);
  }}
  .wb-layout {{
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(270px, 0.8fr);
    gap: 18px;
  }}
  .wb-stack {{ display: grid; gap: 16px; }}
  .wb-section {{
    border: 0;
    border-radius: 12px;
    background: var(--card);
    box-shadow: var(--hairline), var(--soft-shadow);
    overflow: hidden;
  }}
  .wb-hero {{
    background: linear-gradient(135deg, rgba(83,170,220,0.18), rgba(255,255,255,0.04));
    box-shadow: inset 0 0 0 1px rgba(103,214,255,0.22), var(--soft-shadow);
  }}
  .wb-section-head {{
    padding: 15px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }}
  .wb-section-head h3 {{ margin: 0; font-size: 14px; }}
  .wb-section-head span {{ color: #8d9cac; font-size: 12px; }}
  .wb-row {{
    min-height: 54px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 18px;
    padding: 9px 16px;
    border-top: 1px solid rgba(255,255,255,0.055);
  }}
  .wb-row:hover {{ background: rgba(255,255,255,0.026); }}
  .wb-row:first-of-type {{ border-top: 0; }}
  .wb-row-label {{ display: grid; gap: 3px; min-width: 0; }}
  .wb-row-label b {{ font-size: 13px; font-weight: 650; color: #dce5ee; }}
  .wb-row-label span {{ font-size: 11px; color: #8998a7; line-height: 1.38; }}
  input, select, textarea {{
    height: 34px;
    min-width: 138px;
    border-radius: 8px;
    background: #18232e;
    border: 0;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.105);
    color: #d5e0ea;
    padding: 0 11px;
    outline: none;
  }}
  textarea {{
    height: 70px;
    padding: 9px 11px;
    resize: vertical;
  }}
  input:focus, select:focus, textarea:focus {{ box-shadow: inset 0 0 0 1px rgba(103,214,255,0.62), 0 0 0 3px rgba(103,214,255,0.10); }}
  .wb-row-tall {{ align-items: start; padding-top: 12px; padding-bottom: 12px; }}
  .wb-inline-controls {{ display: flex; align-items: center; gap: 8px; }}
  .wb-inline-controls input {{ width: 160px; }}
  .wb-button.compact {{ height: 30px; padding: 0 10px; font-size: 12px; }}
  .wb-switch-input {{
    appearance: none;
    width: 42px;
    height: 24px;
    min-width: 42px;
    padding: 0;
    border: 0;
    border-radius: 99px;
    background: #2c4052;
    position: relative;
  }}
  .wb-switch-input::after {{
    content: "";
    position: absolute;
    left: 2px;
    top: 2px;
    width: 20px;
    height: 20px;
    border-radius: 99px;
    background: #8fa0af;
    transition: left 120ms ease, background 120ms ease;
  }}
  .wb-switch-input:checked::after {{
    left: 20px;
    background: var(--accent);
  }}
  .wb-table {{ padding: 13px 16px 16px; display: grid; gap: 8px; }}
  .wb-table-head, .wb-table-row {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 42px;
    gap: 8px;
  }}
  .wb-table-head {{
    color: #7f8d9b;
    font-size: 11px;
    padding: 0 4px 2px;
  }}
  .wb-table-row input {{ width: 100%; min-width: 0; }}
  .wb-table-row button {{
    border: 0;
    border-radius: 8px;
    background: rgba(255,255,255,0.08);
    color: #cbd7e3;
    cursor: pointer;
  }}
  .wb-table-actions {{
    display: flex;
    justify-content: flex-end;
    padding: 0 16px 16px;
  }}
  .wb-message {{
    min-width: 180px;
    color: #91a1b1;
    align-self: center;
    font-size: 12px;
  }}
  .wb-message.error {{ color: #ffb5bd; }}
  .wb-message.ok {{ color: #a9f3c4; }}
  .wb-note {{
    padding: 14px 16px;
    color: #91a1b1;
    font-size: 12px;
    line-height: 1.45;
  }}
  .wb-command-list {{
    display: grid;
    gap: 0;
  }}
  .wb-command-head, .wb-command-row {{
    display: grid;
    grid-template-columns: minmax(220px, 1fr) minmax(160px, 0.72fr) minmax(180px, 0.9fr);
    gap: 12px;
    align-items: center;
    padding: 10px 16px;
    border-top: 1px solid rgba(255,255,255,0.055);
  }}
  .wb-command-head {{
    border-top: 0;
    color: #7f8d9b;
    font-size: 11px;
  }}
  .wb-command-row code {{
    min-width: 0;
    white-space: normal;
    overflow-wrap: anywhere;
    border-radius: 6px;
    background: rgba(0,0,0,0.18);
    color: #dce5ee;
    padding: 5px 7px;
    line-height: 1.3;
  }}
  .wb-command-row span {{
    min-width: 0;
    color: #aab7c4;
    font-size: 12px;
    line-height: 1.35;
  }}
  @media (max-width: 760px) {{
    .wb-shell {{ grid-template-columns: 1fr; height: auto; min-height: calc(100vh - 52px); overflow: visible; }}
    .wb-sidebar {{ position: static; height: auto; border-right: 0; border-bottom: 1px solid rgba(255,255,255,0.08); }}
    .wb-layout {{ grid-template-columns: 1fr; }}
    .wb-page-head {{ grid-template-columns: 1fr; }}
    .wb-main {{ overflow: visible; }}
    .wb-command-head, .wb-command-row {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<form class="wb-frame wb-polished">
  <header class="wb-windowbar">
    <div class="wb-title"><span class="wb-logo">WB</span><span>{escape(tr("settings.title"))}</span></div>
    <div class="wb-actions">
      <span id="settings-message" class="wb-message"></span>
      <button id="settings-cancel" class="wb-button" type="button">{escape(tr("settings.cancel"))}</button>
      <button id="settings-save" class="wb-button primary" type="button">{escape(tr("settings.save"))}</button>
    </div>
  </header>
  <div class="wb-shell">
    <aside class="wb-sidebar">
      <div class="wb-nav-label">{escape(tr("settings.nav_label"))}</div>
      <nav class="wb-nav" aria-label="{escape(tr("settings.nav_label"))}">
        <button class="wb-nav-item active" type="button" data-page="general"><span class="wb-icon"></span><span>{escape(tr("settings.general"))}</span><span class="wb-count">2</span></button>
        <button class="wb-nav-item" type="button" data-page="recording"><span class="wb-icon"></span><span>{escape(tr("settings.recording"))}</span><span class="wb-count">2</span></button>
        <button class="wb-nav-item" type="button" data-page="transcription"><span class="wb-icon"></span><span>{escape(tr("settings.transcription"))}</span><span class="wb-count">3</span></button>
        <button class="wb-nav-item" type="button" data-page="flow"><span class="wb-icon"></span><span>{escape(tr("settings.flow"))}</span><span class="wb-count">5</span></button>
        <button class="wb-nav-item" type="button" data-page="voice-commands"><span class="wb-icon"></span><span>{escape(tr("settings.voice_commands"))}</span><span class="wb-count">{len(COMMAND_SPECS)}</span></button>
        <button class="wb-nav-item" type="button" data-page="privacy"><span class="wb-icon"></span><span>{escape(tr("settings.privacy"))}</span><span class="wb-count">1</span></button>
        <button class="wb-nav-item" type="button" data-page="advanced"><span class="wb-icon"></span><span>{escape(tr("settings.advanced"))}</span><span class="wb-count">4</span></button>
      </nav>
    </aside>
    <main class="wb-main">
      <section class="wb-page active" data-page-id="general">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.general"))}</h2><p>{escape(tr("settings.general_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.local_preview"))}</span>
        </div>
        <div class="wb-stack">
          {_section(tr("settings.app_behavior"), tr("settings.daily_use"), general_rows, hero=True)}
          {_section(tr("settings.hotkeys"), tr("settings.all_actions"), hotkey_rows)}
        </div>
      </section>

      <section class="wb-page" data-page-id="recording">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.recording"))}</h2><p>{escape(tr("settings.recording_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.audio"))}</span>
        </div>
        <div class="wb-stack">
          {_section(tr("settings.capture"), tr("settings.input_feedback"), recording_rows, hero=True)}
          {_section(tr("settings.silence_handling"), tr("settings.expert_vad"), vad_rows)}
        </div>
      </section>

      <section class="wb-page" data-page-id="transcription">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.transcription"))}</h2><p>{escape(tr("settings.transcription_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.engine_status"))}</span>
        </div>
        <div class="wb-stack">
          {_section(tr("settings.engine"), tr("setting.backend"), transcription_rows, hero=True)}
          {_section(tr("settings.api_keys"), tr("settings.local_env_file"), api_rows)}
          {_section(tr("settings.post_processing"), tr("settings.cleanup"), postprocess_rows)}
        </div>
      </section>

      <section class="wb-page" data-page-id="flow">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.flow"))}</h2><p>{escape(tr("settings.flow_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.flow_ready"))}</span>
        </div>
        <div class="wb-layout">
          <div class="wb-stack">
            {_section(tr("settings.flow_mode"), tr("settings.behavior"), flow_primary_rows, hero=True)}
            {_section(tr("settings.profiles"), tr("settings.context"), flow_controls_rows)}
            {_section(tr("settings.ai_rewrite"), tr("settings.optional"), rewrite_rows)}
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

      <section class="wb-page" data-page-id="voice-commands">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.voice_commands"))}</h2><p>{escape(tr("settings.voice_commands_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("setting.command_mode"))}</span>
        </div>
        <div class="wb-stack">
          <section class="wb-section wb-hero">
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
        </div>
      </section>

      <section class="wb-page" data-page-id="privacy">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.privacy"))}</h2><p>{escape(tr("settings.privacy_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.local_files"))}</span>
        </div>
        <div class="wb-stack">{_section(tr("settings.storage"), tr("settings.history_local_helpers"), privacy_rows, hero=True)}</div>
      </section>

      <section class="wb-page" data-page-id="advanced">
        <div class="wb-page-head">
          <div><h2>{escape(tr("settings.advanced"))}</h2><p>{escape(tr("settings.advanced_desc"))}</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> {escape(tr("settings.expert"))}</span>
        </div>
        <div class="wb-stack">
          {_section(tr("settings.runtime"), tr("settings.technical"), advanced_rows, hero=True)}
          {_section(tr("settings.indicator"), tr("settings.flow_bar"), indicator_rows)}
          {_section(tr("settings.overlay"), tr("settings.floating_transcript"), overlay_rows)}
          <section class="wb-section"><div class="wb-note">{escape(tr("settings.advanced_note"))}</div></section>
        </div>
      </section>
    </main>
  </div>
</form>
<script>
  const messageEl = document.getElementById('settings-message');
  const navButtons = [...document.querySelectorAll('.wb-nav-item')];
  const pages = [...document.querySelectorAll('.wb-page')];
  for (const button of navButtons) {{
    button.addEventListener('click', () => {{
      const page = button.dataset.page;
      navButtons.forEach(item => item.classList.toggle('active', item === button));
      pages.forEach(item => item.classList.toggle('active', item.dataset.pageId === page));
    }});
  }}

  function postSettingsMessage(message) {{
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.settings) {{
      window.webkit.messageHandlers.settings.postMessage(JSON.stringify(message));
    }}
  }}

  function setMessage(text, type = '') {{
    messageEl.textContent = text || '';
    messageEl.className = `wb-message ${{type}}`;
  }}

  function readNamedControls() {{
    const settings = {{}};
    const hotkeys = {{}};
    const api_keys = {{}};
    document.querySelectorAll('[name]').forEach((control) => {{
      const name = control.getAttribute('name');
      const value = control.type === 'checkbox' ? control.checked : control.value;
      if (name.startsWith('hotkey:')) {{
        hotkeys[name.slice(7)] = value;
      }} else if (name.startsWith('api:')) {{
        api_keys[name.slice(4)] = value;
      }} else {{
        settings[name] = value;
      }}
    }});
    return {{ settings, hotkeys, api_keys }};
  }}

  function readTable(tableName) {{
    return [...document.querySelectorAll(`[data-table="${{tableName}}"] .wb-table-row`)].map((row) => {{
      const item = {{}};
      row.querySelectorAll('[data-col]').forEach((input) => {{
        item[input.dataset.col] = input.value;
      }});
      return item;
    }});
  }}

  function collectPayload() {{
    const payload = readNamedControls();
    payload.dictionary = readTable('dictionary');
    payload.snippets = readTable('snippets');
    return payload;
  }}

  function makeTableRow(tableName) {{
    const row = document.createElement('div');
    row.className = 'wb-table-row';
    if (tableName === 'dictionary') {{
      row.innerHTML = '<input data-col="spoken" placeholder="whisper bar"><input data-col="written" placeholder="WhisprBar"><button type="button" data-remove-row>-</button>';
    }} else {{
      row.innerHTML = '<input data-col="trigger" placeholder="my signature"><input data-col="text" placeholder="Best regards, Rik"><button type="button" data-remove-row>-</button>';
    }}
    return row;
  }}

  document.querySelectorAll('[data-add-row]').forEach((button) => {{
    button.addEventListener('click', () => {{
      const tableName = button.dataset.addRow;
      const table = document.querySelector(`[data-table="${{tableName}}"]`);
      table.appendChild(makeTableRow(tableName));
    }});
  }});

  document.addEventListener('click', (event) => {{
    const removeButton = event.target.closest('[data-remove-row]');
    if (removeButton) {{
      const row = removeButton.closest('.wb-table-row');
      const table = row.parentElement;
      if (table.querySelectorAll('.wb-table-row').length > 1) {{
        row.remove();
      }} else {{
        row.querySelectorAll('input').forEach(input => input.value = '');
      }}
      return;
    }}
    const captureButton = event.target.closest('[data-capture-hotkey]');
    if (captureButton) {{
      const action = captureButton.dataset.captureHotkey;
      setMessage({json.dumps(tr("settings.press_key"))}, '');
      postSettingsMessage({{ action: 'capture_hotkey', hotkey_action: action }});
    }}
  }});

  document.getElementById('settings-save').addEventListener('click', () => {{
    setMessage({json.dumps(tr("settings.saving"))}, '');
    postSettingsMessage({{ action: 'save', payload: collectPayload() }});
  }});

  document.getElementById('settings-cancel').addEventListener('click', () => {{
    postSettingsMessage({{ action: 'cancel' }});
  }});

  document.querySelectorAll('[data-preview-indicator]').forEach((button) => {{
    button.addEventListener('click', () => {{
      postSettingsMessage({{ action: 'preview_indicator', payload: collectPayload() }});
    }});
  }});

  window.whisprbarSettings = {{
    setHotkey(action, value, label) {{
      const input = document.querySelector(`[name="hotkey:${{action}}"]`);
      if (input) {{
        input.value = value || '';
        input.title = label || value || '';
      }}
      setMessage(label ? `${{label}}` : {json.dumps(tr("settings.hotkey_captured"))}, 'ok');
    }},
    setMessage(text, type) {{
      setMessage(text, type);
    }}
  }};
</script>
</body>
</html>"""


def _decode_webkit_message(message: object) -> dict:
    try:
        value = message.get_js_value()
        raw = value.to_string()
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {}
    except Exception as exc:
        print(f"[WARN] Failed to decode settings message: {exc}", file=sys.stderr)
        return {}


def _run_webview_script(webview: object, script: str) -> None:
    try:
        webview.run_javascript(script, None, None, None)
    except Exception as exc:
        print(f"[WARN] Failed to run settings script: {exc}", file=sys.stderr)


def _set_webview_message(webview: object, text: str, message_type: str = "") -> None:
    _run_webview_script(
        webview,
        "window.whisprbarSettings && "
        f"window.whisprbarSettings.setMessage({json.dumps(text)}, {json.dumps(message_type)});",
    )


def open_settings_window(
    config: dict,
    state: Optional[dict] = None,
    on_save: Optional[Callable[[], None]] = None,
    *,
    quit_on_destroy: bool = False,
) -> bool:
    """Open the production WebKit settings window."""

    global _settings_webview_window

    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import Gtk, WebKit2
    except Exception as exc:
        print(f"[WARN] WebKit settings unavailable, falling back to GTK settings: {exc}", file=sys.stderr)
        try:
            from whisprbar.ui.settings import open_settings_window as open_gtk_settings

            open_gtk_settings(config, state or {}, on_save=on_save)
            return True
        except Exception as fallback_exc:
            notify(t("settings.unavailable", config))
            print(f"[WARN] Settings fallback unavailable: {fallback_exc}", file=sys.stderr)
            return False

    with _settings_webview_lock:
        if _settings_webview_window is not None:
            _present_settings_window(_settings_webview_window)
            return True

    window = Gtk.Window(title=t("settings.title", config))
    window.set_position(Gtk.WindowPosition.CENTER)
    window.set_default_size(1120, 760)
    window.set_resizable(True)

    user_content = WebKit2.UserContentManager()
    user_content.register_script_message_handler("settings")
    webview = WebKit2.WebView.new_with_user_content_manager(user_content)
    window.add(webview)
    preview_state = {"indicator": None}
    closing = {"active": False}

    def close_window(*_args) -> None:
        global _settings_webview_window
        if closing["active"]:
            return
        closing["active"] = True
        cancel_hotkey_capture()
        if preview_state["indicator"] is not None:
            try:
                preview_state["indicator"].destroy()
            except Exception:
                pass
            preview_state["indicator"] = None
        with _settings_webview_lock:
            if _settings_webview_window is window:
                _settings_webview_window = None
        try:
            window.destroy()
        except Exception:
            pass
        if quit_on_destroy:
            Gtk.main_quit()

    def handle_preview_indicator(payload: Mapping[str, object]) -> None:
        try:
            from gi.repository import GLib
            from whisprbar.ui.recording_indicator import PHASE_RECORDING, RecordingIndicator

            settings = payload.get("settings") if isinstance(payload.get("settings"), Mapping) else {}
            preview_config = dict(config)
            preview_config["recording_indicator_enabled"] = True
            preview_config["recording_indicator_position"] = str(
                _setting(settings, "recording_indicator_position", config.get("recording_indicator_position", "top-center"))
                or "top-center"
            )
            preview_config["recording_indicator_width"] = _int_value(
                _setting(settings, "recording_indicator_width", config.get("recording_indicator_width", 240)),
                240,
            )
            preview_config["recording_indicator_height"] = _int_value(
                _setting(settings, "recording_indicator_height", config.get("recording_indicator_height", 30)),
                30,
            )
            preview_config["recording_indicator_opacity"] = _float_value(
                _setting(settings, "recording_indicator_opacity", config.get("recording_indicator_opacity", 0.85)),
                0.85,
                2,
            )
            if preview_state["indicator"] is not None:
                preview_state["indicator"].destroy()
            indicator = RecordingIndicator(preview_config)
            preview_state["indicator"] = indicator
            indicator.show(PHASE_RECORDING)

            def stop_preview() -> bool:
                if preview_state["indicator"] is indicator:
                    indicator.destroy()
                    preview_state["indicator"] = None
                return False

            GLib.timeout_add(2200, stop_preview)
            _set_webview_message(webview, t("settings.preview_shown", config), "ok")
        except Exception as exc:
            _set_webview_message(webview, f"{t('settings.preview_failed', config)}: {exc}", "error")

    def handle_capture_hotkey(action_id: str) -> None:
        if action_id not in HOTKEY_SETTINGS_LABELS:
            _set_webview_message(webview, t("settings.hotkey_unknown", config), "error")
            return

        def on_complete(config_value: str, label: str) -> None:
            _run_webview_script(
                webview,
                "window.whisprbarSettings && "
                f"window.whisprbarSettings.setHotkey({json.dumps(action_id)}, "
                f"{json.dumps(config_value)}, {json.dumps(label)});",
            )

        def on_cancel() -> None:
            _set_webview_message(webview, t("settings.hotkey_cancelled", config), "error")

        try:
            capture_hotkey(on_complete=on_complete, on_cancel=on_cancel, notify_user=False)
        except Exception as exc:
            _set_webview_message(webview, f"{t('settings.hotkey_unavailable', config)}: {exc}", "error")

    def on_settings_message(_manager, message) -> None:
        data = _decode_webkit_message(message)
        action = data.get("action")
        if action == "cancel":
            close_window()
            return
        if action == "capture_hotkey":
            handle_capture_hotkey(str(data.get("hotkey_action") or ""))
            return
        if action == "preview_indicator":
            payload = data.get("payload") if isinstance(data.get("payload"), Mapping) else {}
            handle_preview_indicator(payload)
            return
        if action != "save":
            return

        try:
            result = apply_settings_payload(
                config,
                data.get("payload") if isinstance(data.get("payload"), Mapping) else {},
                state=state,
            )
        except Exception as exc:
            notify(f"{t('settings.save_failed', config)}: {exc}")
            _set_webview_message(webview, f"{t('settings.save_failed', config)}: {exc}", "error")
            return

        if not result.ok:
            notify(result.message)
            _set_webview_message(webview, result.message, "error")
            return

        if config.get("auto_paste_enabled") and is_wayland_session():
            notify(t("settings.wayland_clipboard", config))
        notify(result.message)
        _set_webview_message(webview, result.message, "ok")
        if on_save:
            on_save()
        close_window()

    user_content.connect("script-message-received::settings", on_settings_message)

    html = generate_settings_html(
        config,
        dictionary_entries=load_dictionary(),
        snippets=load_snippets(),
        devices=list_input_devices(),
        api_keys={
            "DEEPGRAM_API_KEY": get_env_value("DEEPGRAM_API_KEY"),
            "OPENAI_API_KEY": get_env_value("OPENAI_API_KEY"),
            "ELEVENLABS_API_KEY": get_env_value("ELEVENLABS_API_KEY"),
        },
    )
    webview.load_html(html, "file:///")
    window.connect("destroy", close_window)
    window.show_all()
    _present_settings_window(window)
    with _settings_webview_lock:
        _settings_webview_window = window
    return True


def open_settings_webview_window(
    config: dict,
    state: Optional[dict] = None,
    on_save: Optional[Callable[[], None]] = None,
) -> bool:
    """Backward-compatible name for the WebKit settings window."""

    return open_settings_window(config, state, on_save=on_save)


def main() -> None:
    """Run the experimental settings preview as a standalone window."""

    from whisprbar.config import load_config

    config = load_config()
    if open_settings_window(config, {}, quit_on_destroy=True):
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        Gtk.main()


if __name__ == "__main__":
    main()
