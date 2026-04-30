#!/usr/bin/env python3
"""
whisprbar/ui/history.py - History window
"""

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
except (ImportError, ValueError):
    Gtk = Gdk = GLib = None

from whisprbar.utils import (
    APP_NAME,
    notify,
    read_history,
    clear_history,
    copy_to_clipboard,
)
from whisprbar.i18n import t
from whisprbar.ui.theme import get_effective_theme, apply_theme_css
from whisprbar.flow.stats import compute_dictation_stats

# Module state
_history_window = None


def open_history_window(cfg: dict) -> None:
    """Open a window showing recent transcription history."""
    global _history_window

    entries = read_history(limit=50)

    if Gtk is None:
        if not entries:
            notify(t("history.none", cfg))
            return
        preview = entries[0].get("text", "").strip() or t("history.empty", cfg)
        preview = preview[:120] + ("..." if len(preview) > 120 else "")
        print(f"{t('history.cli_title', cfg)}\n")
        for entry in entries[:10]:
            text = (entry.get("text", "") or "").strip() or t("history.empty", cfg)
            print(f"- {text}")
        notify(t("history.recent_notify", cfg).format(preview=preview))
        return

    if _history_window is not None:
        if GLib is not None:
            GLib.idle_add(lambda: _history_window.present() or False)
        else:
            _history_window.present()
        return

    def _present() -> bool:
        global _history_window
        if _history_window is not None:
            _history_window.present()
            return False

        window = Gtk.Window(title=t("history.title", cfg))
        window.set_default_size(680, 480)
        try:
            window.set_position(Gtk.WindowPosition.CENTER)
        except Exception:
            pass

        theme = get_effective_theme(cfg)
        apply_theme_css(window, theme)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_border_width(12)
        window.add(content)

        title = Gtk.Label()
        if GLib is not None:
            title.set_markup(f"<b>{GLib.markup_escape_text(t('history.recent', cfg))}</b>")
        else:
            title.set_text(t("history.recent", cfg))
        title.set_xalign(0.0)
        content.pack_start(title, False, False, 0)

        summary_label = Gtk.Label()
        summary_label.set_xalign(0.0)
        summary_label.set_line_wrap(True)
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

        refresh_button = Gtk.Button(label=t("history.refresh", cfg))
        clear_button = Gtk.Button(label=t("history.clear", cfg))
        close_button = Gtk.Button(label=t("history.close", cfg))
        button_box.pack_start(refresh_button, False, False, 0)
        button_box.pack_start(clear_button, False, False, 0)
        button_box.pack_start(close_button, False, False, 0)

        def populate() -> None:
            history_entries = read_history(limit=50)

            for child in list(results_box.get_children()):
                results_box.remove(child)

            if not history_entries:
                summary_label.set_text(t("history.none", cfg))
                empty_label = Gtk.Label(label=t("history.record_to_populate", cfg))
                empty_label.set_xalign(0.0)
                try:
                    empty_label.get_style_context().add_class("dim-label")
                except Exception:
                    pass
                results_box.pack_start(empty_label, False, False, 0)
                results_box.show_all()
                return

            stats = compute_dictation_stats(history_entries)
            summary_label.set_text(
                t("history.summary", cfg).format(
                    count=len(history_entries),
                    words=stats["word_count"],
                    duration=stats["duration_seconds"],
                    wpm=stats["words_per_minute"],
                )
            )
            for entry in history_entries:
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                row.set_hexpand(True)
                try:
                    row.set_margin_bottom(6)
                except Exception:
                    pass

                meta_parts = []
                if entry.get("ts"):
                    meta_parts.append(str(entry["ts"]))
                if entry.get("duration_seconds") is not None:
                    meta_parts.append(f"{float(entry['duration_seconds']):.1f}s")
                if entry.get("word_count") is not None:
                    meta_parts.append(f"{int(entry['word_count'])} {t('history.words', cfg)}")
                if entry.get("language"):
                    meta_parts.append(str(entry["language"]))
                meta_text = "  •  ".join(meta_parts) if meta_parts else t("history.transcript", cfg)

                meta_label = Gtk.Label()
                if GLib is not None:
                    meta_label.set_markup(f"<b>{GLib.markup_escape_text(meta_text)}</b>")
                else:
                    meta_label.set_text(meta_text)
                meta_label.set_xalign(0.0)
                row.pack_start(meta_label, False, False, 0)

                transcript = Gtk.Label(label=(entry.get("text", "") or t("history.empty", cfg)).strip() or t("history.empty", cfg))
                transcript.set_xalign(0.0)
                transcript.set_line_wrap(True)
                transcript.set_selectable(True)
                transcript.set_max_width_chars(100)
                row.pack_start(transcript, False, False, 0)

                flow_metadata = entry.get("metadata") or {}
                if flow_metadata:
                    flow_parts = []
                    if flow_metadata.get("profile_id"):
                        flow_parts.append(f"Flow: {flow_metadata['profile_id']}")
                    if flow_metadata.get("rewrite_status"):
                        flow_parts.append(f"rewrite: {flow_metadata['rewrite_status']}")
                    if flow_metadata.get("command"):
                        flow_parts.append(f"command: {flow_metadata['command']}")
                    if flow_parts:
                        flow_label = Gtk.Label(label=" | ".join(flow_parts))
                        flow_label.set_xalign(0.0)
                        try:
                            flow_label.get_style_context().add_class("dim-label")
                        except Exception:
                            pass
                        row.pack_start(flow_label, False, False, 0)

                action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                action_row.set_halign(Gtk.Align.START)
                copy_button = Gtk.Button(label=t("history.copy", cfg))
                copy_button.connect(
                    "clicked",
                    lambda *_args, text=entry.get("text", ""): notify(t("history.copied", cfg))
                    if copy_to_clipboard(text) else notify(t("history.copy_failed", cfg))
                )
                action_row.pack_start(copy_button, False, False, 0)
                row.pack_start(action_row, False, False, 0)

                divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                results_box.pack_start(row, False, False, 0)
                results_box.pack_start(divider, False, False, 0)

            results_box.show_all()

        def on_clear(*_args) -> None:
            clear_history()
            notify(t("history.cleared", cfg))
            populate()

        refresh_button.connect("clicked", lambda *_: populate())
        clear_button.connect("clicked", on_clear)
        close_button.connect("clicked", lambda *_: window.destroy())

        def on_destroy(*_args) -> None:
            global _history_window
            _history_window = None

        window.connect("destroy", on_destroy)

        populate()
        _history_window = window
        window.show_all()
        return False

    if GLib is not None:
        GLib.idle_add(_present)
    else:
        _present()
