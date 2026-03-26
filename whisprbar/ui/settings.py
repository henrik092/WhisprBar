"""Settings dialog for WhisprBar."""

#!/usr/bin/env python3
"""
whisprbar/ui.py - GUI components (settings, overlay, diagnostics)

This module handles all user interface components:
- Settings dialog with all configuration options
- Live transcription overlay window
- First-run diagnostics wizard
"""

from typing import Optional, Callable, List
import sys
import threading

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib, Pango
    import cairo
except (ImportError, ValueError):
    Gtk = Gdk = GLib = Pango = None
    cairo = None

# Import from other whisprbar modules
from whisprbar.config import save_config, cfg, get_env_value, save_env_file_value
from whisprbar.utils import (
    collect_diagnostics,
    DiagnosticResult,
    STATUS_OK,
    STATUS_WARN,
    STATUS_ERROR,
    STATUS_ICON_NAME,
    CLI_STATUS_LABEL,
    APP_NAME,
    notify,
    read_history,
    clear_history,
    copy_to_clipboard,
)
from whisprbar.audio import list_input_devices, update_device_index
from whisprbar.hotkeys import capture_hotkey, cancel_hotkey_capture
from whisprbar.hotkey_actions import HOTKEY_SETTINGS_LABELS
from whisprbar.ui_hotkeys import (
    build_hotkey_conflict_message,
    build_pending_hotkeys,
    get_hotkey_conflicts_for_actions,
)
from whisprbar.paste import PASTE_OPTIONS, is_wayland_session

# Module state - window references
_overlay_window = None
_overlay_window_lock = threading.Lock()
_settings_window = None
_settings_window_lock = threading.Lock()
_diagnostics_window = None
_history_window = None

# Check VAD availability
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False


# =============================================================================
# Theme Detection and Styling
# =============================================================================

from .helpers import make_row, build_switch
from .theme import apply_theme_css, get_effective_theme

# =============================================================================
# Settings Window
# =============================================================================

def open_settings_window(cfg: dict, state: dict, on_save: Optional[Callable] = None) -> None:
    """
    Open settings window with tabbed configuration interface.

    Tabs:
    - Basis: Theme, Language, Hotkeys, Auto-Paste, Notifications
    - Audio: Input Device, Noise Reduction, Audio Feedback
    - Transcription: Backend selection, API keys, Model selection
    - Erweitert: VAD, Chunking, Overlay, Postprocessing

    Args:
        cfg: Configuration dictionary
        state: Application state dictionary
        on_save: Optional callback to invoke after saving settings
    """
    global _settings_window

    try:
        from gi.repository import Gtk, GLib
    except Exception as exc:
        notify("GTK unavailable: cannot open settings window.")
        print(f"[WARN] Settings window unavailable: {exc}", file=sys.stderr)
        return

    # Thread-safe check
    with _settings_window_lock:
        if _settings_window is not None:
            window_ref = _settings_window
            GLib.idle_add(lambda: window_ref.present() or False)
            return

    def _present_settings() -> bool:
        global _settings_window

        # Thread-safe double-check
        with _settings_window_lock:
            if _settings_window is not None:
                _settings_window.present()
                return False

        devices = list_input_devices()
        device_map = {"__default__": None}

        window = Gtk.Window(title=f"{APP_NAME} Settings")
        window.set_position(Gtk.WindowPosition.CENTER)
        window.set_resizable(True)
        window.set_default_size(550, 600)

        # Apply theme
        theme = get_effective_theme(cfg)
        apply_theme_css(window, theme)

        # Main vertical container
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        window.add(main_vbox)

        # Helper functions for creating rows
        def make_row(
            label_text: str,
            widget: Gtk.Widget,
            tooltip: Optional[str] = None,
            expand: bool = False,
            defaults_text: Optional[str] = None,
        ) -> Gtk.Box:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            lbl = Gtk.Label(label=label_text)
            lbl.set_xalign(0.0)
            label_box.pack_start(lbl, False, False, 0)
            if tooltip:
                try:
                    info_icon = Gtk.Image.new_from_icon_name("dialog-information", Gtk.IconSize.SMALL_TOOLBAR)
                except Exception:
                    info_icon = Gtk.Label(label="i")
                info_icon.set_tooltip_text(tooltip)
                label_box.pack_start(info_icon, False, False, 0)
            if defaults_text:
                defaults_lbl = Gtk.Label(label=defaults_text)
                defaults_lbl.get_style_context().add_class("dim-label")
                defaults_lbl.set_xalign(0.0)
                label_box.pack_start(defaults_lbl, False, False, 0)
            row.pack_start(label_box, True, True, 0)
            row.pack_start(widget, expand, expand, 0)
            return row

        def build_switch(label_text: str, active: bool, tooltip: Optional[str] = None) -> tuple:
            switch = Gtk.Switch()
            switch.set_active(active)
            if tooltip:
                switch.set_tooltip_text(tooltip)
            row = make_row(label_text, switch, tooltip=tooltip)
            return row, switch

        # Create Notebook (tabbed interface)
        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.TOP)
        main_vbox.pack_start(notebook, True, True, 0)

        # =====================================================================
        # TAB 1: Basis (Basic Settings)
        # =====================================================================
        basis_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        basis_page.set_border_width(12)
        notebook.append_page(basis_page, Gtk.Label(label="Basis"))

        # Theme selection
        theme_combo = Gtk.ComboBoxText()
        theme_combo.append("auto", "Auto (Systemeinstellung)")
        theme_combo.append("light", "Hell")
        theme_combo.append("dark", "Dunkel")
        active_theme = cfg.get("theme_preference", "auto")
        theme_combo.set_active_id(active_theme)
        theme_tooltip = "Wähle UI-Theme: Auto folgt Systemeinstellungen"
        basis_page.pack_start(make_row("Theme", theme_combo, tooltip=theme_tooltip), False, False, 0)

        theme_note = Gtk.Label(label="(Theme-Änderungen erfordern Neustart)")
        theme_note.set_xalign(0.0)
        theme_note.get_style_context().add_class("dim-label")
        basis_page.pack_start(theme_note, False, False, 0)

        # Language selection
        language_combo = Gtk.ComboBoxText()
        language_combo.append("de", "Deutsch (de)")
        language_combo.append("en", "English (en)")
        active_lang = cfg.get("language", "de")
        if active_lang not in {"de", "en"}:
            active_lang = "de"
        language_combo.set_active_id(active_lang)
        language_tooltip = "Sprache für Transkription"
        basis_page.pack_start(make_row("Sprache", language_combo, tooltip=language_tooltip), False, False, 0)

        basis_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Hotkeys section
        hotkeys_section = Gtk.Label()
        hotkeys_section.set_markup("<b>Hotkeys</b>")
        hotkeys_section.set_xalign(0.0)
        basis_page.pack_start(hotkeys_section, False, False, 6)

        # Get hotkeys from config
        from whisprbar.hotkeys import parse_hotkey, hotkey_to_label
        hotkeys_config = cfg.get("hotkeys", {})
        hotkey_actions = HOTKEY_SETTINGS_LABELS.copy()
        pending_hotkeys = build_pending_hotkeys(hotkeys_config, hotkey_actions)

        hotkey_widgets = {}
        capture_state = {"active": False, "current_action": None}

        def finish_hotkey_capture(action_id: str, hotkey_str: str, label: str) -> None:
            capture_state["active"] = False
            capture_state["current_action"] = None
            state["hotkey_capture_active"] = False
            pending_hotkeys[action_id] = hotkey_str
            widgets = hotkey_widgets.get(action_id)
            if widgets:
                widgets["label"].set_text(label)
                widgets["change_btn"].set_label("Ändern")
                widgets["change_btn"].set_sensitive(True)
            for action, wdgs in hotkey_widgets.items():
                wdgs["change_btn"].set_sensitive(True)

        def begin_hotkey_capture(action_id: str) -> None:
            if capture_state["active"]:
                return
            widgets = hotkey_widgets.get(action_id)
            if not widgets:
                return

            previous_hotkey = pending_hotkeys.get(action_id)

            capture_state["active"] = True
            capture_state["current_action"] = action_id
            state["hotkey_capture_active"] = True

            widgets["label"].set_text("Taste drücken...")
            widgets["change_btn"].set_label("Warten...")
            widgets["change_btn"].set_sensitive(False)

            for other_action, other_widgets in hotkey_widgets.items():
                if other_action != action_id:
                    other_widgets["change_btn"].set_sensitive(False)

            try:
                def on_complete(config_str: str, label: str) -> None:
                    finish_hotkey_capture(action_id, config_str, label)

                def on_cancel() -> None:
                    capture_state["active"] = False
                    capture_state["current_action"] = None
                    state["hotkey_capture_active"] = False
                    if previous_hotkey:
                        try:
                            binding = parse_hotkey(previous_hotkey)
                            previous_label = hotkey_to_label(binding)
                        except Exception:
                            previous_label = previous_hotkey
                    else:
                        previous_label = "Nicht gesetzt"
                    widgets["label"].set_text(previous_label)
                    widgets["change_btn"].set_label("Ändern")
                    widgets["change_btn"].set_sensitive(True)
                    for action, wdgs in hotkey_widgets.items():
                        wdgs["change_btn"].set_sensitive(True)

                capture_hotkey(on_complete=on_complete, on_cancel=on_cancel, notify_user=False)
            except Exception as exc:
                capture_state["active"] = False
                capture_state["current_action"] = None
                state["hotkey_capture_active"] = False
                current_hotkey = hotkeys_config.get(action_id)
                if current_hotkey:
                    try:
                        binding = parse_hotkey(current_hotkey)
                        display = hotkey_to_label(binding)
                    except Exception:
                        display = current_hotkey or "Nicht gesetzt"
                else:
                    display = "Nicht gesetzt"
                if widgets:
                    widgets["label"].set_text(display)
                    widgets["change_btn"].set_label("Ändern")
                    widgets["change_btn"].set_sensitive(True)
                for action, wdgs in hotkey_widgets.items():
                    wdgs["change_btn"].set_sensitive(True)
                print(f"[WARN] Hotkey capture failed: {exc}", file=sys.stderr)

        for action_id, action_label in hotkey_actions.items():
            hotkey_str = hotkeys_config.get(action_id)
            if hotkey_str:
                try:
                    hotkey_binding = parse_hotkey(hotkey_str)
                    display_label = hotkey_to_label(hotkey_binding)
                except Exception:
                    display_label = hotkey_str or "Nicht gesetzt"
            else:
                display_label = "Nicht gesetzt"

            hotkey_row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hotkey_value_label = Gtk.Label(label=display_label)
            hotkey_value_label.set_xalign(0.0)
            hotkey_value_label.set_width_chars(15)
            hotkey_row_box.pack_start(hotkey_value_label, False, False, 0)

            change_btn = Gtk.Button(label="Ändern")
            hotkey_row_box.pack_start(change_btn, False, False, 0)

            hotkey_widgets[action_id] = {
                "label": hotkey_value_label,
                "change_btn": change_btn,
            }

            basis_page.pack_start(make_row(action_label, hotkey_row_box), False, False, 0)

        for action_id, widgets in hotkey_widgets.items():
            widgets["change_btn"].connect("clicked", lambda btn, aid=action_id: begin_hotkey_capture(aid))

        basis_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Auto-paste and notifications
        auto_tooltip = "Text automatisch nach Transkription einfügen"
        if is_wayland_session():
            auto_tooltip += " (Wayland: nur Zwischenablage)"
        auto_row, auto_switch = build_switch("Auto-Paste", cfg.get("auto_paste_enabled", False), auto_tooltip)
        basis_page.pack_start(auto_row, False, False, 0)

        notify_tooltip = "Desktop-Benachrichtigungen anzeigen"
        notify_row, notify_switch = build_switch("Benachrichtigungen", cfg.get("notifications_enabled", True), notify_tooltip)
        basis_page.pack_start(notify_row, False, False, 0)

        # Paste settings (sub-options)
        paste_combo = Gtk.ComboBoxText()
        for key, label in PASTE_OPTIONS.items():
            paste_combo.append(key, label)
        paste_combo.set_active_id(cfg.get("paste_sequence", "auto"))
        if is_wayland_session():
            paste_combo.set_sensitive(False)
        paste_row = make_row("  Paste-Modus", paste_combo, tooltip="Methode für Auto-Paste")
        basis_page.pack_start(paste_row, False, False, 0)

        paste_delay_adjustment = Gtk.Adjustment(value=float(cfg.get("paste_delay_ms", 250) or 0), lower=0.0, upper=2000.0, step_increment=25.0, page_increment=100.0)
        paste_delay_spin = Gtk.SpinButton()
        paste_delay_spin.set_adjustment(paste_delay_adjustment)
        paste_delay_spin.set_numeric(True)
        paste_delay_spin.set_value(float(cfg.get("paste_delay_ms", 250) or 0))
        paste_delay_spin.set_digits(0)
        paste_delay_row = make_row("  Paste-Verzögerung (ms)", paste_delay_spin, defaults_text="(Standard: 250)")
        basis_page.pack_start(paste_delay_row, False, False, 0)

        def sync_paste_options(*_args) -> None:
            active = auto_switch.get_active()
            paste_row.set_visible(active)
            paste_delay_row.set_visible(active)

        auto_switch.connect("notify::active", sync_paste_options)
        sync_paste_options()

        # =====================================================================
        # TAB 2: Audio
        # =====================================================================
        audio_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        audio_page.set_border_width(12)
        notebook.append_page(audio_page, Gtk.Label(label="Audio"))

        # Input device
        device_combo = Gtk.ComboBoxText()
        device_combo.append("__default__", "System-Standard")
        active_device_id = "__default__"
        saved_name = cfg.get("device_name")
        for device in devices:
            device_id = str(device.get("index"))
            device_name = device.get("name") or f"Gerät {device_id}"
            device_map[device_id] = device_name
            device_combo.append(device_id, device_name)
            if saved_name and device_name.lower() == saved_name.lower():
                active_device_id = device_id
        device_combo.set_active_id(active_device_id)
        audio_page.pack_start(make_row("Eingabegerät", device_combo, tooltip="Mikrofon für Aufnahme"), False, False, 0)

        audio_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Noise Reduction
        noise_reduction_available = True
        try:
            import noisereduce
        except ImportError:
            noise_reduction_available = False

        nr_tooltip = "Hintergrundgeräusche vor Transkription entfernen" if noise_reduction_available else "Paket 'noisereduce' nicht installiert"
        nr_row, nr_switch = build_switch("Rauschunterdrückung", cfg.get("noise_reduction_enabled", True) and noise_reduction_available, nr_tooltip)
        nr_switch.set_sensitive(noise_reduction_available)
        audio_page.pack_start(nr_row, False, False, 0)

        nr_strength = float(cfg.get("noise_reduction_strength", 0.7) or 0.7)
        nr_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        nr_scale.set_digits(1)
        nr_scale.set_value(max(0.0, min(1.0, nr_strength)))
        nr_scale.set_draw_value(True)
        nr_scale.set_value_pos(Gtk.PositionType.RIGHT)
        nr_scale.set_hexpand(True)
        nr_scale.clear_marks()
        nr_scale.connect("format-value", lambda scale, value: f"{int(value * 100)}%")
        nr_strength_row = make_row("  Stärke", nr_scale, expand=True, defaults_text="(Standard: 70%)")
        audio_page.pack_start(nr_strength_row, False, False, 0)

        def sync_nr_controls(*_args) -> None:
            active = nr_switch.get_active() and noise_reduction_available
            nr_strength_row.set_visible(active)

        nr_switch.connect("notify::active", sync_nr_controls)
        sync_nr_controls()

        audio_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Audio Feedback
        audio_fb_tooltip = "Töne bei Aufnahme-Start, Stopp und Abschluss abspielen"
        audio_fb_row, audio_fb_switch = build_switch("Audio-Feedback", cfg.get("audio_feedback_enabled", True), audio_fb_tooltip)
        audio_page.pack_start(audio_fb_row, False, False, 0)

        audio_fb_volume = float(cfg.get("audio_feedback_volume", 0.3) or 0.3)
        audio_fb_volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        audio_fb_volume_scale.set_digits(1)
        audio_fb_volume_scale.set_value(max(0.0, min(1.0, audio_fb_volume)))
        audio_fb_volume_scale.set_draw_value(True)
        audio_fb_volume_scale.set_value_pos(Gtk.PositionType.RIGHT)
        audio_fb_volume_scale.set_hexpand(True)
        audio_fb_volume_scale.clear_marks()
        audio_fb_volume_scale.connect("format-value", lambda scale, value: f"{int(value * 100)}%")
        audio_fb_volume_row = make_row("  Lautstärke", audio_fb_volume_scale, expand=True, defaults_text="(Standard: 30%)")
        audio_page.pack_start(audio_fb_volume_row, False, False, 0)

        def sync_audio_fb_controls(*_args) -> None:
            active = audio_fb_switch.get_active()
            audio_fb_volume_row.set_visible(active)

        audio_fb_switch.connect("notify::active", sync_audio_fb_controls)
        sync_audio_fb_controls()

        # =====================================================================
        # TAB 3: Transcription
        # =====================================================================
        trans_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        trans_page.set_border_width(12)
        notebook.append_page(trans_page, Gtk.Label(label="Transkription"))

        # Backend selection with speed indicators
        backend_combo = Gtk.ComboBoxText()
        backend_combo.append("deepgram", "Deepgram Nova-3 (⚡ <300ms, online)")
        backend_combo.append("elevenlabs", "ElevenLabs Scribe v2 (⚡ ~500ms, online)")
        backend_combo.append("openai", "OpenAI Whisper (2-4s, beste Qualität)")
        backend_combo.append("faster_whisper", "faster-whisper (offline, lokal)")
        backend_combo.append("streaming", "sherpa-onnx (offline, streaming)")
        active_backend = cfg.get("transcription_backend", "openai")
        backend_combo.set_active_id(active_backend)
        trans_page.pack_start(make_row("Backend", backend_combo, tooltip="Transkriptions-Dienst wählen"), False, False, 0)

        # Speed indicator label
        speed_label = Gtk.Label()
        speed_label.set_xalign(0.0)
        speed_label.get_style_context().add_class("dim-label")

        def update_speed_label(*_args):
            backend = backend_combo.get_active_id()
            if backend == "deepgram":
                speed_label.set_markup("<small>⚡ Schnellstes Backend: sub-300ms Latenz</small>")
            elif backend == "elevenlabs":
                speed_label.set_markup("<small>⚡ Sehr schnell: ~500ms-1s Latenz</small>")
            elif backend == "openai":
                speed_label.set_markup("<small>🐌 Langsam aber beste Qualität: 2-4s Latenz</small>")
            elif backend == "faster_whisper":
                speed_label.set_markup("<small>💻 Offline: Geschwindigkeit abhängig von Hardware</small>")
            else:
                speed_label.set_markup("<small>💻 Offline Streaming</small>")

        backend_combo.connect("changed", update_speed_label)
        update_speed_label()
        trans_page.pack_start(speed_label, False, False, 0)

        trans_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # API Keys Section
        api_section = Gtk.Label()
        api_section.set_markup("<b>API-Schlüssel</b>")
        api_section.set_xalign(0.0)
        trans_page.pack_start(api_section, False, False, 6)

        api_note = Gtk.Label(label="Gespeichert in ~/.config/whisprbar.env")
        api_note.set_xalign(0.0)
        api_note.get_style_context().add_class("dim-label")
        trans_page.pack_start(api_note, False, False, 0)

        def create_api_key_row(key_name: str, placeholder: str, env_key: str, get_url: str) -> tuple:
            key_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            key_entry = Gtk.Entry()
            key_entry.set_placeholder_text(placeholder)
            key_entry.set_visibility(False)
            key_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            current_key = get_env_value(env_key)
            if current_key:
                key_entry.set_text(current_key)
            key_entry.set_hexpand(True)
            key_box.pack_start(key_entry, True, True, 0)

            paste_btn = Gtk.Button(label="📋")
            paste_btn.set_tooltip_text("Aus Zwischenablage einfügen")
            def on_paste(_button, entry=key_entry):
                try:
                    import pyperclip
                    clipboard_text = pyperclip.paste()
                    if clipboard_text:
                        entry.set_text(clipboard_text.strip())
                except Exception as exc:
                    print(f"[WARN] Clipboard paste failed: {exc}", file=sys.stderr)
            paste_btn.connect("clicked", on_paste)
            key_box.pack_start(paste_btn, False, False, 0)

            show_btn = Gtk.Button(label="👁")
            show_btn.set_tooltip_text("Anzeigen/Verbergen")
            def on_toggle(_button, entry=key_entry, btn=show_btn):
                visible = entry.get_visibility()
                entry.set_visibility(not visible)
                btn.set_label("🙈" if not visible else "👁")
            show_btn.connect("clicked", on_toggle)
            key_box.pack_start(show_btn, False, False, 0)

            row = make_row(key_name, key_box, tooltip=f"Holen von: {get_url}")
            return row, key_entry

        # Deepgram API Key
        deepgram_key_row, deepgram_key_entry = create_api_key_row(
            "Deepgram API Key", "...", "DEEPGRAM_API_KEY", "https://console.deepgram.com"
        )
        trans_page.pack_start(deepgram_key_row, False, False, 0)

        # OpenAI API Key
        openai_key_row, openai_key_entry = create_api_key_row(
            "OpenAI API Key", "sk-...", "OPENAI_API_KEY", "https://platform.openai.com/api-keys"
        )
        trans_page.pack_start(openai_key_row, False, False, 0)

        # ElevenLabs API Key
        elevenlabs_key_row, elevenlabs_key_entry = create_api_key_row(
            "ElevenLabs API Key", "...", "ELEVENLABS_API_KEY", "https://elevenlabs.io/api"
        )
        trans_page.pack_start(elevenlabs_key_row, False, False, 0)

        def update_api_key_visibility(*_args):
            backend = backend_combo.get_active_id()
            deepgram_key_row.set_visible(backend == "deepgram")
            openai_key_row.set_visible(backend == "openai")
            elevenlabs_key_row.set_visible(backend == "elevenlabs")
            show_api = backend in ["deepgram", "openai", "elevenlabs"]
            api_section.set_visible(show_api)
            api_note.set_visible(show_api)

        backend_combo.connect("changed", update_api_key_visibility)
        update_api_key_visibility()

        trans_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Model selection for offline backends
        model_section = Gtk.Label()
        model_section.set_markup("<b>Modell-Einstellungen</b>")
        model_section.set_xalign(0.0)
        trans_page.pack_start(model_section, False, False, 6)

        fw_model_combo = Gtk.ComboBoxText()
        fw_model_combo.append("tiny", "Tiny (~1GB RAM)")
        fw_model_combo.append("base", "Base (~1GB RAM)")
        fw_model_combo.append("small", "Small (~2GB RAM)")
        fw_model_combo.append("medium", "Medium (~5GB RAM)")
        fw_model_combo.append("large", "Large (~10GB RAM)")
        active_model = cfg.get("faster_whisper_model", "medium")
        fw_model_combo.set_active_id(active_model)
        fw_model_row = make_row("faster-whisper Modell", fw_model_combo)
        trans_page.pack_start(fw_model_row, False, False, 0)

        streaming_model_combo = Gtk.ComboBoxText()
        streaming_model_combo.append("tiny", "Tiny (schnellstes)")
        streaming_model_combo.append("base", "Base")
        streaming_model_combo.append("small", "Small")
        streaming_model_combo.append("medium", "Medium")
        active_streaming_model = cfg.get("streaming_model", "tiny")
        streaming_model_combo.set_active_id(active_streaming_model)
        streaming_model_row = make_row("sherpa-onnx Modell", streaming_model_combo)
        trans_page.pack_start(streaming_model_row, False, False, 0)

        def update_model_visibility(*_args):
            backend = backend_combo.get_active_id()
            fw_model_row.set_visible(backend == "faster_whisper")
            streaming_model_row.set_visible(backend == "streaming")
            show_models = backend in ["faster_whisper", "streaming"]
            model_section.set_visible(show_models)

        backend_combo.connect("changed", update_model_visibility)
        update_model_visibility()

        # =====================================================================
        # TAB 4: Erweitert (Advanced)
        # =====================================================================
        adv_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        adv_page.set_border_width(12)

        # Wrap in ScrolledWindow for long content
        adv_scroll = Gtk.ScrolledWindow()
        adv_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        adv_scroll.add(adv_page)
        notebook.append_page(adv_scroll, Gtk.Label(label="Erweitert"))

        # VAD Section
        vad_section = Gtk.Label()
        vad_section.set_markup("<b>Sprachaktivitätserkennung (VAD)</b>")
        vad_section.set_xalign(0.0)
        adv_page.pack_start(vad_section, False, False, 0)

        vad_tooltip = "Stille entfernen für schnellere Verarbeitung" if VAD_AVAILABLE else "Paket 'webrtcvad' nicht installiert"
        vad_row, vad_switch = build_switch("VAD aktivieren", cfg.get("use_vad", False) and VAD_AVAILABLE, vad_tooltip)
        vad_switch.set_sensitive(VAD_AVAILABLE)
        adv_page.pack_start(vad_row, False, False, 0)

        vad_rows: List[Gtk.Widget] = []

        vad_sensitivity = float(cfg.get("vad_energy_ratio", 0.02) or 0.02)
        vad_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.01, 0.2, 0.005)
        vad_scale.set_digits(3)
        vad_scale.set_value(max(0.01, min(0.2, vad_sensitivity)))
        vad_scale.set_draw_value(True)
        vad_scale.set_value_pos(Gtk.PositionType.RIGHT)
        vad_scale.set_hexpand(True)
        sensitivity_row = make_row("  Empfindlichkeit", vad_scale, expand=True, defaults_text="(Standard: 0.02)")
        vad_rows.append(sensitivity_row)
        adv_page.pack_start(sensitivity_row, False, False, 0)

        bridge_default = int(cfg.get("vad_bridge_ms", 180) or 180)
        bridge_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 400.0, 10.0)
        bridge_scale.set_digits(0)
        bridge_scale.set_value(max(0.0, min(400.0, float(bridge_default))))
        bridge_scale.set_draw_value(True)
        bridge_scale.set_value_pos(Gtk.PositionType.RIGHT)
        bridge_scale.set_hexpand(True)
        bridge_scale.clear_marks()
        bridge_scale.connect("format-value", lambda scale, value: f"{int(value)} ms")
        bridge_row = make_row("  Pausen-Brücke (ms)", bridge_scale, expand=True, defaults_text="(Standard: 180)")
        vad_rows.append(bridge_row)
        adv_page.pack_start(bridge_row, False, False, 0)

        min_frames_default = int(cfg.get("vad_min_energy_frames", 2) or 2)
        frames_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 8.0, 1.0)
        frames_scale.set_digits(0)
        frames_scale.set_value(max(1.0, min(8.0, float(min_frames_default))))
        frames_scale.set_draw_value(True)
        frames_scale.set_value_pos(Gtk.PositionType.RIGHT)
        frames_scale.set_hexpand(True)
        frames_row = make_row("  Rausch-Schutz (Frames)", frames_scale, expand=True, defaults_text="(Standard: 2)")
        vad_rows.append(frames_row)
        adv_page.pack_start(frames_row, False, False, 0)

        auto_stop_row, auto_stop_switch = build_switch("  Auto-Stop bei Stille", cfg.get("vad_auto_stop_enabled", False) and VAD_AVAILABLE, "Aufnahme automatisch bei Stille stoppen")
        auto_stop_switch.set_sensitive(VAD_AVAILABLE)
        vad_rows.append(auto_stop_row)
        adv_page.pack_start(auto_stop_row, False, False, 0)

        auto_stop_silence_seconds = float(cfg.get("vad_auto_stop_silence_seconds", 2.0) or 2.0)
        auto_stop_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 10.0, 0.5)
        auto_stop_scale.set_digits(1)
        auto_stop_scale.set_value(max(0.5, min(10.0, auto_stop_silence_seconds)))
        auto_stop_scale.set_draw_value(True)
        auto_stop_scale.set_value_pos(Gtk.PositionType.RIGHT)
        auto_stop_scale.set_hexpand(True)
        auto_stop_scale.clear_marks()
        auto_stop_scale.connect("format-value", lambda scale, value: f"{value:.1f} s")
        auto_stop_duration_row = make_row("    Stille-Dauer (s)", auto_stop_scale, expand=True, defaults_text="(Standard: 2.0)")
        vad_rows.append(auto_stop_duration_row)
        adv_page.pack_start(auto_stop_duration_row, False, False, 0)

        stop_tail_grace = int(cfg.get("stop_tail_grace_ms", 500) or 500)
        stop_tail_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100.0, 2000.0, 100.0)
        stop_tail_scale.set_digits(0)
        stop_tail_scale.set_value(max(100, min(2000, float(stop_tail_grace))))
        stop_tail_scale.set_draw_value(True)
        stop_tail_scale.set_value_pos(Gtk.PositionType.RIGHT)
        stop_tail_scale.set_hexpand(True)
        stop_tail_scale.clear_marks()
        stop_tail_scale.connect("format-value", lambda scale, value: f"{int(value)} ms")
        stop_tail_row = make_row("  Aufnahme-Puffer (ms)", stop_tail_scale, expand=True, defaults_text="(Standard: 500)")
        vad_rows.append(stop_tail_row)
        adv_page.pack_start(stop_tail_row, False, False, 0)

        def sync_vad_controls(*_args) -> None:
            vad_active = vad_switch.get_active() and VAD_AVAILABLE
            for row in vad_rows:
                row.set_visible(vad_active)
            auto_stop_active = auto_stop_switch.get_active() and vad_active
            auto_stop_duration_row.set_visible(auto_stop_active)

        def sync_auto_stop_controls(*_args) -> None:
            vad_active = vad_switch.get_active() and VAD_AVAILABLE
            auto_stop_active = auto_stop_switch.get_active() and vad_active
            auto_stop_duration_row.set_visible(auto_stop_active)

        vad_switch.connect("notify::active", sync_vad_controls)
        auto_stop_switch.connect("notify::active", sync_auto_stop_controls)
        sync_vad_controls()

        adv_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Hallucination Prevention
        min_energy = float(cfg.get("min_audio_energy", 0.0008) or 0.0008)
        min_energy_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0001, 0.01, 0.0001)
        min_energy_scale.set_digits(4)
        min_energy_scale.set_value(max(0.0001, min(0.01, min_energy)))
        min_energy_scale.set_draw_value(True)
        min_energy_scale.set_value_pos(Gtk.PositionType.RIGHT)
        min_energy_scale.set_hexpand(True)
        min_energy_scale.clear_marks()
        min_energy_row = make_row("Halluzinations-Schutz", min_energy_scale, tooltip="Blockiert Transkription bei zu leiser Audio", expand=True, defaults_text="(Standard: 0.0008)")
        adv_page.pack_start(min_energy_row, False, False, 0)

        adv_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Post-Processing
        pp_section = Gtk.Label()
        pp_section.set_markup("<b>Nachbearbeitung</b>")
        pp_section.set_xalign(0.0)
        adv_page.pack_start(pp_section, False, False, 6)

        pp_row, pp_switch = build_switch("Nachbearbeitung aktivieren", cfg.get("postprocess_enabled", True), "Text nach Transkription bereinigen")
        adv_page.pack_start(pp_row, False, False, 0)

        pp_rows: List[Gtk.Widget] = []

        pp_spacing_row, pp_spacing_switch = build_switch("  Abstände korrigieren", cfg.get("postprocess_fix_spacing", True), "Doppelte Leerzeichen entfernen")
        pp_rows.append(pp_spacing_row)
        adv_page.pack_start(pp_spacing_row, False, False, 0)

        pp_caps_row, pp_caps_switch = build_switch("  Großschreibung korrigieren", cfg.get("postprocess_fix_capitalization", True), "Satzanfänge großschreiben")
        pp_rows.append(pp_caps_row)
        adv_page.pack_start(pp_caps_row, False, False, 0)

        def sync_pp_controls(*_args) -> None:
            active = pp_switch.get_active()
            for row in pp_rows:
                row.set_visible(active)

        pp_switch.connect("notify::active", sync_pp_controls)
        sync_pp_controls()

        adv_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Chunking
        chunking_row, chunking_switch = build_switch("Chunking (lange Aufnahmen)", cfg.get("chunking_enabled", True), "Lange Audio in Teile aufteilen für parallele Verarbeitung")
        adv_page.pack_start(chunking_row, False, False, 0)

        adv_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Recording Indicator section
        ri_section = Gtk.Label()
        ri_section.set_markup("<b>Aufnahme-Indikator</b>")
        ri_section.set_xalign(0.0)
        adv_page.pack_start(ri_section, False, False, 6)

        ri_row, ri_switch = build_switch("Indikator aktivieren", cfg.get("recording_indicator_enabled", True), "Animiertes Aufnahme-Fenster anzeigen")
        adv_page.pack_start(ri_row, False, False, 0)

        ri_rows: List[Gtk.Widget] = []

        # Position combo
        ri_pos_combo = Gtk.ComboBoxText()
        for pid, plabel in [
            ("top-center", "Oben Mitte"), ("top-left", "Oben Links"), ("top-right", "Oben Rechts"),
            ("bottom-center", "Unten Mitte"), ("bottom-left", "Unten Links"), ("bottom-right", "Unten Rechts"),
            ("draggable", "Frei verschiebbar"),
        ]:
            ri_pos_combo.append(pid, plabel)
        ri_pos_combo.set_active_id(cfg.get("recording_indicator_position", "top-center"))
        ri_pos_row = make_row("  Position", ri_pos_combo)
        ri_rows.append(ri_pos_row)
        adv_page.pack_start(ri_pos_row, False, False, 0)

        # Width slider (60 - 600px, default 240)
        ri_width_val = int(cfg.get("recording_indicator_width", 240))
        ri_width = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 60, 600, 10)
        ri_width.set_digits(0)
        ri_width.set_value(max(60, min(600, ri_width_val)))
        ri_width.set_draw_value(True)
        ri_width.set_value_pos(Gtk.PositionType.RIGHT)
        ri_width.set_hexpand(True)
        ri_width.clear_marks()
        ri_width.connect("format-value", lambda scale, value: f"{int(value)}px")
        ri_width_row = make_row("  Breite", ri_width, expand=True, defaults_text="(Standard: 240px)")
        ri_rows.append(ri_width_row)
        adv_page.pack_start(ri_width_row, False, False, 0)

        # Height slider (10 - 100px, default 30)
        ri_height_val = int(cfg.get("recording_indicator_height", 30))
        ri_height = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 100, 2)
        ri_height.set_digits(0)
        ri_height.set_value(max(10, min(100, ri_height_val)))
        ri_height.set_draw_value(True)
        ri_height.set_value_pos(Gtk.PositionType.RIGHT)
        ri_height.set_hexpand(True)
        ri_height.clear_marks()
        ri_height.connect("format-value", lambda scale, value: f"{int(value)}px")
        ri_height_row = make_row("  Hoehe", ri_height, expand=True, defaults_text="(Standard: 30px)")
        ri_rows.append(ri_height_row)
        adv_page.pack_start(ri_height_row, False, False, 0)

        # Opacity slider
        ri_opacity_val = float(cfg.get("recording_indicator_opacity", 0.85))
        ri_opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.3, 1.0, 0.05)
        ri_opacity.set_digits(2)
        ri_opacity.set_value(max(0.3, min(1.0, ri_opacity_val)))
        ri_opacity.set_draw_value(True)
        ri_opacity.set_value_pos(Gtk.PositionType.RIGHT)
        ri_opacity.set_hexpand(True)
        ri_opacity.clear_marks()
        ri_opacity.connect("format-value", lambda scale, value: f"{int(value * 100)}%")
        ri_opacity_row = make_row("  Transparenz", ri_opacity, expand=True, defaults_text="(Standard: 85%)")
        ri_rows.append(ri_opacity_row)
        adv_page.pack_start(ri_opacity_row, False, False, 0)

        # Preview button for recording indicator
        preview_state = {"active": False, "indicator": None}

        def _build_preview_cfg() -> dict:
            """Build a config dict from current slider values for preview."""
            return {
                "recording_indicator_enabled": True,
                "recording_indicator_position": ri_pos_combo.get_active_id() or "top-center",
                "recording_indicator_width": int(ri_width.get_value()),
                "recording_indicator_height": int(ri_height.get_value()),
                "recording_indicator_opacity": round(float(ri_opacity.get_value()), 2),
            }

        def _stop_preview() -> None:
            """Stop the preview indicator."""
            if preview_state["indicator"] is not None:
                preview_state["indicator"].destroy()
                preview_state["indicator"] = None
            preview_state["active"] = False
            preview_btn.set_label("Vorschau anzeigen")

        def _start_preview() -> None:
            """Start/restart the preview indicator with current slider values."""
            from whisprbar.ui.recording_indicator import RecordingIndicator, PHASE_RECORDING
            # Destroy old preview if exists
            if preview_state["indicator"] is not None:
                preview_state["indicator"].destroy()
            preview_cfg = _build_preview_cfg()
            indicator = RecordingIndicator(preview_cfg)
            preview_state["indicator"] = indicator
            preview_state["active"] = True
            indicator.show(PHASE_RECORDING)
            preview_btn.set_label("Vorschau ausblenden")

        def _on_preview_clicked(_button) -> None:
            if preview_state["active"]:
                _stop_preview()
            else:
                _start_preview()

        def _on_ri_slider_changed(*_args) -> None:
            """Update preview in real-time when sliders change."""
            if preview_state["active"]:
                _start_preview()

        preview_btn = Gtk.Button(label="Vorschau anzeigen")
        preview_btn.set_tooltip_text("Zeigt den Aufnahme-Indikator mit den aktuellen Einstellungen")
        preview_btn.connect("clicked", _on_preview_clicked)

        # Connect sliders for live update
        ri_width.connect("value-changed", _on_ri_slider_changed)
        ri_height.connect("value-changed", _on_ri_slider_changed)
        ri_opacity.connect("value-changed", _on_ri_slider_changed)
        ri_pos_combo.connect("changed", _on_ri_slider_changed)

        preview_row = make_row("  Vorschau", preview_btn)
        ri_rows.append(preview_row)
        adv_page.pack_start(preview_row, False, False, 0)

        def sync_ri_controls(*_args) -> None:
            active = ri_switch.get_active()
            for row in ri_rows:
                row.set_visible(active)
            if not active:
                _stop_preview()

        ri_switch.connect("notify::active", sync_ri_controls)
        sync_ri_controls()

        adv_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Live Overlay
        overlay_section = Gtk.Label()
        overlay_section.set_markup("<b>Live-Overlay</b>")
        overlay_section.set_xalign(0.0)
        adv_page.pack_start(overlay_section, False, False, 6)

        overlay_row, overlay_switch = build_switch("Overlay aktivieren", cfg.get("live_overlay_enabled", False), "Schwebendes Fenster mit Transkriptions-Fortschritt")
        adv_page.pack_start(overlay_row, False, False, 0)

        overlay_rows: List[Gtk.Widget] = []

        font_size = int(cfg.get("live_overlay_font_size", 14))
        font_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 8.0, 32.0, 1.0)
        font_scale.set_digits(0)
        font_scale.set_value(max(8, min(32, font_size)))
        font_scale.set_draw_value(True)
        font_scale.set_value_pos(Gtk.PositionType.RIGHT)
        font_scale.set_hexpand(True)
        font_row = make_row("  Schriftgröße", font_scale, expand=True, defaults_text="(Standard: 14)")
        overlay_rows.append(font_row)
        adv_page.pack_start(font_row, False, False, 0)

        opacity = float(cfg.get("live_overlay_opacity", 0.9))
        opacity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.3, 1.0, 0.05)
        opacity_scale.set_digits(2)
        opacity_scale.set_value(max(0.3, min(1.0, opacity)))
        opacity_scale.set_draw_value(True)
        opacity_scale.set_value_pos(Gtk.PositionType.RIGHT)
        opacity_scale.set_hexpand(True)
        opacity_scale.clear_marks()
        opacity_scale.connect("format-value", lambda scale, value: f"{int(value * 100)}%")
        opacity_row = make_row("  Transparenz", opacity_scale, expand=True, defaults_text="(Standard: 90%)")
        overlay_rows.append(opacity_row)
        adv_page.pack_start(opacity_row, False, False, 0)

        width = int(cfg.get("live_overlay_width", 400))
        width_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 200.0, 800.0, 50.0)
        width_scale.set_digits(0)
        width_scale.set_value(max(200, min(800, width)))
        width_scale.set_draw_value(True)
        width_scale.set_value_pos(Gtk.PositionType.RIGHT)
        width_scale.set_hexpand(True)
        width_scale.clear_marks()
        width_scale.connect("format-value", lambda scale, value: f"{int(value)} px")
        width_row = make_row("  Breite (px)", width_scale, expand=True, defaults_text="(Standard: 400)")
        overlay_rows.append(width_row)
        adv_page.pack_start(width_row, False, False, 0)

        height = int(cfg.get("live_overlay_height", 150))
        height_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100.0, 400.0, 25.0)
        height_scale.set_digits(0)
        height_scale.set_value(max(100, min(400, height)))
        height_scale.set_draw_value(True)
        height_scale.set_value_pos(Gtk.PositionType.RIGHT)
        height_scale.set_hexpand(True)
        height_scale.clear_marks()
        height_scale.connect("format-value", lambda scale, value: f"{int(value)} px")
        height_row = make_row("  Höhe (px)", height_scale, expand=True, defaults_text="(Standard: 150)")
        overlay_rows.append(height_row)
        adv_page.pack_start(height_row, False, False, 0)

        display_duration = float(cfg.get("live_overlay_display_duration", 2.0))
        duration_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 10.0, 0.5)
        duration_scale.set_digits(1)
        duration_scale.set_value(max(0.5, min(10.0, display_duration)))
        duration_scale.set_draw_value(True)
        duration_scale.set_value_pos(Gtk.PositionType.RIGHT)
        duration_scale.set_hexpand(True)
        duration_scale.clear_marks()
        duration_scale.connect("format-value", lambda scale, value: f"{value:.1f} s")
        duration_row = make_row("  Anzeigedauer (s)", duration_scale, expand=True, defaults_text="(Standard: 2.0)")
        overlay_rows.append(duration_row)
        adv_page.pack_start(duration_row, False, False, 0)

        def sync_overlay_controls(*_args) -> None:
            active = overlay_switch.get_active()
            for row in overlay_rows:
                row.set_visible(active)

        overlay_switch.connect("notify::active", sync_overlay_controls)
        sync_overlay_controls()

        # =====================================================================
        # Button bar at bottom
        # =====================================================================
        main_vbox.pack_end(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        button_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_container.set_border_width(12)
        main_vbox.pack_end(button_container, False, False, 0)

        shortcuts_label = Gtk.Label()
        shortcuts_label.set_markup("<small>Esc = Abbrechen | Ctrl+S = Speichern</small>")
        shortcuts_label.set_xalign(0.0)
        shortcuts_label.get_style_context().add_class("dim-label")
        button_container.pack_start(shortcuts_label, False, False, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_hexpand(True)
        button_container.pack_start(button_box, True, True, 0)

        cancel_button = Gtk.Button(label="Abbrechen")
        save_button = Gtk.Button(label="Speichern")
        button_box.pack_start(cancel_button, False, False, 0)
        button_box.pack_start(save_button, False, False, 0)

        def close_window(*_args) -> None:
            global _settings_window
            if _settings_window is None:
                return
            # Stop recording indicator preview if active
            _stop_preview()
            window_ref = _settings_window
            _settings_window = None
            window_ref.destroy()
            capture_state["active"] = False
            state["hotkey_capture_active"] = False
            cancel_hotkey_capture()

        def on_cancel(_button) -> None:
            close_window()

        def on_save_clicked(_button) -> None:
            conflicts = get_hotkey_conflicts_for_actions(pending_hotkeys, hotkey_actions)
            conflict_message = build_hotkey_conflict_message(conflicts, hotkey_actions)
            if conflict_message:
                notify(conflict_message)
                return

            # Tab 1: Basis
            cfg["theme_preference"] = theme_combo.get_active_id() or "auto"
            cfg["language"] = language_combo.get_active_id() or "de"
            cfg["auto_paste_enabled"] = auto_switch.get_active()
            cfg["notifications_enabled"] = notify_switch.get_active()
            cfg["paste_sequence"] = paste_combo.get_active_id() or "auto"
            cfg["paste_delay_ms"] = int(round(paste_delay_spin.get_value()))
            cfg["hotkeys"] = pending_hotkeys.copy()
            cfg["hotkey"] = cfg["hotkeys"].get("toggle_recording", cfg.get("hotkey", "F9"))

            # Tab 2: Audio
            device_id = device_combo.get_active_id() or "__default__"
            cfg["device_name"] = device_map.get(device_id)
            cfg["noise_reduction_enabled"] = nr_switch.get_active() if noise_reduction_available else False
            cfg["noise_reduction_strength"] = round(float(nr_scale.get_value()), 1)
            cfg["audio_feedback_enabled"] = audio_fb_switch.get_active()
            cfg["audio_feedback_volume"] = round(float(audio_fb_volume_scale.get_value()), 1)

            # Tab 3: Transkription
            cfg["transcription_backend"] = backend_combo.get_active_id() or "openai"
            cfg["faster_whisper_model"] = fw_model_combo.get_active_id() or "medium"
            cfg["streaming_model"] = streaming_model_combo.get_active_id() or "tiny"

            # Save API keys to .env file
            deepgram_key = deepgram_key_entry.get_text().strip()
            openai_key = openai_key_entry.get_text().strip()
            elevenlabs_key = elevenlabs_key_entry.get_text().strip()
            save_env_file_value("DEEPGRAM_API_KEY", deepgram_key)
            save_env_file_value("OPENAI_API_KEY", openai_key)
            save_env_file_value("ELEVENLABS_API_KEY", elevenlabs_key)

            # Tab 4: Erweitert
            cfg["use_vad"] = vad_switch.get_active() if VAD_AVAILABLE else False
            cfg["vad_energy_ratio"] = round(float(vad_scale.get_value()), 3)
            cfg["vad_bridge_ms"] = int(round(bridge_scale.get_value()))
            cfg["vad_min_energy_frames"] = int(round(frames_scale.get_value()))
            cfg["vad_auto_stop_enabled"] = (auto_stop_switch.get_active() and vad_switch.get_active()) if VAD_AVAILABLE else False
            cfg["vad_auto_stop_silence_seconds"] = round(float(auto_stop_scale.get_value()), 1)
            cfg["stop_tail_grace_ms"] = int(round(stop_tail_scale.get_value()))
            cfg["min_audio_energy"] = round(float(min_energy_scale.get_value()), 4)
            cfg["postprocess_enabled"] = pp_switch.get_active()
            cfg["postprocess_fix_spacing"] = pp_spacing_switch.get_active() and pp_switch.get_active()
            cfg["postprocess_fix_capitalization"] = pp_caps_switch.get_active() and pp_switch.get_active()
            cfg["chunking_enabled"] = chunking_switch.get_active()
            # Recording indicator settings
            old_ri_enabled = cfg.get("recording_indicator_enabled")
            old_ri_position = cfg.get("recording_indicator_position")
            old_ri_width = cfg.get("recording_indicator_width")
            old_ri_height = cfg.get("recording_indicator_height")
            old_ri_opacity = cfg.get("recording_indicator_opacity")

            cfg["recording_indicator_enabled"] = ri_switch.get_active()
            cfg["recording_indicator_position"] = ri_pos_combo.get_active_id() or "top-center"
            cfg["recording_indicator_width"] = int(ri_width.get_value())
            cfg["recording_indicator_height"] = int(ri_height.get_value())
            cfg["recording_indicator_opacity"] = round(float(ri_opacity.get_value()), 2)

            # Reset indicator singleton if any indicator settings changed
            ri_changed = (
                old_ri_enabled != cfg["recording_indicator_enabled"]
                or old_ri_position != cfg["recording_indicator_position"]
                or old_ri_width != cfg["recording_indicator_width"]
                or old_ri_height != cfg["recording_indicator_height"]
                or old_ri_opacity != cfg["recording_indicator_opacity"]
            )
            if ri_changed:
                try:
                    from whisprbar.ui.recording_indicator import reset_recording_indicator
                    reset_recording_indicator()
                except Exception as exc:
                    print(f"[WARN] Failed to reset recording indicator: {exc}", file=sys.stderr)

            cfg["live_overlay_enabled"] = overlay_switch.get_active()
            cfg["live_overlay_font_size"] = int(font_scale.get_value())
            cfg["live_overlay_opacity"] = round(float(opacity_scale.get_value()), 2)
            cfg["live_overlay_width"] = int(width_scale.get_value())
            cfg["live_overlay_height"] = int(height_scale.get_value())
            cfg["live_overlay_display_duration"] = round(float(duration_scale.get_value()), 1)

            if cfg.get("auto_paste_enabled"):
                state["wayland_notice_shown"] = False

            save_config()
            update_device_index()

            if cfg.get("auto_paste_enabled") and is_wayland_session():
                notify("Wayland: Auto-Paste nur über Zwischenablage.")
            notify("Einstellungen gespeichert.")

            if on_save:
                on_save()

            close_window()

        cancel_button.connect("clicked", on_cancel)
        save_button.connect("clicked", on_save_clicked)
        window.connect("destroy", lambda *_: close_window())

        def on_key_press(widget, event):
            keyval = event.keyval
            mod_state = event.state
            ctrl_pressed = bool(mod_state & Gdk.ModifierType.CONTROL_MASK)

            if keyval == Gdk.KEY_Escape:
                on_cancel(None)
                return True
            if ctrl_pressed and keyval == Gdk.KEY_s:
                on_save_clicked(None)
                return True
            if ctrl_pressed and keyval == Gdk.KEY_w:
                on_cancel(None)
                return True
            return False

        window.connect("key-press-event", on_key_press)

        window.show_all()
        window.present()
        window.set_keep_above(True)
        GLib.timeout_add(500, lambda: window.set_keep_above(False) or False)

        with _settings_window_lock:
            _settings_window = window
        return False

    GLib.idle_add(_present_settings)
