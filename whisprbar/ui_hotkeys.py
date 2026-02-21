"""UI-facing helpers for hotkey settings validation and messaging."""

from __future__ import annotations

from typing import Dict, Optional

from whisprbar.hotkeys import find_hotkey_conflicts, hotkey_to_label, parse_hotkey


def build_pending_hotkeys(
    hotkeys_config: Dict[str, Optional[str]],
    editable_actions: Dict[str, str],
) -> Dict[str, Optional[str]]:
    """Create editable hotkey state and ensure all editable actions exist."""
    pending_hotkeys = dict(hotkeys_config)
    for action_id in editable_actions:
        pending_hotkeys.setdefault(action_id, None)
    return pending_hotkeys


def get_hotkey_conflicts_for_actions(
    pending_hotkeys: Dict[str, Optional[str]],
    editable_actions: Dict[str, str],
) -> Dict[str, list[str]]:
    """Find conflicts within the editable settings actions only."""
    scoped_hotkeys = {
        action_id: pending_hotkeys.get(action_id)
        for action_id in editable_actions
    }
    return find_hotkey_conflicts(scoped_hotkeys)


def build_hotkey_conflict_message(
    conflicts: Dict[str, list[str]],
    editable_actions: Dict[str, str],
) -> Optional[str]:
    """Build user-facing conflict message from detected collisions."""
    if not conflicts:
        return None
    conflict_hotkey = sorted(conflicts.keys())[0]
    conflict_actions = conflicts[conflict_hotkey]
    action_names = ", ".join(
        editable_actions.get(action_id, action_id) for action_id in conflict_actions
    )
    try:
        readable_hotkey = hotkey_to_label(parse_hotkey(conflict_hotkey))
    except Exception:
        readable_hotkey = conflict_hotkey
    return (
        f"Hotkey-Konflikt: {readable_hotkey} ist mehrfach belegt "
        f"({action_names})."
    )

