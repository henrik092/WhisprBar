"""Local Flow scratchpad window and storage."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from whisprbar.config import DATA_DIR
from whisprbar.utils import copy_to_clipboard, notify

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
except (ImportError, ValueError):
    Gtk = GLib = None

NOTES_PATH = DATA_DIR / "notes.jsonl"
_scratchpad_window = None


def _now_id() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_notes(path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Read local scratchpad notes from JSONL."""
    notes_path = path or NOTES_PATH
    if not notes_path.exists():
        return []
    notes = []
    for line in notes_path.read_text(encoding="utf-8").splitlines():
        try:
            note = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(note, dict):
            notes.append(note)
    return notes


def _write_notes(notes: List[Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for note in notes:
            handle.write(json.dumps(note, ensure_ascii=False) + "\n")


def create_note(
    text: str,
    path: Optional[Path] = None,
    storage_enabled: bool = True,
) -> Dict[str, str]:
    """Create a note and optionally persist it."""
    note_id = _now_id()
    note = {"id": note_id, "updated_at": note_id, "text": text}
    if storage_enabled:
        notes_path = path or NOTES_PATH
        notes = list_notes(notes_path)
        notes.append(note)
        _write_notes(notes, notes_path)
    return note


def update_note(
    note_id: str,
    text: str,
    path: Optional[Path] = None,
    storage_enabled: bool = True,
) -> Dict[str, str]:
    """Update an existing note or create it if missing."""
    updated_at = _now_id()
    note = {"id": note_id, "updated_at": updated_at, "text": text}
    if storage_enabled:
        notes_path = path or NOTES_PATH
        notes = [existing for existing in list_notes(notes_path) if existing.get("id") != note_id]
        notes.append(note)
        _write_notes(notes, notes_path)
    return note


def open_scratchpad_window(cfg: dict) -> None:
    """Open a small local scratchpad window."""
    global _scratchpad_window
    if Gtk is None:
        notify("Scratchpad unavailable: GTK not installed.")
        return
    if _scratchpad_window is not None:
        _scratchpad_window.present()
        return

    notes = list_notes()
    active_note = notes[-1] if notes else create_note("", storage_enabled=cfg.get("flow_history_storage") != "never")
    storage_enabled = cfg.get("flow_history_storage") != "never"

    window = Gtk.Window(title="WhisprBar Scratchpad")
    window.set_default_size(520, 360)
    window.set_keep_above(True)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_border_width(8)
    window.add(box)

    text_view = Gtk.TextView()
    text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    buffer = text_view.get_buffer()
    buffer.set_text(active_note.get("text", ""))
    box.pack_start(text_view, True, True, 0)

    buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    new_button = Gtk.Button(label="New")
    copy_button = Gtk.Button(label="Copy")
    buttons.pack_start(new_button, False, False, 0)
    buttons.pack_start(copy_button, False, False, 0)
    box.pack_start(buttons, False, False, 0)

    state = {"note_id": active_note["id"], "save_source": 0}

    def save_buffer() -> bool:
        start, end = buffer.get_bounds()
        text = buffer.get_text(start, end, True)
        update_note(state["note_id"], text, storage_enabled=storage_enabled)
        state["save_source"] = 0
        return False

    def schedule_save(*_args) -> None:
        if state["save_source"] and GLib is not None:
            GLib.source_remove(state["save_source"])
        state["save_source"] = GLib.timeout_add(2000, save_buffer) if GLib is not None else 0

    buffer.connect("changed", schedule_save)

    def new_note(*_args) -> None:
        note = create_note("", storage_enabled=storage_enabled)
        state["note_id"] = note["id"]
        buffer.set_text("")

    def copy_note(*_args) -> None:
        start, end = buffer.get_bounds()
        text = buffer.get_text(start, end, True)
        notify("Copied scratchpad") if copy_to_clipboard(text) else notify("Failed to copy scratchpad")

    new_button.connect("clicked", new_note)
    copy_button.connect("clicked", copy_note)

    def on_destroy(*_args) -> None:
        global _scratchpad_window
        save_buffer()
        _scratchpad_window = None

    window.connect("destroy", on_destroy)
    _scratchpad_window = window
    window.show_all()
