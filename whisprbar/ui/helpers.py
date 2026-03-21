#!/usr/bin/env python3
"""
whisprbar/ui/helpers.py - Shared GTK helper functions used across multiple UI components
"""

from typing import Optional

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
except (ImportError, ValueError):
    Gtk = None


def make_row(
    label_text: str,
    widget,
    tooltip: Optional[str] = None,
    expand: bool = False,
    defaults_text: Optional[str] = None,
):
    """Create a horizontal row with a label and widget.

    Args:
        label_text: Text for the label
        widget: GTK widget to place on the right side
        tooltip: Optional tooltip text
        expand: Whether the widget should expand
        defaults_text: Optional defaults hint text

    Returns:
        Gtk.Box containing the row
    """
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
    """Create a switch with a label row.

    Args:
        label_text: Text for the label
        active: Initial switch state
        tooltip: Optional tooltip text

    Returns:
        Tuple of (row, switch) where row is a Gtk.Box and switch is a Gtk.Switch
    """
    switch = Gtk.Switch()
    switch.set_active(active)
    if tooltip:
        switch.set_tooltip_text(tooltip)
    row = make_row(label_text, switch, tooltip=tooltip)
    return row, switch
