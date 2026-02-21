#!/usr/bin/env python3
"""Check diagnose output for both X11 and Wayland session paths."""

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_BIN = REPO_ROOT / ".venv" / "bin" / "python3"
APP_ENTRY = REPO_ROOT / "whisprbar.py"


def run_diagnose(session_type: str) -> tuple[bool, str]:
    """Run --diagnose with a forced session type and validate output."""
    env = os.environ.copy()
    env["XDG_SESSION_TYPE"] = session_type

    try:
        result = subprocess.run(
            [str(PYTHON_BIN), str(APP_ENTRY), "--diagnose"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return False, f"Failed to run diagnose for {session_type}: {exc}"

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    if "WhisprBar Diagnostics" not in output:
        return False, f"Diagnose output malformed for {session_type}"
    if session_type == "x11" and "X11" not in output:
        return False, "X11 diagnose output missing X11 marker"
    if session_type == "wayland" and "Wayland" not in output:
        return False, "Wayland diagnose output missing Wayland marker"

    # Wayland may return non-zero if optional dependencies are missing.
    if session_type == "x11" and result.returncode != 0:
        return False, f"Unexpected x11 diagnose exit code: {result.returncode}"

    return True, f"{session_type}: diagnose path looks correct (exit {result.returncode})"


def main() -> int:
    print("=" * 60)
    print("WhisprBar V6 - Session Diagnose Check")
    print("=" * 60)

    if not PYTHON_BIN.exists():
        print(f"✗ Python not found: {PYTHON_BIN}")
        return 1

    ok = True
    for session_type in ("x11", "wayland"):
        status, msg = run_diagnose(session_type)
        prefix = "✓" if status else "✗"
        print(f"{prefix} {msg}")
        ok = ok and status

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
