"""WhisprBar UI package - settings, overlay, diagnostics, history.

Re-exports all public UI functions for backwards compatibility.
Existing code can continue to use:
    from whisprbar.ui import open_settings_window
    from whisprbar.ui import show_live_overlay
"""

from .overlay import show_live_overlay, update_live_overlay, hide_live_overlay
from .diagnostics import maybe_show_first_run_diagnostics, open_diagnostics_window, _run_diagnostics_cli
from .history import open_history_window
from .settings import open_settings_window
from .scratchpad import open_scratchpad_window
from .theme import apply_theme_css, get_effective_theme, detect_system_theme
from .helpers import make_row, build_switch
