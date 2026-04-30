#!/usr/bin/env python3
"""
whisprbar/ui/diagnostics.py - First-run wizard and diagnostics window
"""

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
except (ImportError, ValueError):
    Gtk = Gdk = GLib = None

from whisprbar.config import save_config, cfg
from whisprbar.i18n import t
from whisprbar.utils import (
    collect_diagnostics,
    DiagnosticResult,
    STATUS_OK,
    STATUS_WARN,
    STATUS_ERROR,
    STATUS_ICON_NAME,
    CLI_STATUS_LABEL,
)
from whisprbar.ui.theme import get_effective_theme, apply_theme_css

# Module state
_diagnostics_window = None


def _mark_first_run_complete(cfg: dict) -> None:
    """Mark first run as complete and save config."""
    if not cfg.get("first_run_complete", False):
        cfg["first_run_complete"] = True
        save_config()


def _run_diagnostics_cli(cfg: dict) -> int:
    """Run diagnostics in CLI mode and return exit code."""
    print(f"\n=== {t('diagnostics.title', cfg)} ===\n")
    results = collect_diagnostics()

    errors = sum(1 for r in results if r.status == STATUS_ERROR)
    warnings = sum(1 for r in results if r.status == STATUS_WARN)

    for res in results:
        status_label = CLI_STATUS_LABEL.get(res.status, res.status.upper())
        print(f"[{status_label}] {res.label}")
        print(f"  {res.detail}")
        if res.remedy:
            print(f"  {t('diagnostics.fix', cfg)}: {res.remedy}")
        print()

    if errors:
        print(t("diagnostics.summary_errors", cfg).format(errors=errors, warnings=warnings))
        return 1
    elif warnings:
        print(t("diagnostics.summary_warnings", cfg).format(warnings=warnings))
        return 0
    else:
        print(t("diagnostics.all_passed", cfg))
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
        print(t("diagnostics.window_requires_gtk", cfg))
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

        window = Gtk.Window(title=t("diagnostics.title", cfg))
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
            title_label.set_markup(f"<b>{GLib.markup_escape_text(t('diagnostics.environment', cfg))}</b>")
        else:
            title_label.set_text(t("diagnostics.environment", cfg))
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

        rerun_button = Gtk.Button(label=t("diagnostics.run_again", cfg))
        close_label = t("diagnostics.done" if first_run else "diagnostics.close", cfg)
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
                summary_label.set_text(t("diagnostics.summary_errors", cfg).format(errors=errors, warnings=warnings))
            elif warnings:
                summary_label.set_text(t("diagnostics.summary_warnings", cfg).format(warnings=warnings))
            else:
                summary_label.set_text(t("diagnostics.all_passed", cfg))

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
                    remedy_text = f"{t('diagnostics.fix', cfg)}: {res.remedy}"
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
