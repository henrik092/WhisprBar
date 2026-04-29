# Settings UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old tabbed settings layout with the selected refined-B sidebar settings experience while preserving all existing settings behavior.

**Architecture:** Keep GTK 3 and the existing `open_settings_window()` entry point. Replace `Gtk.Notebook` with a `Gtk.Stack` plus `Gtk.StackSidebar`, add a modern header and page CSS, and keep existing controls/save logic intact. Add only focused helper code where it lowers risk.

**Tech Stack:** Python 3, GTK 3 via PyGObject, existing WhisprBar config and Flow dictionary helpers, pytest.

---

### Task 1: Commit Plan

**Files:**
- Create: `docs/superpowers/plans/2026-04-29-settings-ux-redesign.md`

- [ ] **Step 1: Review spec coverage**

Verify the plan covers:

- sidebar navigation
- consistent page layout
- modern soft-dark visual style
- existing settings still reachable
- Flow dictionary editor still works
- automated and GTK smoke verification

- [ ] **Step 2: Commit the plan**

Run:

```bash
git add docs/superpowers/plans/2026-04-29-settings-ux-redesign.md
git commit -m "docs: plan settings ux redesign"
```

Expected: commit succeeds.

### Task 2: Add Sidebar Settings Shell

**Files:**
- Modify: `whisprbar/ui/settings.py`

- [ ] **Step 1: Replace notebook shell with header + stack**

In `open_settings_window()`, change the top layout from `Gtk.Notebook` to:

```python
window.set_default_size(820, 680)

main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
main_vbox.get_style_context().add_class("settings-root")
window.add(main_vbox)

header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
header.get_style_context().add_class("settings-header")
main_vbox.pack_start(header, False, False, 0)

brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
brand.get_style_context().add_class("settings-brand")
header.pack_start(brand, True, True, 0)

brand_badge = Gtk.Label(label="WB")
brand_badge.get_style_context().add_class("settings-brand-badge")
brand.pack_start(brand_badge, False, False, 0)

brand_text = Gtk.Label(label="WhisprBar Settings")
brand_text.set_xalign(0.0)
brand_text.get_style_context().add_class("settings-brand-title")
brand.pack_start(brand_text, False, False, 0)

content_shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
content_shell.get_style_context().add_class("settings-shell")
main_vbox.pack_start(content_shell, True, True, 0)

stack = Gtk.Stack()
stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
stack.set_transition_duration(140)

sidebar = Gtk.StackSidebar()
sidebar.set_stack(stack)
sidebar.get_style_context().add_class("settings-sidebar")
content_shell.pack_start(sidebar, False, False, 0)
content_shell.pack_start(stack, True, True, 0)
```

- [ ] **Step 2: Add page helper**

Add local helper:

```python
def create_settings_page() -> tuple:
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("settings-page-scroll")
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    page.set_border_width(18)
    page.get_style_context().add_class("settings-page")
    scroll.add(page)
    return scroll, page
```

- [ ] **Step 3: Replace page registration**

Replace `notebook.append_page(...)` calls:

```python
basis_scroll, basis_page = create_settings_page()
stack.add_titled(basis_scroll, "general", "General")

audio_scroll, audio_page = create_settings_page()
stack.add_titled(audio_scroll, "recording", "Recording")

trans_scroll, trans_page = create_settings_page()
stack.add_titled(trans_scroll, "transcription", "Transcription")

advanced_scroll, adv_page = create_settings_page()
stack.add_titled(advanced_scroll, "advanced", "Advanced")

flow_scroll, flow_page = create_settings_page()
stack.add_titled(flow_scroll, "flow", "Flow")
```

Remove the old `Gtk.Notebook` creation.

- [ ] **Step 4: Run compile check**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m py_compile whisprbar/ui/settings.py
```

Expected: exit 0.

### Task 3: Apply Modern Settings Styling

**Files:**
- Modify: `whisprbar/ui/settings.py`

- [ ] **Step 1: Add local CSS helper**

Add a helper in `_present_settings()` after `apply_theme_css(window, theme)`:

```python
def apply_settings_redesign_css() -> None:
    css = b"""
    .settings-root {
        background: #0d1218;
    }
    .settings-header {
        min-height: 46px;
        padding: 0 14px;
        background: #111820;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .settings-brand {
        margin: 0;
    }
    .settings-brand-badge {
        min-width: 26px;
        min-height: 26px;
        border-radius: 7px;
        background: #63c7f4;
        color: #071118;
        font-weight: 800;
        font-size: 10px;
    }
    .settings-brand-title {
        color: #eef5fb;
        font-weight: 700;
        font-size: 14px;
    }
    .settings-shell {
        background: #0d1218;
    }
    .settings-sidebar {
        min-width: 176px;
        background: #101720;
        border-right: 1px solid rgba(255,255,255,0.08);
        padding: 10px 6px;
    }
    .settings-page-scroll {
        background: #0d1218;
    }
    .settings-page {
        background: #0d1218;
    }
    .settings-row {
        min-height: 38px;
        padding: 6px 10px;
        border-radius: 8px;
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.06);
    }
    .settings-section-label {
        color: #eef5fb;
        font-size: 13px;
        font-weight: 700;
        margin-top: 4px;
    }
    .settings-bottom-bar {
        padding: 10px 12px;
        background: #111820;
        border-top: 1px solid rgba(255,255,255,0.08);
    }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )
```

Then call:

```python
apply_settings_redesign_css()
```

- [ ] **Step 2: Style setting rows**

Inside local `make_row()`, add:

```python
row.get_style_context().add_class("settings-row")
```

For section labels created in the redesigned area, add `settings-section-label` where practical.

- [ ] **Step 3: Style bottom button bar**

Add:

```python
button_container.get_style_context().add_class("settings-bottom-bar")
```

- [ ] **Step 4: Run GTK smoke test**

Run:

```bash
timeout 5 /home/rik/WhisprBar/.venv/bin/python - <<'PY'
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from whisprbar.config import load_config
from whisprbar.ui.settings import open_settings_window

open_settings_window(load_config(), {}, on_save=None)
GLib.timeout_add(1200, Gtk.main_quit)
Gtk.main()
print("settings_smoke_ok")
PY
```

Expected: `settings_smoke_ok`.

### Task 4: Preserve Flow Dictionary Editing and Verify Complex Flows

**Files:**
- Modify: `whisprbar/ui/settings.py` only if needed
- Test: existing Flow tests

- [ ] **Step 1: Verify dictionary editor remains on Flow page**

Open the file and confirm the `dictionary_store`, `dictionary_view`, `Add`, and `Remove` controls are still packed into `flow_page`.

- [ ] **Step 2: Run focused tests**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m pytest tests/test_flow_dictionary.py tests/test_flow_formatting.py tests/test_flow_pipeline.py -q
```

Expected: all pass.

- [ ] **Step 3: Run complex pipeline probe**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python - <<'PY'
from whisprbar.config import load_config
from whisprbar.flow.pipeline import process_flow_text

cfg = load_config().copy()
cfg.update({
    "flow_mode_enabled": True,
    "flow_dictionary_enabled": True,
    "flow_command_mode_enabled": True,
    "flow_smart_formatting_enabled": True,
    "flow_backtrack_enabled": True,
    "flow_rewrite_enabled": False,
})
for raw in [
    "Das ist ein Test mit Vispaba Komma und danach Punkt",
    "Erste Zeile Punkt neue Zeile zweite Zeile Komma Punkt",
    "eins erster Punkt zwei zweiter Punkt als Liste",
    "wir treffen uns heute streich das morgen Punkt",
]:
    out = process_flow_text(raw, cfg.get("language", "de"), cfg)
    print(repr(out.final_text), out.command, out.dictionary_hits, out.metadata)
PY
```

Expected output includes:

- `WhisprBar`
- a newline in the second scenario
- numbered list output
- `morgen.`

### Task 5: Full Verification, Restart, Commit

**Files:**
- Modified files from Tasks 2-4

- [ ] **Step 1: Run full test suite**

Run:

```bash
/home/rik/WhisprBar/.venv/bin/python -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Restart local feature app**

Stop the previous local WhisprBar process and start the worktree app again:

```bash
/home/rik/WhisprBar/.venv/bin/python - <<'PY'
import os, signal, subprocess, time
from pathlib import Path
for pid in [249771]:
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
    except ProcessLookupError:
        pass
log = Path("/tmp/whisprbar-flow-test.log")
out = log.open("ab")
proc = subprocess.Popen(
    ["/home/rik/WhisprBar/.venv/bin/python", "/home/rik/WhisprBar/.claude/worktrees/wispr-flow-parity/whisprbar.py"],
    cwd="/home/rik/WhisprBar/.claude/worktrees/wispr-flow-parity",
    stdin=subprocess.DEVNULL,
    stdout=out,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
print(proc.pid)
PY
```

Expected: new PID printed and `ps -p <pid>` shows WhisprBar running.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add whisprbar/ui/settings.py docs/superpowers/plans/2026-04-29-settings-ux-redesign.md
git commit -m "feat: redesign settings shell"
```

Expected: commit succeeds.
