#!/usr/bin/env python3
"""Render a static WhisprBar tray menu mock for screenshots."""

from __future__ import annotations

from dataclasses import dataclass, field
import subprocess
from typing import List, Optional
import tkinter as tk
from tkinter import font

MENU_BACKGROUND = "#2f343f"
MENU_BORDER = "#15171d"
MENU_FOREGROUND = "#f2f2f2"
MENU_DISABLED = "#8d939f"
INDICATOR_COLOR = "#fbd86d"
SEPARATOR_COLOR = "#3c414a"
SEPARATOR_PADY = 4
ROW_PADDING_X = 10
ROW_PADDING_Y = 2
INDENT_STEP = 16
INDICATOR_SIZE = 14
WINDOW_PADDING = 6


@dataclass
class MenuItem:
    label: str = ""
    kind: str = "command"
    checked: Optional[bool] = None
    disabled: bool = False
    children: List["MenuItem"] = field(default_factory=list)
    note: Optional[str] = None


def build_menu_model() -> List[MenuItem]:
    """Return the static menu structure we want to display."""
    return [
        MenuItem(label="Start Recording"),
        MenuItem(kind="separator"),
        MenuItem(label="Session: Ready", kind="status", disabled=True),
        MenuItem(label="Tray: AppIndicator", kind="status", disabled=True),
        MenuItem(label="Settings..."),
        MenuItem(label="Diagnostics..."),
        MenuItem(kind="separator"),
        MenuItem(
            label="Language",
            kind="submenu",
            children=[
                MenuItem(label="Deutsch", kind="radio"),
                MenuItem(label="English", kind="radio", checked=True),
            ],
        ),
        MenuItem(
            label="Input Device",
            kind="submenu",
            children=[
                MenuItem(label="System Default", kind="radio", checked=True),
                MenuItem(label="USB Microphone", kind="radio"),
                MenuItem(label="Loopback Monitor", kind="radio"),
            ],
        ),
        MenuItem(label="Notifications", kind="check", checked=False),
        MenuItem(label="Auto Paste", kind="check", checked=True),
        MenuItem(
            label="Paste Mode",
            kind="submenu",
            children=[
                MenuItem(label="Auto", kind="radio", checked=True),
                MenuItem(label="Clipboard", kind="radio"),
                MenuItem(label="Active Window", kind="radio"),
            ],
        ),
        MenuItem(
            label="Voice Activity Detection",
            kind="check",
            checked=False,
            disabled=True,
            note="(requires webrtcvad)",
        ),
        MenuItem(kind="separator"),
        MenuItem(label="Hotkey (F9)", kind="status", disabled=True),
        MenuItem(kind="separator"),
        MenuItem(label="Quit"),
    ]


def render_separator(parent: tk.Widget) -> None:
    separator = tk.Frame(parent, height=1, bg=SEPARATOR_COLOR, bd=0, highlightthickness=0)
    separator.pack(fill="x", padx=ROW_PADDING_X, pady=SEPARATOR_PADY)


def create_indicator(parent: tk.Widget, item: MenuItem, fg: str) -> tk.Widget:
    indicator = tk.Canvas(
        parent,
        width=INDICATOR_SIZE,
        height=INDICATOR_SIZE,
        bg=MENU_BACKGROUND,
        highlightthickness=0,
        bd=0,
    )
    outline = fg
    fill = INDICATOR_COLOR if item.checked else MENU_BACKGROUND
    if item.kind == "check":
        indicator.create_rectangle(
            2,
            2,
            INDICATOR_SIZE - 2,
            INDICATOR_SIZE - 2,
            outline=outline,
            width=1,
            fill=fill,
        )
        if item.checked:
            indicator.create_line(4, 7, 7, 10, 11, 4, fill=MENU_BACKGROUND, width=2, capstyle="round")
    elif item.kind == "radio":
        indicator.create_oval(
            2,
            2,
            INDICATOR_SIZE - 2,
            INDICATOR_SIZE - 2,
            outline=outline,
            width=1,
            fill=MENU_BACKGROUND,
        )
        if item.checked:
            indicator.create_oval(
                5,
                5,
                INDICATOR_SIZE - 5,
                INDICATOR_SIZE - 5,
                outline="",
                fill=INDICATOR_COLOR,
            )
    return indicator


def render_row(parent: tk.Widget, item: MenuItem, indent: int) -> None:
    fg = MENU_DISABLED if item.disabled else MENU_FOREGROUND
    row = tk.Frame(parent, bg=MENU_BACKGROUND, highlightthickness=0, bd=0)
    row.pack(fill="x")

    indent_pad = tk.Frame(
        row,
        width=ROW_PADDING_X + indent * INDENT_STEP,
        bg=MENU_BACKGROUND,
        highlightthickness=0,
        bd=0,
    )
    indent_pad.pack(side="left")

    if item.kind in {"check", "radio"}:
        indicator = create_indicator(row, item, fg)
        indicator.pack(side="left")
    else:
        spacer = tk.Frame(row, width=INDICATOR_SIZE, bg=MENU_BACKGROUND, highlightthickness=0, bd=0)
        spacer.pack(side="left")

    between = tk.Frame(row, width=4, bg=MENU_BACKGROUND, highlightthickness=0, bd=0)
    between.pack(side="left")

    if item.kind == "submenu":
        arrow = tk.Canvas(
            row,
            width=10,
            height=INDICATOR_SIZE,
            bg=MENU_BACKGROUND,
            highlightthickness=0,
            bd=0,
        )
        arrow_color = fg
        arrow.create_polygon(2, 3, 9, INDICATOR_SIZE // 2, 2, INDICATOR_SIZE - 3, fill=arrow_color, outline="")
        arrow.pack(side="right", padx=(0, ROW_PADDING_X))
    else:
        right_pad = tk.Frame(row, width=ROW_PADDING_X, bg=MENU_BACKGROUND, highlightthickness=0, bd=0)
        right_pad.pack(side="right")

    text = item.label
    if item.note:
        text = f"{text} {item.note}".strip()

    label = tk.Label(
        row,
        text=text,
        anchor="w",
        justify="left",
        bg=MENU_BACKGROUND,
        fg=fg,
        pady=ROW_PADDING_Y,
    )
    label.pack(side="left", fill="x", expand=True)


def render_menu(parent: tk.Widget, items: List[MenuItem], indent: int = 0) -> None:
    for item in items:
        if item.kind == "separator":
            render_separator(parent)
            continue

        render_row(parent, item, indent)

        if item.children:
            render_menu(parent, item.children, indent + 1)


def detect_system_font() -> Optional[str]:
    """Try to read the desktop interface font via gsettings."""
    schemas = [
        ("org.cinnamon.desktop.interface", "font-name"),
        ("org.gnome.desktop.interface", "font-name"),
    ]
    for schema, key in schemas:
        try:
            value = subprocess.check_output(
                ["gsettings", "get", schema, key],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except Exception:
            continue
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        if value:
            return value
    return None


def configure_fonts(root: tk.Tk) -> None:
    try:
        menu_font = font.nametofont("TkMenuFont")
    except tk.TclError:
        menu_font = font.nametofont("TkDefaultFont")
    system_font = detect_system_font()
    family = None
    size = 11
    if system_font:
        parts = system_font.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            family, size_str = parts
            size = int(size_str)
        else:
            family = system_font
    try:
        if family is not None:
            menu_font.configure(family=family, size=size)
        else:
            menu_font.configure(size=size)
    except tk.TclError:
        menu_font.configure(size=11)
    root.option_add("*Font", menu_font)


def build_window() -> tk.Tk:
    root = tk.Tk()
    root.title("WhisprBar Tray (Mock)")
    root.configure(bg=MENU_BORDER)
    root.resizable(False, False)
    configure_fonts(root)

    outer = tk.Frame(root, bg=MENU_BORDER, highlightthickness=0, bd=0)
    outer.pack(padx=WINDOW_PADDING, pady=WINDOW_PADDING)

    frame = tk.Frame(
        outer,
        bg=MENU_BACKGROUND,
        highlightbackground=MENU_BORDER,
        highlightthickness=1,
        bd=0,
    )
    frame.pack()

    render_menu(frame, build_menu_model())

    return root


def main() -> None:
    root = build_window()
    root.mainloop()


if __name__ == "__main__":
    main()
