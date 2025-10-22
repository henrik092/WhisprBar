#!/usr/bin/env python3
"""
whisprbar/ui.py - GUI components (settings, overlay, diagnostics)

This module handles all user interface components:
- Settings dialog with all configuration options
- Live transcription overlay window
- First-run diagnostics wizard
"""

from typing import Optional, Callable, List
import contextlib
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
from whisprbar.config import save_config, cfg
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
)
from whisprbar.audio import list_input_devices, update_device_index
from whisprbar.hotkeys import key_to_label, capture_hotkey, update_hotkey_binding
from whisprbar.paste import PASTE_OPTIONS, is_wayland_session

# Module state - window references
_overlay_window = None
_overlay_window_lock = threading.Lock()
_settings_window = None
_settings_window_lock = threading.Lock()
_diagnostics_window = None
_capture_listener = None

# Check VAD availability
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False


# =============================================================================
# Theme Detection and Styling
# =============================================================================

def detect_system_theme() -> str:
    """Detect system theme preference.

    Returns:
        "dark" or "light" based on system settings
    """
    try:
        from gi.repository import Gtk
        settings = Gtk.Settings.get_default()
        if settings:
            # Try to get GTK theme name
            theme_name = settings.get_property("gtk-theme-name")
            if theme_name:
                theme_name_lower = theme_name.lower()
                if "dark" in theme_name_lower:
                    return "dark"

            # Try to check application prefer dark theme
            if hasattr(settings.props, "gtk_application_prefer_dark_theme"):
                if settings.get_property("gtk-application-prefer-dark-theme"):
                    return "dark"
    except Exception:
        pass

    # Default to light theme
    return "light"


def get_effective_theme(cfg: dict) -> str:
    """Get effective theme based on user preference.

    Args:
        cfg: Configuration dictionary

    Returns:
        "dark" or "light"
    """
    preference = cfg.get("theme_preference", "auto")

    if preference == "auto":
        return detect_system_theme()
    elif preference in ("dark", "light"):
        return preference
    else:
        return "light"


def apply_theme_css(widget, theme: str = "light") -> None:
    """Apply theme-specific CSS to a widget.

    Args:
        widget: GTK widget to apply CSS to
        theme: "light" or "dark"
    """
    if Gtk is None or Gdk is None:
        return

    try:
        css_provider = Gtk.CssProvider()

        if theme == "dark":
            css = b"""
                window {
                    background-color: #2b2b2b;
                    color: #e0e0e0;
                }

                box, frame, grid {
                    background-color: #2b2b2b;
                    color: #e0e0e0;
                }

                entry, textview {
                    background-color: #3c3c3c;
                    color: #e0e0e0;
                    border-color: #555555;
                }

                button {
                    background-color: #3c3c3c;
                    color: #e0e0e0;
                    border-color: #555555;
                }

                button:hover {
                    background-color: #4a4a4a;
                }

                button:active {
                    background-color: #2a2a2a;
                }

                label {
                    color: #e0e0e0;
                }

                .dim-label {
                    color: #a0a0a0;
                }

                /* Modern Sliders with orange accent (compact) */
                scale {
                    color: #e0e0e0;
                    min-height: 10px;
                }

                scale trough {
                    background-color: #404040;
                    border: none;
                    border-radius: 4px;
                    min-height: 4px;
                }

                scale highlight {
                    background: linear-gradient(90deg, #ff6600, #ff8800);
                    border-radius: 4px;
                    min-height: 4px;
                }

                scale slider {
                    background-color: #ff7700;
                    border: 2px solid #ffffff;
                    border-radius: 50%;
                    min-width: 14px;
                    min-height: 14px;
                    margin: -5px;
                }

                scale slider:hover {
                    background-color: #ff9933;
                }

                scale slider:active {
                    background-color: #ffaa00;
                }

                combobox, combobox * {
                    background-color: #3c3c3c;
                    color: #e0e0e0;
                }

                spinbutton {
                    background-color: #3c3c3c;
                    color: #e0e0e0;
                    border-color: #555555;
                }

                /* Modern Switches with orange accent */
                switch {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    border-radius: 12px;
                }

                switch:checked {
                    background: linear-gradient(90deg, #ff6600, #ff8800);
                    border-color: #ff7700;
                }

                switch slider {
                    background-color: #ffffff;
                    border-radius: 50%;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.4);
                }

                scrolledwindow {
                    background-color: #2b2b2b;
                }

                separator {
                    background-color: #555555;
                }
            """
        else:  # light theme
            css = b"""
                window {
                    background-color: #f5f5f5;
                    color: #2b2b2b;
                }

                .dim-label {
                    color: #666666;
                }
            """

        css_provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        style_context = Gtk.StyleContext()
        style_context.add_provider_for_screen(
            screen,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    except Exception as e:
        # Styling is optional, don't fail
        pass


# =============================================================================
# First-Run Diagnostics
# =============================================================================

def _mark_first_run_complete(cfg: dict) -> None:
    """Mark first run as complete and save config."""
    if not cfg.get("first_run_complete", False):
        cfg["first_run_complete"] = True
        save_config()


def _run_diagnostics_cli(cfg: dict) -> int:
    """Run diagnostics in CLI mode and return exit code."""
    print("\n=== WhisprBar Diagnostics ===\n")
    results = collect_diagnostics()

    errors = sum(1 for r in results if r.status == STATUS_ERROR)
    warnings = sum(1 for r in results if r.status == STATUS_WARN)

    for res in results:
        status_label = CLI_STATUS_LABEL.get(res.status, res.status.upper())
        print(f"[{status_label}] {res.label}")
        print(f"  {res.detail}")
        if res.remedy:
            print(f"  Fix: {res.remedy}")
        print()

    if errors:
        print(f"Summary: {errors} error(s), {warnings} warning(s) detected.")
        return 1
    elif warnings:
        print(f"Summary: No errors detected. {warnings} warning(s) to review.")
        return 0
    else:
        print("Summary: All checks passed.")
        return 0


def maybe_show_first_run_diagnostics(cfg: dict) -> None:
    """Show diagnostics wizard if this is the first run."""
    if cfg.get("first_run_complete", False):
        return
    open_diagnostics_window(cfg, first_run=True)


def open_diagnostics_window(cfg: dict, first_run: bool = False) -> None:
    """
    Open diagnostics window showing system environment checks.

    Args:
        cfg: Configuration dictionary
        first_run: If True, this is the first-run wizard
    """
    global _diagnostics_window

    if Gtk is None:
        print("Diagnostics window requires GTK; falling back to CLI output.")
        _run_diagnostics_cli(cfg)
        if first_run:
            _mark_first_run_complete(cfg)
        return

    if _diagnostics_window is not None:
        if GLib is not None:
            GLib.idle_add(lambda: _diagnostics_window.present() or False)
        else:
            _diagnostics_window.present()
        return

    def _present() -> bool:
        global _diagnostics_window
        if _diagnostics_window is not None:
            _diagnostics_window.present()
            return False

        window = Gtk.Window(title="WhisprBar Diagnostics")
        window.set_default_size(540, 420)
        try:
            window.set_position(Gtk.WindowPosition.CENTER)
        except Exception:
            pass

        # Apply theme to diagnostics window
        theme = get_effective_theme(cfg)
        apply_theme_css(window, theme)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_border_width(12)
        window.add(content)

        title_label = Gtk.Label()
        if GLib is not None:
            title_label.set_markup("<b>Environment diagnostics</b>")
        else:
            title_label.set_text("Environment diagnostics")
        title_label.set_xalign(0.0)
        content.pack_start(title_label, False, False, 0)

        summary_label = Gtk.Label()
        summary_label.set_xalign(0.0)
        summary_label.set_line_wrap(True)
        summary_label.set_max_width_chars(70)
        content.pack_start(summary_label, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        try:
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        except Exception:
            pass
        content.pack_start(scroller, True, True, 0)

        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        results_box.set_hexpand(True)
        scroller.add(results_box)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.set_halign(Gtk.Align.END)
        content.pack_end(button_box, False, False, 0)

        rerun_button = Gtk.Button(label="Run again")
        close_label = "Done" if first_run else "Close"
        close_button = Gtk.Button(label=close_label)
        button_box.pack_start(rerun_button, False, False, 0)
        button_box.pack_start(close_button, False, False, 0)

        def populate() -> None:
            for child in list(results_box.get_children()):
                results_box.remove(child)

            results = collect_diagnostics()
            errors = sum(1 for item in results if item.status == STATUS_ERROR)
            warnings = sum(1 for item in results if item.status == STATUS_WARN)
            if errors:
                summary_label.set_text(f"{errors} error(s), {warnings} warning(s) detected.")
            elif warnings:
                summary_label.set_text(f"No errors detected. {warnings} warning(s) to review.")
            else:
                summary_label.set_text("All checks passed.")

            for res in results:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.set_hexpand(True)

                icon_name = STATUS_ICON_NAME.get(res.status, "dialog-information")
                try:
                    icon_widget = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
                except Exception:
                    icon_widget = Gtk.Label(label=CLI_STATUS_LABEL.get(res.status, res.status.upper()))
                icon_widget.set_valign(Gtk.Align.START)
                row.pack_start(icon_widget, False, False, 0)

                text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                text_box.set_hexpand(True)

                label_text = res.label
                if GLib is not None:
                    safe_label = GLib.markup_escape_text(label_text)
                    title = Gtk.Label()
                    title.set_markup(f"<b>{safe_label}</b>")
                else:
                    title = Gtk.Label(label=label_text)
                title.set_xalign(0.0)
                text_box.pack_start(title, False, False, 0)

                detail = Gtk.Label(label=res.detail)
                detail.set_xalign(0.0)
                detail.set_line_wrap(True)
                detail.set_max_width_chars(90)
                text_box.pack_start(detail, False, False, 0)

                if res.remedy:
                    remedy_text = f"Fix: {res.remedy}"
                    if GLib is not None:
                        safe_fix = GLib.markup_escape_text(remedy_text)
                        remedy = Gtk.Label()
                        remedy.set_markup(f"<span size='small'>{safe_fix}</span>")
                    else:
                        remedy = Gtk.Label(label=remedy_text)
                    remedy.set_xalign(0.0)
                    remedy.set_line_wrap(True)
                    remedy.set_max_width_chars(90)
                    try:
                        remedy.get_style_context().add_class("dim-label")
                    except Exception:
                        pass
                    text_box.pack_start(remedy, False, False, 0)

                row.pack_start(text_box, True, True, 0)
                results_box.pack_start(row, False, False, 0)

            results_box.show_all()

        populate()

        rerun_button.connect("clicked", lambda *_: populate())
        close_button.connect("clicked", lambda *_: window.destroy())

        def on_destroy(*_args) -> None:
            global _diagnostics_window
            _diagnostics_window = None
            if first_run:
                _mark_first_run_complete(cfg)

        window.connect("destroy", on_destroy)

        _diagnostics_window = window
        window.show_all()
        return False

    if GLib is not None:
        GLib.idle_add(_present)
    else:
        _present()


# =============================================================================
# Live Overlay Window
# =============================================================================

def show_live_overlay(cfg: dict, initial_text: str = "Transcribing...") -> None:
    """
    Show live transcription overlay window.

    Args:
        cfg: Configuration dictionary
        initial_text: Initial text to display
    """
    if not cfg.get("live_overlay_enabled"):
        return

    try:
        from gi.repository import Gtk, Gdk, GLib
    except Exception:
        return

    global _overlay_window

    # Thread-safe check to prevent race condition
    with _overlay_window_lock:
        if _overlay_window is not None:
            import sys
            print("[DEBUG] Overlay already exists, skipping", file=sys.stderr)
            return

    def _show_overlay() -> bool:
        global _overlay_window

        # Thread-safe double-check in GTK thread
        with _overlay_window_lock:
            if _overlay_window is not None:
                import sys
                print("[DEBUG] Overlay already exists in GTK thread, skipping", file=sys.stderr)
                return False

        window = Gtk.Window()
        window.set_decorated(False)
        window.set_keep_above(True)
        window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)

        # Enable RGBA visual for true transparency (fixes black corners)
        screen = window.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            window.set_visual(visual)
        window.set_app_paintable(True)

        # Position from config or bottom-right corner
        screen_width = screen.get_width()
        screen_height = screen.get_height()
        window_width = int(cfg.get("live_overlay_width", 400))
        window_height = int(cfg.get("live_overlay_height", 150))
        window.set_default_size(window_width, window_height)

        # Use saved position or default to bottom-right
        saved_x = cfg.get("live_overlay_x")
        saved_y = cfg.get("live_overlay_y")
        if saved_x is not None and saved_y is not None:
            window.move(int(saved_x), int(saved_y))
        else:
            window.move(screen_width - window_width - 50, screen_height - window_height - 50)

        # Connect draw signal for transparent background
        def on_draw(widget, cr):
            """Make window background fully transparent."""
            cr.set_source_rgba(0, 0, 0, 0)
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            return False

        window.connect("draw", on_draw)

        # Content
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)

        # Progress spinner
        spinner = Gtk.Spinner()
        spinner.start()
        box.pack_start(spinner, False, False, 0)

        # Transcript text
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        buffer = text_view.get_buffer()
        buffer.set_text(initial_text)

        # Font size
        try:
            from gi.repository import Pango
            font_size = int(cfg.get("live_overlay_font_size", 14))
            font_desc = Pango.FontDescription(f"monospace {font_size}")
            text_view.override_font(font_desc)
        except Exception:
            pass  # Font override is optional

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(text_view)
        scroll.set_min_content_height(80)
        box.pack_start(scroll, True, True, 0)

        # Hint
        hint = Gtk.Label(label="ESC to cancel, processing...")
        hint.set_xalign(0.0)
        hint.get_style_context().add_class("dim-label")
        box.pack_start(hint, False, False, 0)

        # Get configured opacity for background
        opacity = max(0.3, min(1.0, float(cfg.get("live_overlay_opacity", 0.9))))

        # Apply modern styling with rounded corners and theme
        # Apply to box instead of window to avoid black corners
        try:
            theme = get_effective_theme(cfg)
            css_provider = Gtk.CssProvider()

            if theme == "dark":
                css = f"""
                    .overlay-box {{
                        border-radius: 12px;
                        background-color: rgba(40, 40, 40, {opacity});
                        padding: 12px;
                    }}
                    * {{
                        color: #ffffff;
                    }}
                """.encode()
            else:
                css = f"""
                    .overlay-box {{
                        border-radius: 12px;
                        background-color: rgba(240, 240, 240, {opacity});
                        padding: 12px;
                    }}
                    * {{
                        color: #2b2b2b;
                    }}
                """.encode()

            css_provider.load_from_data(css)
            screen = Gdk.Screen.get_default()
            style_context = box.get_style_context()
            style_context.add_provider_for_screen(
                screen,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            style_context.add_class("overlay-box")
        except Exception as exc:
            import sys
            print(f"[WARN] Failed to apply overlay CSS: {exc}", file=sys.stderr)

        window.add(box)

        # Store references
        window.text_buffer = buffer
        window.spinner = spinner
        window.hint_label = hint

        # Enable drag-and-drop
        window.drag_start_x = None
        window.drag_start_y = None

        def on_button_press(widget, event):
            if event.button == 1:  # Left mouse button
                widget.drag_start_x = event.x_root
                widget.drag_start_y = event.y_root
                widget.drag_offset_x, widget.drag_offset_y = widget.get_position()
            return False

        def on_motion_notify(widget, event):
            if widget.drag_start_x is not None:
                x = widget.drag_offset_x + (event.x_root - widget.drag_start_x)
                y = widget.drag_offset_y + (event.y_root - widget.drag_start_y)
                widget.move(int(x), int(y))
            return False

        def on_button_release(widget, event):
            if event.button == 1:
                widget.drag_start_x = None
                widget.drag_start_y = None
                # Save position to config
                x, y = widget.get_position()
                cfg["live_overlay_x"] = x
                cfg["live_overlay_y"] = y
                save_config()
            return False

        window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK |
                         Gdk.EventMask.POINTER_MOTION_MASK)
        window.connect("button-press-event", on_button_press)
        window.connect("motion-notify-event", on_motion_notify)
        window.connect("button-release-event", on_button_release)

        # Thread-safe assignment
        with _overlay_window_lock:
            _overlay_window = window
        window.show_all()

        return False

    try:
        from gi.repository import GLib
        GLib.idle_add(_show_overlay)
    except Exception:
        pass


def update_live_overlay(text: str, status: str = "") -> None:
    """
    Update live overlay text.

    Args:
        text: New text to display
        status: Optional status message
    """
    global _overlay_window

    # Thread-safe check
    with _overlay_window_lock:
        if _overlay_window is None:
            return
        window_ref = _overlay_window

    def _update() -> bool:
        # Use captured reference to avoid race
        if window_ref is None:
            return False

        try:
            window_ref.text_buffer.set_text(text)
            if status and hasattr(window_ref, 'hint_label'):
                window_ref.hint_label.set_text(status)
        except Exception:
            pass

        return False

    try:
        from gi.repository import GLib
        GLib.idle_add(_update)
    except Exception:
        pass


def hide_live_overlay() -> None:
    """Hide and destroy live overlay window."""
    global _overlay_window

    # Thread-safe check and clear
    with _overlay_window_lock:
        if _overlay_window is None:
            return
        window_ref = _overlay_window
        _overlay_window = None  # Clear immediately to prevent double-destroy

    def _hide() -> bool:
        # Use captured reference
        if window_ref is None:
            return False

        try:
            if hasattr(window_ref, 'destroy'):
                window_ref.destroy()
        except Exception as exc:
            import sys
            print(f"[WARN] Failed to destroy overlay: {exc}", file=sys.stderr)

        return False

    try:
        from gi.repository import GLib
        GLib.idle_add(_hide)
    except Exception as exc:
        import sys
        print(f"[WARN] Failed to schedule overlay hide: {exc}", file=sys.stderr)
        # Fallback: destroy immediately
        try:
            if _overlay_window:
                _overlay_window.destroy()
                _overlay_window = None
        except:
            pass


# =============================================================================
# Settings Window
# =============================================================================

def open_settings_window(cfg: dict, state: dict, on_save: Optional[Callable] = None) -> None:
    """
    Open settings window with all configuration options.

    Args:
        cfg: Configuration dictionary
        state: Application state dictionary
        on_save: Optional callback to invoke after saving settings
    """
    global _settings_window, _capture_listener

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
        global _settings_window, _capture_listener

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

        # Apply theme
        theme = get_effective_theme(cfg)
        apply_theme_css(window, theme)

        # Main vertical container
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        window.add(main_vbox)

        # Show warning only if API key is missing
        if not state.get("client_ready"):
            header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            header_box.set_border_width(12)
            main_vbox.pack_start(header_box, False, False, 0)

            warning = Gtk.Label()
            warning.set_markup(
                "<b>Transcription disabled:</b> Configure OPENAI_API_KEY in ~/.config/whisprbar.env."
            )
            warning.set_xalign(0.0)
            warning.set_line_wrap(True)
            warning.set_max_width_chars(90)
            header_box.pack_start(warning, False, False, 0)

        # Two-column layout (no scrolling - auto-size to content)
        columns_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        columns_box.set_border_width(12)
        main_vbox.pack_start(columns_box, True, True, 0)

        # LEFT COLUMN
        left_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left_column.set_hexpand(True)
        columns_box.pack_start(left_column, True, True, 0)

        # RIGHT COLUMN
        right_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        right_column.set_hexpand(True)
        columns_box.pack_start(right_column, True, True, 0)

        # --- LEFT COLUMN: Basic Settings ---
        basic_section = Gtk.Label()
        basic_section.set_markup("<b>Basic Settings</b>")
        basic_section.set_xalign(0.0)
        left_column.pack_start(basic_section, False, False, 0)

        # Use left_column as content for basic settings
        content = left_column

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

        # Theme selection
        theme_combo = Gtk.ComboBoxText()
        theme_combo.append("auto", "Auto (Follow system)")
        theme_combo.append("light", "Light")
        theme_combo.append("dark", "Dark")
        active_theme = cfg.get("theme_preference", "auto")
        theme_combo.set_active_id(active_theme)
        theme_tooltip = "Choose UI theme: Auto follows system settings, or manually select Light/Dark mode"
        content.pack_start(make_row("Theme", theme_combo, tooltip=theme_tooltip), False, False, 0)

        # Add a note about theme changes requiring restart
        theme_note = Gtk.Label(label="(Theme changes take effect after restart)")
        theme_note.set_xalign(0.0)
        theme_note.get_style_context().add_class("dim-label")
        content.pack_start(theme_note, False, False, 0)

        language_combo = Gtk.ComboBoxText()
        language_combo.append("de", "Deutsch (de)")
        language_combo.append("en", "English (en)")
        active_lang = cfg.get("language", "de")
        if active_lang not in {"de", "en"}:
            active_lang = "de"
        language_combo.set_active_id(active_lang)
        language_tooltip = "Select language for voice transcription (affects recognition accuracy for specific languages)"
        content.pack_start(make_row("Language", language_combo, tooltip=language_tooltip), False, False, 0)

        # Transcription backend selection
        backend_combo = Gtk.ComboBoxText()
        backend_combo.append("openai", "OpenAI Whisper API (online, best quality)")
        backend_combo.append("faster_whisper", "faster-whisper (offline, local)")
        backend_combo.append("streaming", "sherpa-onnx streaming (low latency, offline)")
        active_backend = cfg.get("transcription_backend", "openai")
        backend_combo.set_active_id(active_backend)
        backend_tooltip = "Select transcription backend: OpenAI for best quality (requires API key), faster-whisper for offline use, streaming for low latency"
        content.pack_start(make_row("Transcription Backend", backend_combo, tooltip=backend_tooltip), False, False, 0)

        # faster-whisper model size selection (only shown when faster_whisper backend selected)
        fw_model_combo = Gtk.ComboBoxText()
        fw_model_combo.append("tiny", "Tiny (~1GB RAM, fast)")
        fw_model_combo.append("base", "Base (~1GB RAM)")
        fw_model_combo.append("small", "Small (~2GB RAM)")
        fw_model_combo.append("medium", "Medium (~5GB RAM, recommended)")
        fw_model_combo.append("large", "Large (~10GB RAM, best quality)")
        active_model = cfg.get("faster_whisper_model", "medium")
        fw_model_combo.set_active_id(active_model)
        fw_model_tooltip = "Model size affects quality and speed. Larger = better quality but slower"
        fw_model_row = make_row("  Model Size", fw_model_combo, tooltip=fw_model_tooltip)
        content.pack_start(fw_model_row, False, False, 0)

        # sherpa-onnx streaming model selection (only shown when streaming backend selected)
        streaming_model_combo = Gtk.ComboBoxText()
        streaming_model_combo.append("tiny", "Tiny (fastest, lower quality)")
        streaming_model_combo.append("base", "Base (balanced)")
        streaming_model_combo.append("small", "Small (good quality)")
        streaming_model_combo.append("medium", "Medium (best quality, slower)")
        active_streaming_model = cfg.get("streaming_model", "tiny")
        streaming_model_combo.set_active_id(active_streaming_model)
        streaming_model_tooltip = "Model size for streaming transcription. Tiny recommended for low latency"
        streaming_model_row = make_row("  Streaming Model", streaming_model_combo, tooltip=streaming_model_tooltip)
        content.pack_start(streaming_model_row, False, False, 0)

        # Show/hide model selectors based on backend
        if active_backend != "faster_whisper":
            fw_model_row.set_visible(False)
        if active_backend != "streaming":
            streaming_model_row.set_visible(False)

        # Update visibility when backend changes
        def on_backend_changed(combo):
            backend = combo.get_active_id()
            fw_model_row.set_visible(backend == "faster_whisper")
            streaming_model_row.set_visible(backend == "streaming")

        backend_combo.connect("changed", on_backend_changed)

        device_combo = Gtk.ComboBoxText()
        device_combo.append("__default__", "System Default")
        active_device_id = "__default__"
        saved_name = cfg.get("device_name")
        for device in devices:
            device_id = str(device.get("index"))
            device_name = device.get("name") or f"Device {device_id}"
            device_map[device_id] = device_name
            device_combo.append(device_id, device_name)
            if saved_name and device_name.lower() == saved_name.lower():
                active_device_id = device_id
        device_combo.set_active_id(active_device_id)
        device_tooltip = "Select audio input device for recording. System Default uses your system's preferred microphone."
        content.pack_start(make_row("Input Device", device_combo, tooltip=device_tooltip), False, False, 0)

        paste_combo = Gtk.ComboBoxText()
        for key, label in PASTE_OPTIONS.items():
            paste_combo.append(key, label)
        paste_combo.set_active_id(cfg.get("paste_sequence", "auto"))
        if is_wayland_session():
            paste_combo.set_sensitive(False)
        paste_tooltip = "Select the key sequence used when auto paste runs. 'Auto' chooses based on the active window."
        content.pack_start(make_row("Paste Mode", paste_combo, tooltip=paste_tooltip), False, False, 0)

        paste_delay_adjustment = Gtk.Adjustment(
            value=float(cfg.get("paste_delay_ms", 250) or 0),
            lower=0.0,
            upper=2000.0,
            step_increment=25.0,
            page_increment=100.0,
        )
        paste_delay_spin = Gtk.SpinButton()
        paste_delay_spin.set_adjustment(paste_delay_adjustment)
        paste_delay_spin.set_numeric(True)
        paste_delay_spin.set_value(float(cfg.get("paste_delay_ms", 250) or 0))
        paste_delay_spin.set_digits(0)
        paste_delay_tooltip = "Delay before auto paste (milliseconds). Increase for slow apps or reduce for faster paste."
        content.pack_start(
            make_row(
                "Paste Delay",
                paste_delay_spin,
                tooltip=paste_delay_tooltip,
                defaults_text="Default: 250 ms",
            ),
            False,
            False,
            0,
        )

        # Multiple hotkeys section
        hotkeys_section = Gtk.Label()
        hotkeys_section.set_markup("<b>Hotkeys</b>")
        hotkeys_section.set_xalign(0.0)
        content.pack_start(hotkeys_section, False, False, 6)

        # Get hotkeys from config
        from whisprbar.hotkeys import parse_hotkey, hotkey_to_label
        hotkeys_config = cfg.get("hotkeys", {})

        # Define available hotkey actions with descriptions
        hotkey_actions = {
            "toggle_recording": "Toggle Recording",
            "open_settings": "Open Settings",
            "show_history": "Show History (planned)",
            "cancel_recording": "Cancel Recording (ESC)",
        }

        # Store hotkey widgets for capture
        hotkey_widgets = {}
        capture_state = {"active": False, "current_action": None}

        def finish_hotkey_capture(action_id: str, hotkey_str: str, label: str) -> None:
            capture_state["active"] = False
            capture_state["current_action"] = None
            state["hotkey_capture_active"] = False

            # Update config
            if "hotkeys" not in cfg:
                cfg["hotkeys"] = {}
            cfg["hotkeys"][action_id] = hotkey_str

            # Update widget
            widgets = hotkey_widgets.get(action_id)
            if widgets:
                widgets["label"].set_text(label)
                widgets["change_btn"].set_label("Change")
                widgets["change_btn"].set_sensitive(True)
                widgets["clear_btn"].set_sensitive(action_id not in ["toggle_recording", "cancel_recording"])

            # Re-enable all change buttons
            for action, wdgs in hotkey_widgets.items():
                wdgs["change_btn"].set_sensitive(True)

        def begin_hotkey_capture(action_id: str) -> None:
            if capture_state["active"]:
                return
            capture_state["active"] = True
            capture_state["current_action"] = action_id
            state["hotkey_capture_active"] = True

            widgets = hotkey_widgets.get(action_id)
            if not widgets:
                return

            widgets["label"].set_text("Press key...")
            widgets["change_btn"].set_label("Listening...")
            widgets["change_btn"].set_sensitive(False)

            # Disable all other change buttons during capture
            for other_action, other_widgets in hotkey_widgets.items():
                if other_action != action_id:
                    other_widgets["change_btn"].set_sensitive(False)

            try:
                def on_complete(config_str: str, label: str) -> None:
                    finish_hotkey_capture(action_id, config_str, label)

                capture_hotkey(on_complete=on_complete, notify_user=False)
            except Exception as exc:
                # Restore state on error
                capture_state["active"] = False
                capture_state["current_action"] = None
                state["hotkey_capture_active"] = False
                current_hotkey = hotkeys_config.get(action_id)
                if current_hotkey:
                    try:
                        binding = parse_hotkey(current_hotkey)
                        display = hotkey_to_label(binding)
                    except:
                        display = current_hotkey or "Not set"
                else:
                    display = "Not set"
                if widgets:
                    widgets["label"].set_text(display)
                    widgets["change_btn"].set_label("Change")
                    widgets["change_btn"].set_sensitive(True)
                    widgets["clear_btn"].set_sensitive(action_id not in ["toggle_recording", "cancel_recording"])
                # Re-enable all buttons
                for action, wdgs in hotkey_widgets.items():
                    wdgs["change_btn"].set_sensitive(True)
                print(f"[WARN] Hotkey capture failed: {exc}", file=sys.stderr)

        def clear_hotkey(action_id: str) -> None:
            if action_id in ["toggle_recording", "cancel_recording"]:
                return  # Cannot clear essential hotkeys

            widgets = hotkey_widgets.get(action_id)
            if widgets:
                widgets["label"].set_text("Not set")
                if "hotkeys" not in cfg:
                    cfg["hotkeys"] = {}
                cfg["hotkeys"][action_id] = None

        # Create hotkey rows
        for action_id, action_label in hotkey_actions.items():
            hotkey_str = hotkeys_config.get(action_id)

            # Parse and display current hotkey
            if hotkey_str:
                try:
                    hotkey_binding = parse_hotkey(hotkey_str)
                    display_label = hotkey_to_label(hotkey_binding)
                except:
                    display_label = hotkey_str or "Not set"
            else:
                display_label = "Not set"

            # Special handling for cancel_recording (ESC is hardcoded)
            if action_id == "cancel_recording":
                display_label = "ESC (built-in)"

            # Create row with label + Change + Clear buttons
            hotkey_row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hotkey_value_label = Gtk.Label(label=display_label)
            hotkey_value_label.set_xalign(0.0)
            hotkey_value_label.set_width_chars(20)
            hotkey_row_box.pack_start(hotkey_value_label, False, False, 0)

            change_btn = Gtk.Button(label="Change")
            clear_btn = Gtk.Button(label="Clear")
            hotkey_row_box.pack_start(change_btn, False, False, 0)
            hotkey_row_box.pack_start(clear_btn, False, False, 0)

            # Disable buttons for cancel_recording (ESC is hardcoded)
            if action_id == "cancel_recording":
                change_btn.set_sensitive(False)
                change_btn.set_tooltip_text("ESC key is hardcoded for cancellation")
                clear_btn.set_sensitive(False)
                clear_btn.set_tooltip_text("ESC key cannot be changed or cleared")
            elif action_id == "toggle_recording":
                clear_btn.set_sensitive(False)
                clear_btn.set_tooltip_text("This hotkey cannot be cleared")

            # Store references
            hotkey_widgets[action_id] = {
                "label": hotkey_value_label,
                "change_btn": change_btn,
                "clear_btn": clear_btn,
            }

            tooltip = f"Global shortcut for: {action_label}"
            content.pack_start(make_row(action_label, hotkey_row_box, tooltip=tooltip), False, False, 0)

        # Connect button signals
        for action_id, widgets in hotkey_widgets.items():
            widgets["change_btn"].connect("clicked", lambda btn, aid=action_id: begin_hotkey_capture(aid))
            widgets["clear_btn"].connect("clicked", lambda btn, aid=action_id: clear_hotkey(aid))

        def build_switch(label_text: str, active: bool, tooltip: Optional[str] = None) -> tuple:
            switch = Gtk.Switch()
            switch.set_active(active)
            if tooltip:
                switch.set_tooltip_text(tooltip)
            row = make_row(label_text, switch, tooltip=tooltip)
            return row, switch

        notify_tooltip = "Show desktop notifications for transcription status and errors"
        notify_row, notify_switch = build_switch(
            "Notifications",
            cfg.get("notifications_enabled", True),
            notify_tooltip,
        )
        content.pack_start(notify_row, False, False, 0)

        auto_tooltip = "Automatically paste transcripts into the active window after transcription. "
        if is_wayland_session():
            auto_tooltip += "Note: Wayland restricts auto-paste to clipboard-only mode."
        else:
            auto_tooltip += "On X11, uses window-specific paste methods for best compatibility."
        auto_row, auto_switch = build_switch(
            "Auto Paste",
            cfg.get("auto_paste_enabled", False),
            auto_tooltip,
        )
        content.pack_start(auto_row, False, False, 0)

        # --- RIGHT COLUMN: Voice Activity Detection Section ---
        content = right_column  # Switch to right column
        vad_section = Gtk.Label()
        vad_section.set_markup("<b>Voice Activity Detection</b>")
        vad_section.set_xalign(0.0)
        content.pack_start(vad_section, False, False, 0)

        vad_label = "Enable VAD"
        if VAD_AVAILABLE:
            vad_tooltip = "Trim silence around speech to reduce processing time and API usage."
        else:
            vad_tooltip = "Install the 'webrtcvad' package to enable silence trimming."
        vad_row, vad_switch = build_switch(
            vad_label,
            cfg.get("use_vad", False) and VAD_AVAILABLE,
            vad_tooltip,
        )
        vad_switch.set_sensitive(VAD_AVAILABLE)
        content.pack_start(vad_row, False, False, 0)

        vad_rows: List[Gtk.Widget] = []

        vad_sensitivity = float(cfg.get("vad_energy_ratio", 0.02) or 0.02)
        vad_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.01,
            0.2,
            0.005,
        )
        vad_scale.set_digits(3)
        vad_scale.set_value(max(0.01, min(0.2, vad_sensitivity)))
        vad_scale.set_draw_value(True)
        vad_scale.set_value_pos(Gtk.PositionType.RIGHT)
        vad_scale.set_hexpand(True)
        vad_scale.set_tooltip_text(
            "Slide left to keep more quiet speech; slide right to trim silence more aggressively. Recommended baseline: 0.02."
        )
        sensitivity_row = make_row(
            "VAD Sensitivity",
            vad_scale,
            tooltip="Slide left to keep more quiet speech; slide right to trim silence more aggressively.",
            expand=True,
            defaults_text="(Default 0.02)",
        )
        vad_rows.append(sensitivity_row)
        content.pack_start(sensitivity_row, False, False, 0)

        bridge_default = int(cfg.get("vad_bridge_ms", 180) or 180)
        bridge_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.0,
            400.0,
            10.0,
        )
        bridge_scale.set_digits(0)
        bridge_scale.set_value(max(0.0, min(400.0, float(bridge_default))))
        bridge_scale.set_draw_value(True)
        bridge_scale.set_value_pos(Gtk.PositionType.RIGHT)
        bridge_scale.set_hexpand(True)
        bridge_scale.clear_marks()  # Remove all marks for smooth sliding
        bridge_scale.connect("format-value", lambda scale, value: f"{int(value)} ms")
        bridge_scale.set_tooltip_text(
            "Slide left to split after shorter pauses; slide right to keep longer gaps in the same segment. Recommended baseline: 180 ms."
        )
        bridge_row = make_row(
            "Pause Bridging (ms)",
            bridge_scale,
            tooltip="Slide left to split after shorter pauses; slide right to keep longer gaps in the same segment.",
            expand=True,
            defaults_text="(Default 180)",
        )
        vad_rows.append(bridge_row)
        content.pack_start(bridge_row, False, False, 0)

        min_frames_default = int(cfg.get("vad_min_energy_frames", 2) or 2)
        frames_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            1.0,
            8.0,
            1.0,
        )
        frames_scale.set_digits(0)
        frames_scale.set_value(max(1.0, min(8.0, float(min_frames_default))))
        frames_scale.set_draw_value(True)
        frames_scale.set_value_pos(Gtk.PositionType.RIGHT)
        frames_scale.set_hexpand(True)
        frames_scale.set_tooltip_text(
            "Slide left to allow very short bursts; slide right to require longer low-level speech. Recommended baseline: 2 frames."
        )
        frames_row = make_row(
            "Noise Guard (frames)",
            frames_scale,
            tooltip="Slide left to allow very short bursts; slide right to require longer low-level speech.",
            expand=True,
            defaults_text="(Default 2)",
        )
        vad_rows.append(frames_row)
        content.pack_start(frames_row, False, False, 0)

        # Auto-Stop Switch
        auto_stop_tooltip = "Automatically stop recording after sustained silence (hands-free mode)."
        auto_stop_row, auto_stop_switch = build_switch(
            "Auto-Stop on Silence",
            cfg.get("vad_auto_stop_enabled", False) and VAD_AVAILABLE,
            auto_stop_tooltip,
        )
        auto_stop_switch.set_sensitive(VAD_AVAILABLE)
        vad_rows.append(auto_stop_row)
        content.pack_start(auto_stop_row, False, False, 0)

        # Auto-Stop Silence Duration (only visible when Auto-Stop is enabled)
        auto_stop_silence_seconds = float(cfg.get("vad_auto_stop_silence_seconds", 2.0) or 2.0)
        auto_stop_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.5,
            10.0,
            0.5,
        )
        auto_stop_scale.set_digits(1)
        auto_stop_scale.set_value(max(0.5, min(10.0, auto_stop_silence_seconds)))
        auto_stop_scale.set_draw_value(True)
        auto_stop_scale.set_value_pos(Gtk.PositionType.RIGHT)
        auto_stop_scale.set_hexpand(True)
        auto_stop_scale.clear_marks()  # Remove all marks for smooth sliding
        auto_stop_scale.connect("format-value", lambda scale, value: f"{value:.1f} s")
        auto_stop_scale.set_tooltip_text(
            "Duration of silence before auto-stop triggers. Lower = more responsive, higher = more forgiving of pauses."
        )
        auto_stop_duration_row = make_row(
            "  Auto-Stop Silence (seconds)",
            auto_stop_scale,
            tooltip="Duration of silence before auto-stop triggers.",
            expand=True,
            defaults_text="(Default 2.0s)",
        )
        vad_rows.append(auto_stop_duration_row)
        content.pack_start(auto_stop_duration_row, False, False, 0)

        # End Recording Buffer (Stop Tail Grace)
        stop_tail_grace = int(cfg.get("stop_tail_grace_ms", 500) or 500)
        stop_tail_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            100.0,
            2000.0,
            100.0,
        )
        stop_tail_scale.set_digits(0)
        stop_tail_scale.set_value(max(100, min(2000, float(stop_tail_grace))))
        stop_tail_scale.set_draw_value(True)
        stop_tail_scale.set_value_pos(Gtk.PositionType.RIGHT)
        stop_tail_scale.set_hexpand(True)
        stop_tail_scale.clear_marks()  # Remove all marks for smooth sliding
        stop_tail_scale.connect("format-value", lambda scale, value: f"{int(value)} ms")
        stop_tail_scale.set_tooltip_text(
            "Continue recording for a short time after releasing the hotkey to avoid cutting off the last word. "
            "Higher values = more safety against cutoffs, but longer wait time."
        )
        stop_tail_row = make_row(
            "End Recording Buffer (ms)",
            stop_tail_scale,
            tooltip="Keep recording briefly after you stop to capture the end of your speech",
            expand=True,
            defaults_text="(Default: 500ms)",
        )
        vad_rows.append(stop_tail_row)
        content.pack_start(stop_tail_row, False, False, 0)

        def sync_vad_controls(*_args) -> None:
            vad_active = vad_switch.get_active() and VAD_AVAILABLE
            for row in vad_rows:
                row.set_visible(vad_active)

            # Auto-Stop Silence Duration should only be visible when Auto-Stop is enabled
            auto_stop_active = auto_stop_switch.get_active() and vad_active
            auto_stop_duration_row.set_visible(auto_stop_active)

        def sync_auto_stop_controls(*_args) -> None:
            # When Auto-Stop switch changes, sync the duration row
            vad_active = vad_switch.get_active() and VAD_AVAILABLE
            auto_stop_active = auto_stop_switch.get_active() and vad_active
            auto_stop_duration_row.set_visible(auto_stop_active)

        vad_switch.connect("notify::active", sync_vad_controls)
        auto_stop_switch.connect("notify::active", sync_auto_stop_controls)
        sync_vad_controls()

        # --- Audio Processing Section (still in right column) ---
        content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 12)
        section_label = Gtk.Label()
        section_label.set_markup("<b>Audio Processing</b>")
        section_label.set_xalign(0.0)
        content.pack_start(section_label, False, False, 0)

        # Noise Reduction
        noise_reduction_available = True
        try:
            import noisereduce
        except ImportError:
            noise_reduction_available = False

        nr_tooltip = "Remove background noise before transcription (may affect speech quality)." if noise_reduction_available else "Install 'noisereduce' package to enable."
        nr_row, nr_switch = build_switch(
            "Noise Reduction",
            cfg.get("noise_reduction_enabled", True) and noise_reduction_available,
            nr_tooltip,
        )
        nr_switch.set_sensitive(noise_reduction_available)
        content.pack_start(nr_row, False, False, 0)

        nr_rows: List[Gtk.Widget] = []

        nr_strength = float(cfg.get("noise_reduction_strength", 0.7) or 0.7)
        nr_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        nr_scale.set_digits(1)
        nr_scale.set_value(max(0.0, min(1.0, nr_strength)))
        nr_scale.set_draw_value(True)
        nr_scale.set_value_pos(Gtk.PositionType.RIGHT)
        nr_scale.set_hexpand(True)
        nr_scale.clear_marks()  # Remove all marks for smooth sliding
        nr_scale.connect("format-value", lambda scale, value: f"{int(value * 100)}%")
        nr_scale.set_tooltip_text("Higher values remove more noise but may distort speech")
        nr_row_widget = make_row(
            "  Strength (0-100%)",
            nr_scale,
            tooltip="Noise reduction: 0% = Off, 100% = Maximum filtering (may affect speech quality)",
            expand=True,
            defaults_text="(Default: 70%)",
        )
        nr_rows.append(nr_row_widget)
        content.pack_start(nr_row_widget, False, False, 0)

        def sync_nr_controls(*_args) -> None:
            active = nr_switch.get_active() and noise_reduction_available
            for row in nr_rows:
                row.set_visible(active)

        nr_switch.connect("notify::active", sync_nr_controls)
        sync_nr_controls()

        # Minimum Audio Energy (Hallucination Prevention)
        content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        min_energy = float(cfg.get("min_audio_energy", 0.0008) or 0.0008)
        min_energy_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0001, 0.01, 0.0001)
        min_energy_scale.set_digits(4)
        min_energy_scale.set_value(max(0.0001, min(0.01, min_energy)))
        min_energy_scale.set_draw_value(True)
        min_energy_scale.set_value_pos(Gtk.PositionType.RIGHT)
        min_energy_scale.set_hexpand(True)
        min_energy_scale.clear_marks()  # Remove all marks for smooth sliding
        min_energy_scale.set_tooltip_text(
            "Minimum audio energy threshold to prevent hallucinations.\n"
            "Lower = more sensitive (accepts quieter speech, may allow hallucinations)\n"
            "Higher = stricter (requires louder speech, blocks more hallucinations)"
        )
        min_energy_row_widget = make_row(
            "Hallucination Prevention",
            min_energy_scale,
            tooltip="Blocks transcription if audio energy is too low (prevents 'Können wir?' hallucinations)",
            expand=True,
            defaults_text="(Default: 0.0008)",
        )
        content.pack_start(min_energy_row_widget, False, False, 0)

        # Post-Processing
        pp_tooltip = "Clean up transcribed text (spacing, capitalization, punctuation)"
        pp_row, pp_switch = build_switch(
            "Post-Processing",
            cfg.get("postprocess_enabled", True),
            pp_tooltip,
        )
        content.pack_start(pp_row, False, False, 0)

        pp_rows: List[Gtk.Widget] = []

        pp_spacing_row, pp_spacing_switch = build_switch(
            "  Fix Spacing",
            cfg.get("postprocess_fix_spacing", True),
            "Remove double spaces and fix punctuation spacing",
        )
        pp_rows.append(pp_spacing_row)
        content.pack_start(pp_spacing_row, False, False, 0)

        pp_caps_row, pp_caps_switch = build_switch(
            "  Fix Capitalization",
            cfg.get("postprocess_fix_capitalization", True),
            "Capitalize sentences and fix common errors (e.g., 'i' → 'I')",
        )
        pp_rows.append(pp_caps_row)
        content.pack_start(pp_caps_row, False, False, 0)

        def sync_pp_controls(*_args) -> None:
            active = pp_switch.get_active()
            for row in pp_rows:
                row.set_visible(active)

        pp_switch.connect("notify::active", sync_pp_controls)
        sync_pp_controls()

        # Chunking
        chunking_tooltip = "Split long recordings (>60s) into smaller chunks for faster parallel processing. Improves speed for lengthy recordings but may affect coherence at chunk boundaries."
        chunking_row, chunking_switch = build_switch(
            "Chunking (long recordings)",
            cfg.get("chunking_enabled", True),
            chunking_tooltip,
        )
        content.pack_start(chunking_row, False, False, 0)

        # Live Overlay
        overlay_tooltip = "Show a floating window with real-time transcription progress. Helpful for monitoring long transcriptions and seeing interim results."
        overlay_row, overlay_switch = build_switch(
            "Live Overlay",
            cfg.get("live_overlay_enabled", False),
            overlay_tooltip,
        )
        content.pack_start(overlay_row, False, False, 0)

        overlay_rows: List[Gtk.Widget] = []

        # Font Size
        font_size = int(cfg.get("live_overlay_font_size", 14))
        font_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 8.0, 32.0, 1.0)
        font_scale.set_digits(0)
        font_scale.set_value(max(8, min(32, font_size)))
        font_scale.set_draw_value(True)
        font_scale.set_value_pos(Gtk.PositionType.RIGHT)
        font_scale.set_hexpand(True)
        font_scale.set_tooltip_text("Font size for overlay text")
        font_row = make_row(
            "  Font Size",
            font_scale,
            tooltip="Text size in overlay window",
            expand=True,
            defaults_text="(Default: 14)",
        )
        overlay_rows.append(font_row)
        content.pack_start(font_row, False, False, 0)

        # Opacity
        opacity = float(cfg.get("live_overlay_opacity", 0.9))
        opacity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.3, 1.0, 0.05)
        opacity_scale.set_digits(2)
        opacity_scale.set_value(max(0.3, min(1.0, opacity)))
        opacity_scale.set_draw_value(True)
        opacity_scale.set_value_pos(Gtk.PositionType.RIGHT)
        opacity_scale.set_hexpand(True)
        opacity_scale.clear_marks()  # Remove all marks for smooth sliding
        opacity_scale.connect("format-value", lambda scale, value: f"{int(value * 100)}%")
        opacity_scale.set_tooltip_text("Transparency: 1.0 = opaque, 0.3 = very transparent")
        opacity_row = make_row(
            "  Transparency",
            opacity_scale,
            tooltip="Window transparency (1.0 = solid, 0.3 = see-through)",
            expand=True,
            defaults_text="(Default: 0.9)",
        )
        overlay_rows.append(opacity_row)
        content.pack_start(opacity_row, False, False, 0)

        # Width
        width = int(cfg.get("live_overlay_width", 400))
        width_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 200.0, 800.0, 50.0)
        width_scale.set_digits(0)
        width_scale.set_value(max(200, min(800, width)))
        width_scale.set_draw_value(True)
        width_scale.set_value_pos(Gtk.PositionType.RIGHT)
        width_scale.set_hexpand(True)
        width_scale.clear_marks()  # Remove all marks for smooth sliding
        width_scale.connect("format-value", lambda scale, value: f"{int(value)} px")
        width_scale.set_tooltip_text("Overlay window width in pixels")
        width_row = make_row(
            "  Width (px)",
            width_scale,
            tooltip="Overlay window width",
            expand=True,
            defaults_text="(Default: 400)",
        )
        overlay_rows.append(width_row)
        content.pack_start(width_row, False, False, 0)

        # Height
        height = int(cfg.get("live_overlay_height", 150))
        height_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100.0, 400.0, 25.0)
        height_scale.set_digits(0)
        height_scale.set_value(max(100, min(400, height)))
        height_scale.set_draw_value(True)
        height_scale.set_value_pos(Gtk.PositionType.RIGHT)
        height_scale.set_hexpand(True)
        height_scale.clear_marks()  # Remove all marks for smooth sliding
        height_scale.connect("format-value", lambda scale, value: f"{int(value)} px")
        height_scale.set_tooltip_text("Overlay window height in pixels")
        height_row = make_row(
            "  Height (px)",
            height_scale,
            tooltip="Overlay window height",
            expand=True,
            defaults_text="(Default: 150)",
        )
        overlay_rows.append(height_row)
        content.pack_start(height_row, False, False, 0)

        # Display Duration
        display_duration = float(cfg.get("live_overlay_display_duration", 2.0))
        duration_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 10.0, 0.5)
        duration_scale.set_digits(1)
        duration_scale.set_value(max(0.5, min(10.0, display_duration)))
        duration_scale.set_draw_value(True)
        duration_scale.set_value_pos(Gtk.PositionType.RIGHT)
        duration_scale.set_hexpand(True)
        duration_scale.clear_marks()  # Remove all marks for smooth sliding
        duration_scale.connect("format-value", lambda scale, value: f"{value:.1f} s")
        duration_scale.set_tooltip_text("How long to show overlay after transcription completes")
        duration_row = make_row(
            "  Display Time (s)",
            duration_scale,
            tooltip="Duration to show overlay after completion",
            expand=True,
            defaults_text="(Default: 2.0s)",
        )
        overlay_rows.append(duration_row)
        content.pack_start(duration_row, False, False, 0)

        def sync_overlay_controls(*_args) -> None:
            active = overlay_switch.get_active()
            for row in overlay_rows:
                row.set_visible(active)

        overlay_switch.connect("notify::active", sync_overlay_controls)
        sync_overlay_controls()

        # Audio Feedback Section
        content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 12)
        audio_fb_section = Gtk.Label()
        audio_fb_section.set_markup("<b>Audio Feedback</b>")
        audio_fb_section.set_xalign(0.0)
        content.pack_start(audio_fb_section, False, False, 0)

        audio_fb_tooltip = "Play system sounds when recording starts and stops. Provides audible confirmation of recording state."
        audio_fb_row, audio_fb_switch = build_switch(
            "Enable Audio Feedback",
            cfg.get("audio_feedback_enabled", True),
            audio_fb_tooltip,
        )
        content.pack_start(audio_fb_row, False, False, 0)

        audio_fb_rows: List[Gtk.Widget] = []

        # Volume slider
        audio_fb_volume = float(cfg.get("audio_feedback_volume", 0.3) or 0.3)
        audio_fb_volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        audio_fb_volume_scale.set_digits(1)
        audio_fb_volume_scale.set_value(max(0.0, min(1.0, audio_fb_volume)))
        audio_fb_volume_scale.set_draw_value(True)
        audio_fb_volume_scale.set_value_pos(Gtk.PositionType.RIGHT)
        audio_fb_volume_scale.set_hexpand(True)
        audio_fb_volume_scale.clear_marks()  # Remove all marks for smooth sliding
        audio_fb_volume_scale.connect("format-value", lambda scale, value: f"{int(value * 100)}%")
        audio_fb_volume_scale.set_tooltip_text("Audio feedback volume: 0% = Mute, 100% = Maximum volume")
        audio_fb_volume_row = make_row(
            "  Volume (0-100%)",
            audio_fb_volume_scale,
            tooltip="Volume for recording start/stop sounds",
            expand=True,
            defaults_text="(Default: 30%)",
        )
        audio_fb_rows.append(audio_fb_volume_row)
        content.pack_start(audio_fb_volume_row, False, False, 0)

        def sync_audio_fb_controls(*_args) -> None:
            active = audio_fb_switch.get_active()
            for row in audio_fb_rows:
                row.set_visible(active)

        audio_fb_switch.connect("notify::active", sync_audio_fb_controls)
        sync_audio_fb_controls()

        # Keyboard shortcuts hint section
        shortcuts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        shortcuts_box.set_border_width(8)
        main_vbox.pack_end(shortcuts_box, False, False, 0)

        shortcuts_label = Gtk.Label()
        shortcuts_label.set_markup("<small><b>Keyboard Shortcuts:</b> Escape/Ctrl+W = Cancel | Ctrl+S = Save | Tab = Navigate</small>")
        shortcuts_label.set_xalign(0.0)
        shortcuts_label.get_style_context().add_class("dim-label")
        shortcuts_box.pack_start(shortcuts_label, False, False, 0)

        # Separator
        main_vbox.pack_end(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # Button box at bottom of window (outside columns)
        button_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_container.set_border_width(12)
        main_vbox.pack_end(button_container, False, False, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_hexpand(True)
        button_container.pack_start(button_box, True, True, 0)

        cancel_button = Gtk.Button(label="Cancel")
        save_button = Gtk.Button(label="Save")
        button_box.pack_start(cancel_button, False, False, 0)
        button_box.pack_start(save_button, False, False, 0)

        def close_window(*_args) -> None:
            global _settings_window, _capture_listener
            if _settings_window is None:
                return
            window_ref = _settings_window
            _settings_window = None
            window_ref.destroy()
            capture_state["active"] = False
            state["hotkey_capture_active"] = False
            if _capture_listener:
                with contextlib.suppress(Exception):
                    _capture_listener.stop()
            _capture_listener = None

        def on_cancel(_button) -> None:
            close_window()

        def on_save_clicked(_button) -> None:
            # Save theme preference
            theme_pref = theme_combo.get_active_id() or "auto"
            cfg["theme_preference"] = theme_pref

            language = language_combo.get_active_id() or "de"
            cfg["language"] = language

            device_id = device_combo.get_active_id() or "__default__"
            cfg["device_name"] = device_map.get(device_id)

            cfg["paste_sequence"] = paste_combo.get_active_id() or "auto"
            cfg["paste_delay_ms"] = int(round(paste_delay_spin.get_value()))

            cfg["notifications_enabled"] = notify_switch.get_active()
            cfg["auto_paste_enabled"] = auto_switch.get_active()
            cfg["use_vad"] = vad_switch.get_active() if VAD_AVAILABLE else False
            cfg["vad_energy_ratio"] = round(float(vad_scale.get_value()), 3)
            cfg["vad_bridge_ms"] = int(round(bridge_scale.get_value()))
            cfg["vad_min_energy_frames"] = int(round(frames_scale.get_value()))
            cfg["vad_auto_stop_enabled"] = (auto_stop_switch.get_active() and vad_switch.get_active()) if VAD_AVAILABLE else False
            cfg["vad_auto_stop_silence_seconds"] = round(float(auto_stop_scale.get_value()), 1)
            cfg["stop_tail_grace_ms"] = int(round(stop_tail_scale.get_value()))

            # Save backend settings
            cfg["transcription_backend"] = backend_combo.get_active_id() or "openai"
            cfg["faster_whisper_model"] = fw_model_combo.get_active_id() or "medium"
            cfg["streaming_model"] = streaming_model_combo.get_active_id() or "tiny"

            # Save audio processing settings
            cfg["noise_reduction_enabled"] = nr_switch.get_active() if noise_reduction_available else False
            cfg["noise_reduction_strength"] = round(float(nr_scale.get_value()), 1)
            cfg["min_audio_energy"] = round(float(min_energy_scale.get_value()), 4)
            cfg["postprocess_enabled"] = pp_switch.get_active()
            cfg["postprocess_fix_spacing"] = pp_spacing_switch.get_active() and pp_switch.get_active()
            cfg["postprocess_fix_capitalization"] = pp_caps_switch.get_active() and pp_switch.get_active()
            cfg["chunking_enabled"] = chunking_switch.get_active()
            cfg["live_overlay_enabled"] = overlay_switch.get_active()
            cfg["live_overlay_font_size"] = int(font_scale.get_value())
            cfg["live_overlay_opacity"] = round(float(opacity_scale.get_value()), 2)
            cfg["live_overlay_width"] = int(width_scale.get_value())
            cfg["live_overlay_height"] = int(height_scale.get_value())
            cfg["live_overlay_display_duration"] = round(float(duration_scale.get_value()), 1)

            # Save audio feedback settings
            cfg["audio_feedback_enabled"] = audio_fb_switch.get_active()
            cfg["audio_feedback_volume"] = round(float(audio_fb_volume_scale.get_value()), 1)

            if cfg.get("auto_paste_enabled"):
                state["wayland_notice_shown"] = False

            save_config()
            update_device_index()

            if cfg.get("auto_paste_enabled") and is_wayland_session():
                notify("Wayland session: auto-paste remains clipboard-only.")
            notify("Settings saved.")

            # Call user callback if provided
            if on_save:
                on_save()

            close_window()

        cancel_button.connect("clicked", on_cancel)
        save_button.connect("clicked", on_save_clicked)
        window.connect("destroy", lambda *_: close_window())

        # Add keyboard shortcuts
        def on_key_press(widget, event):
            """Handle keyboard shortcuts in settings window."""
            # Get key name and modifiers
            keyval = event.keyval
            state = event.state

            # Check for Ctrl modifier
            ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)

            # Escape to close
            if keyval == Gdk.KEY_Escape:
                on_cancel(None)
                return True

            # Ctrl+S to save
            if ctrl_pressed and keyval == Gdk.KEY_s:
                on_save_clicked(None)
                return True

            # Ctrl+W to close (common shortcut)
            if ctrl_pressed and keyval == Gdk.KEY_w:
                on_cancel(None)
                return True

            return False

        window.connect("key-press-event", on_key_press)

        # Add keyboard shortcut hints to button tooltips
        save_button.set_tooltip_text("Save settings and close (Ctrl+S)")
        cancel_button.set_tooltip_text("Cancel and close without saving (Escape or Ctrl+W)")

        window.show_all()
        window.present()  # Bring window to front
        window.set_keep_above(True)  # Force window to stay on top initially
        # After a short delay, disable keep-above to allow normal window behavior
        GLib.timeout_add(500, lambda: window.set_keep_above(False) or False)

        # Thread-safe assignment
        with _settings_window_lock:
            _settings_window = window
        return False

    GLib.idle_add(_present_settings)
