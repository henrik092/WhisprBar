#!/usr/bin/env python3
"""
whisprbar/ui/theme.py - Theme detection and CSS application functions
"""

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk
except (ImportError, ValueError):
    Gtk = Gdk = None


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
