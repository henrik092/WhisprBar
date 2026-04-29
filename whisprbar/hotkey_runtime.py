"""Runtime helpers for resolving configured hotkeys into unique registrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from whisprbar.hotkeys import (
    HotkeyBinding,
    find_hotkey_conflicts,
    hotkey_to_config,
    parse_hotkey,
)


@dataclass
class HotkeyResolutionResult:
    """Resolved runtime hotkey state."""

    registrations: List[Tuple[str, HotkeyBinding, str]]
    conflicts: Dict[str, List[str]]
    skipped_duplicates: List[Tuple[str, str, str]]
    parse_errors: List[Tuple[str, str, str]]


def build_runtime_hotkey_config(
    hotkeys_config: Dict[str, Optional[str]], legacy_hotkey: str
) -> Dict[str, Optional[str]]:
    """Build canonical runtime hotkey mapping from config state."""
    return {
        "toggle_recording": hotkeys_config.get("toggle_recording") or legacy_hotkey,
        "start_recording": hotkeys_config.get("start_recording"),
        "stop_recording": hotkeys_config.get("stop_recording"),
        "open_settings": hotkeys_config.get("open_settings"),
        "show_history": hotkeys_config.get("show_history"),
        "hands_free_recording": hotkeys_config.get("hands_free_recording"),
        "command_mode": hotkeys_config.get("command_mode"),
        "paste_last_transcript": hotkeys_config.get("paste_last_transcript"),
        "copy_last_transcript": hotkeys_config.get("copy_last_transcript"),
        "open_scratchpad": hotkeys_config.get("open_scratchpad"),
    }


def resolve_runtime_hotkeys(
    configured_hotkeys: Dict[str, Optional[str]],
    action_order: Tuple[str, ...],
) -> HotkeyResolutionResult:
    """Resolve configured hotkeys into unique, registerable bindings."""
    conflicts = find_hotkey_conflicts(configured_hotkeys)
    seen_bindings = set()
    registrations: List[Tuple[str, HotkeyBinding, str]] = []
    skipped_duplicates: List[Tuple[str, str, str]] = []
    parse_errors: List[Tuple[str, str, str]] = []

    for action in action_order:
        hotkey_str = configured_hotkeys.get(action)
        if not hotkey_str:
            continue
        try:
            binding = parse_hotkey(hotkey_str)
            normalized = hotkey_to_config(binding)
        except Exception as exc:
            parse_errors.append((action, hotkey_str, str(exc)))
            continue

        if normalized in seen_bindings:
            skipped_duplicates.append((action, hotkey_str, normalized))
            continue

        seen_bindings.add(normalized)
        registrations.append((action, binding, hotkey_str))

    return HotkeyResolutionResult(
        registrations=registrations,
        conflicts=conflicts,
        skipped_duplicates=skipped_duplicates,
        parse_errors=parse_errors,
    )
