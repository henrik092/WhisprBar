"""Shared hotkey action definitions used by UI and runtime registration."""

from typing import Dict, Tuple

# Action order matters:
# - Runtime registration keeps first action on duplicate bindings.
# - Settings UI displays actions in this order.
HOTKEY_ACTION_ORDER: Tuple[str, ...] = (
    "toggle_recording",
    "start_recording",
    "stop_recording",
    "open_settings",
    "show_history",
    "hands_free_recording",
    "command_mode",
    "paste_last_transcript",
    "copy_last_transcript",
    "open_scratchpad",
)

# Labels used in the settings window.
HOTKEY_SETTINGS_LABELS: Dict[str, str] = {
    "toggle_recording": "Aufnahme umschalten",
    "start_recording": "Aufnahme starten",
    "stop_recording": "Aufnahme stoppen",
    "open_settings": "Einstellungen öffnen",
    "show_history": "Verlauf anzeigen",
    "hands_free_recording": "Hands-free Aufnahme",
    "command_mode": "Command Mode",
    "paste_last_transcript": "Letztes Transkript einfügen",
    "copy_last_transcript": "Letztes Transkript kopieren",
    "open_scratchpad": "Scratchpad öffnen",
}
