#!/usr/bin/env python3
"""Basic configuration sanity check for functional test suite."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from whisprbar.config import load_config, cfg, CONFIG_PATH, get_env_file_path


def main() -> int:
    print("=" * 60)
    print("WhisprBar V6 - Configuration Check")
    print("=" * 60)

    print(f"Config path: {CONFIG_PATH}")
    print(f"Env path:    {get_env_file_path()}")

    try:
        loaded = load_config()
    except Exception as exc:
        print(f"\n✗ Failed to load config: {exc}")
        return 1

    required_keys = ["language", "hotkeys", "transcription_backend", "auto_paste_enabled"]
    missing = [key for key in required_keys if key not in loaded]
    if missing:
        print(f"\n✗ Missing required config keys: {', '.join(missing)}")
        return 1

    hotkeys = loaded.get("hotkeys", {})
    expected_hotkey_actions = ["toggle_recording", "start_recording", "stop_recording", "open_settings"]
    missing_actions = [action for action in expected_hotkey_actions if action not in hotkeys]
    if missing_actions:
        print(f"\n✗ Missing hotkey actions: {', '.join(missing_actions)}")
        return 1

    # Ensure global cfg reference got updated as expected.
    if cfg.get("hotkeys", {}).get("toggle_recording") != hotkeys.get("toggle_recording"):
        print("\n✗ Global cfg state mismatch after load_config()")
        return 1

    print("\n✓ Config loaded successfully")
    print(f"✓ Language: {loaded.get('language')}")
    print(f"✓ Backend:  {loaded.get('transcription_backend')}")
    print(f"✓ Hotkeys:  {len(hotkeys)} actions configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

