from whisprbar.flow.models import DictionaryEntry, Snippet
from whisprbar.ui.settings_webview import apply_settings_payload, generate_settings_html


def test_generate_settings_html_contains_selected_settings_shell():
    html = generate_settings_html(
        {
            "theme_preference": "dark",
            "language": "de",
            "transcription_backend": "deepgram",
            "flow_mode_enabled": True,
            "flow_dictionary_enabled": True,
            "flow_snippets_enabled": False,
        },
        dictionary_entries=[],
        snippets=[],
    )

    assert "WhisprBar Einstellungen" in html
    assert "data-page=\"general\"" in html
    assert "data-page=\"flow\"" in html
    assert "Flow-Modus" in html
    assert "Deepgram Nova-3" in html
    assert "checked" in html


def test_generate_settings_html_uses_english_ui_when_language_is_english():
    html = generate_settings_html(
        {
            "language": "en",
            "flow_mode_enabled": True,
        },
        dictionary_entries=[],
        snippets=[],
    )

    assert "WhisprBar Settings" in html
    assert "Save Changes" in html
    assert "Recording" in html
    assert "Transcription" in html
    assert "Privacy" in html
    assert "Einstellungen" not in html
    assert "Speichern" not in html


def test_generate_settings_html_uses_german_ui_when_language_is_german():
    html = generate_settings_html(
        {
            "language": "de",
            "flow_mode_enabled": True,
        },
        dictionary_entries=[],
        snippets=[],
    )

    assert "WhisprBar Einstellungen" in html
    assert "Änderungen speichern" in html
    assert "Aufnahme" in html
    assert "Transkription" in html
    assert "Datenschutz" in html
    assert "WhisprBar Settings" not in html
    assert "Save Changes" not in html


def test_generate_settings_html_escapes_dictionary_and_snippet_values():
    html = generate_settings_html(
        {"flow_mode_enabled": True},
        dictionary_entries=[
            DictionaryEntry(spoken="<Vispaba>", written="WhisprBar & Flow"),
        ],
        snippets=[
            Snippet(trigger="sig <x>", text="Best & regards"),
        ],
    )

    assert "&lt;Vispaba&gt;" in html
    assert "WhisprBar &amp; Flow" in html
    assert "sig &lt;x&gt;" in html
    assert "Best &amp; regards" in html
    assert "<Vispaba>" not in html


def test_generate_settings_html_uses_monitor_polished_density_tokens():
    html = generate_settings_html(
        {"flow_mode_enabled": True},
        dictionary_entries=[],
        snippets=[],
    )

    assert 'class="wb-frame wb-polished"' in html
    assert "--window-min-width: 1080px" in html
    assert "font-size: 14px" in html
    assert "grid-template-columns: 218px minmax(0, 1fr)" in html


def test_generate_settings_html_shows_voice_commands_from_command_specs():
    html = generate_settings_html(
        {"language": "de", "flow_mode_enabled": True},
        dictionary_entries=[],
        snippets=[],
    )

    assert "data-page=\"voice-commands\"" in html
    assert "data-page-id=\"voice-commands\"" in html
    assert "Sprachbefehle" in html
    assert "KI-Bearbeitung" in html
    assert "Einfüge- und Steuerbefehle" in html
    assert "correct my english" in html
    assert "mach das menschlicher" in html
    assert "drücke enter" in html
    assert "Nutzt AI-Umschreiben" in html
    assert "Keine KI" in html
    assert "settings.command_mode" not in html


def test_generate_settings_html_keeps_settings_sidebar_fixed_while_main_scrolls():
    html = generate_settings_html(
        {"flow_mode_enabled": True},
        dictionary_entries=[],
        snippets=[],
    )

    assert ".wb-shell {" in html
    assert "height: calc(100vh - 52px)" in html
    assert ".wb-sidebar {" in html
    assert "position: sticky" in html
    assert "overflow-y: auto" in html
    assert ".wb-main {" in html


def test_generate_settings_html_marks_dependent_rows_for_dynamic_visibility():
    html = generate_settings_html(
        {
            "transcription_backend": "openai",
            "use_vad": False,
            "noise_reduction_enabled": False,
            "postprocess_enabled": False,
            "flow_rewrite_enabled": False,
            "flow_history_storage": "normal",
            "live_overlay_enabled": False,
        },
        dictionary_entries=[],
        snippets=[],
    )

    assert 'name="faster_whisper_model"' in html
    assert 'data-visible-when="transcription_backend=faster_whisper"' in html
    assert 'name="streaming_model"' in html
    assert 'data-visible-when="transcription_backend=streaming"' in html
    assert 'name="vad_energy_ratio"' in html
    assert 'data-visible-when="use_vad=true"' in html
    assert 'name="noise_reduction_strength"' in html
    assert 'data-visible-when="noise_reduction_enabled=true"' in html
    assert 'name="postprocess_fix_spacing"' in html
    assert 'data-visible-when="postprocess_enabled=true"' in html
    assert 'name="flow_rewrite_model"' in html
    assert 'data-visible-when="flow_rewrite_enabled=true"' in html
    assert 'name="flow_history_auto_delete_hours"' in html
    assert 'data-visible-when="flow_history_storage=auto_delete"' in html
    assert 'name="live_overlay_width"' in html
    assert 'data-visible-when="live_overlay_enabled=true"' in html
    assert "syncDependentRows" in html


def test_generate_settings_html_adds_numeric_bounds_and_units():
    html = generate_settings_html(
        {"flow_mode_enabled": True},
        dictionary_entries=[],
        snippets=[],
    )

    assert 'name="paste_delay_ms" value="250" min="0" max="5000" step="50"' in html
    assert '<span class="wb-unit">ms</span>' in html
    assert 'name="recording_indicator_opacity" value="0.85" min="0.3" max="1" step="0.05"' in html
    assert '<span class="wb-unit">px</span>' in html
    assert 'name="flow_rewrite_timeout_seconds" value="12.0" min="1" max="60" step="0.5"' in html
    assert '<span class="wb-unit">s</span>' in html


def test_generate_settings_html_adds_basic_accessibility_affordances():
    html = generate_settings_html(
        {"flow_mode_enabled": True},
        dictionary_entries=[],
        snippets=[],
    )

    assert 'id="settings-message" class="wb-message" role="status" aria-live="polite"' in html
    assert 'data-page="general" aria-current="page"' in html
    assert 'data-remove-row aria-label=' in html
    assert "setAttribute('aria-current', item === button ? 'page' : 'false')" in html


def test_apply_settings_payload_updates_config_env_and_flow_files():
    config = {
        "hotkeys": {
            "toggle_recording": "F9",
            "open_settings": "F10",
        },
        "hotkey": "F9",
        "recording_indicator_enabled": True,
        "recording_indicator_position": "top-center",
        "recording_indicator_width": 240,
        "recording_indicator_height": 30,
        "recording_indicator_opacity": 0.85,
    }
    state = {"wayland_notice_shown": True}
    saved_config = []
    env_values = {}
    saved_dictionary = []
    saved_snippets = []
    updated_devices = []

    result = apply_settings_payload(
        config,
        {
            "settings": {
                "theme_preference": "dark",
                "language": "en",
                "auto_paste_enabled": True,
                "notifications_enabled": False,
                "paste_sequence": "ctrl_v",
                "paste_delay_ms": "125",
                "device_name": "Studio Mic",
                "noise_reduction_enabled": False,
                "noise_reduction_strength": "0.4",
                "audio_feedback_enabled": True,
                "audio_feedback_volume": "0.6",
                "transcription_backend": "deepgram",
                "faster_whisper_model": "small",
                "streaming_model": "base",
                "use_vad": True,
                "vad_energy_ratio": "0.055",
                "vad_bridge_ms": "240",
                "vad_min_energy_frames": "3",
                "vad_auto_stop_enabled": True,
                "vad_auto_stop_silence_seconds": "3.5",
                "stop_tail_grace_ms": "650",
                "min_audio_energy": "0.0012",
                "postprocess_enabled": True,
                "postprocess_fix_spacing": True,
                "postprocess_fix_capitalization": False,
                "chunking_enabled": False,
                "recording_indicator_enabled": False,
                "recording_indicator_position": "bottom-center",
                "recording_indicator_width": "320",
                "recording_indicator_height": "42",
                "recording_indicator_opacity": "0.7",
                "live_overlay_enabled": True,
                "live_overlay_font_size": "18",
                "live_overlay_opacity": "0.8",
                "live_overlay_width": "500",
                "live_overlay_height": "180",
                "live_overlay_display_duration": "4.5",
                "flow_mode_enabled": True,
                "flow_context_awareness_enabled": True,
                "flow_dictionary_enabled": True,
                "flow_snippets_enabled": True,
                "flow_command_mode_enabled": True,
                "flow_smart_formatting_enabled": True,
                "flow_backtrack_enabled": True,
                "flow_press_enter_enabled": True,
                "flow_rewrite_enabled": True,
                "flow_rewrite_provider": "openai_compatible",
                "flow_rewrite_model": "gpt-test",
                "flow_rewrite_timeout_seconds": "9",
                "flow_default_profile": "chat",
                "flow_history_storage": "auto_delete",
                "flow_preferred_languages": "de, en, fr",
                "flow_language_auto_detect": True,
                "flow_max_recording_minutes": "12",
            },
            "hotkeys": {
                "toggle_recording": "CTRL_R",
                "open_settings": "F10",
                "show_history": "CTRL+H",
            },
            "api_keys": {
                "DEEPGRAM_API_KEY": "dg-key",
                "OPENAI_API_KEY": "",
                "ELEVENLABS_API_KEY": "el-key",
            },
            "dictionary": [
                {"spoken": "Vispaba", "written": "WhisprBar"},
                {"spoken": "", "written": "ignored"},
            ],
            "snippets": [
                {"trigger": "signatur", "text": "Viele Grüße"},
                {"trigger": "", "text": "ignored"},
            ],
        },
        state=state,
        save_config_func=lambda: saved_config.append(True),
        save_env_func=lambda key, value: env_values.__setitem__(key, value),
        save_dictionary_func=lambda entries: saved_dictionary.extend(entries),
        save_snippets_func=lambda entries: saved_snippets.extend(entries),
        update_device_func=lambda: updated_devices.append(True),
        reset_indicator_func=lambda: None,
        vad_available=True,
        noise_reduction_available=True,
    )

    assert result.ok is True
    assert config["theme_preference"] == "dark"
    assert config["language"] == "en"
    assert config["hotkeys"]["toggle_recording"] == "CTRL_R"
    assert config["hotkey"] == "CTRL_R"
    assert config["device_name"] == "Studio Mic"
    assert config["flow_preferred_languages"] == ["de", "en", "fr"]
    assert config["flow_rewrite_model"] == "gpt-test"
    assert env_values == {
        "DEEPGRAM_API_KEY": "dg-key",
        "OPENAI_API_KEY": "",
        "ELEVENLABS_API_KEY": "el-key",
    }
    assert saved_dictionary == [DictionaryEntry(spoken="Vispaba", written="WhisprBar")]
    assert saved_snippets == [Snippet(trigger="signatur", text="Viele Grüße")]
    assert saved_config == [True]
    assert updated_devices == [True]
    assert state["wayland_notice_shown"] is False


def test_apply_settings_payload_rejects_hotkey_conflicts_without_writing():
    config = {"hotkeys": {"toggle_recording": "F9"}, "hotkey": "F9"}
    saved_config = []

    result = apply_settings_payload(
        config,
        {
            "settings": {},
            "hotkeys": {
                "toggle_recording": "F9",
                "open_settings": "F9",
            },
            "api_keys": {},
            "dictionary": [],
            "snippets": [],
        },
        save_config_func=lambda: saved_config.append(True),
        save_env_func=lambda _key, _value: None,
        save_dictionary_func=lambda _entries: None,
        save_snippets_func=lambda _entries: None,
        update_device_func=lambda: None,
    )

    assert result.ok is False
    assert "Hotkey-Konflikt" in result.message
    assert saved_config == []


def test_apply_settings_payload_clamps_runtime_sensitive_values():
    config = {"hotkeys": {"toggle_recording": "F9"}, "hotkey": "F9"}

    result = apply_settings_payload(
        config,
        {
            "settings": {
                "paste_delay_ms": "999999",
                "noise_reduction_strength": "5",
                "audio_feedback_volume": "-1",
                "vad_energy_ratio": "3",
                "vad_bridge_ms": "-10",
                "vad_min_energy_frames": "99",
                "vad_auto_stop_silence_seconds": "99",
                "stop_tail_grace_ms": "9999",
                "min_audio_energy": "1",
                "recording_indicator_width": "9999",
                "recording_indicator_height": "-4",
                "recording_indicator_opacity": "9",
                "live_overlay_font_size": "99",
                "live_overlay_opacity": "-4",
                "live_overlay_width": "9999",
                "live_overlay_height": "-20",
                "live_overlay_display_duration": "99",
                "flow_rewrite_timeout_seconds": "999",
                "flow_history_auto_delete_hours": "99999",
                "flow_recent_copy_seconds": "-2",
                "flow_max_recording_minutes": "999",
            },
            "hotkeys": {},
            "api_keys": {},
            "dictionary": [],
            "snippets": [],
        },
        save_config_func=lambda: None,
        save_env_func=lambda _key, _value: None,
        save_dictionary_func=lambda _entries: None,
        save_snippets_func=lambda _entries: None,
        update_device_func=lambda: None,
        reset_indicator_func=lambda: None,
    )

    assert result.ok is True
    assert config["paste_delay_ms"] == 5000
    assert config["noise_reduction_strength"] == 1.0
    assert config["audio_feedback_volume"] == 0.0
    assert config["vad_energy_ratio"] == 0.3
    assert config["vad_bridge_ms"] == 0
    assert config["vad_min_energy_frames"] == 10
    assert config["vad_auto_stop_silence_seconds"] == 30.0
    assert config["stop_tail_grace_ms"] == 2000
    assert config["min_audio_energy"] == 0.01
    assert config["recording_indicator_width"] == 600
    assert config["recording_indicator_height"] == 10
    assert config["recording_indicator_opacity"] == 1.0
    assert config["live_overlay_font_size"] == 32
    assert config["live_overlay_opacity"] == 0.3
    assert config["live_overlay_width"] == 800
    assert config["live_overlay_height"] == 100
    assert config["live_overlay_display_duration"] == 10.0
    assert config["flow_rewrite_timeout_seconds"] == 60.0
    assert config["flow_history_auto_delete_hours"] == 720
    assert config["flow_recent_copy_seconds"] == 1
    assert config["flow_max_recording_minutes"] == 60


def test_ui_exports_webview_settings_as_default():
    from whisprbar import ui

    assert ui.open_settings_window.__module__ == "whisprbar.ui.settings_webview"
