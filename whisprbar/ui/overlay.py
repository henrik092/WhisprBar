#!/usr/bin/env python3
"""
whisprbar/ui/overlay.py - Live transcription overlay
"""

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

from whisprbar.config import save_config
from whisprbar.ui.theme import get_effective_theme

# Module state
_overlay_window = None
_overlay_window_lock = threading.Lock()


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
            if window_ref:
                window_ref.destroy()
                _overlay_window = None
        except Exception:
            pass
