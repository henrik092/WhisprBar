"""Active application context detection for Flow Mode."""

import re
import shutil
import subprocess
from typing import Optional

from whisprbar.flow.models import AppContext
from whisprbar.utils import debug, detect_session_type

CONTEXT_DETECT_TIMEOUT = 0.35


def _run_context_command(args):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=CONTEXT_DETECT_TIMEOUT,
        check=False,
    )


def _parse_wm_class(output: str) -> tuple[str, str]:
    matches = re.findall(r'"([^"]*)"', output or "")
    if not matches:
        return "", ""
    app_name = matches[0]
    app_class = matches[-1]
    return app_name, app_class


def detect_app_context(session_type: Optional[str] = None) -> AppContext:
    """Detect active app/window context for profile resolution.

    Wayland and unknown sessions intentionally return a safe unknown context
    because arbitrary active-window inspection is not reliably available there.
    """
    session = session_type or detect_session_type()
    if session != "x11":
        return AppContext(session_type=session)

    xdotool = shutil.which("xdotool")
    if not xdotool:
        return AppContext(session_type=session)

    try:
        active = _run_context_command([xdotool, "getactivewindow"])
        if active.returncode != 0:
            return AppContext(session_type=session)
        win_id = active.stdout.strip().splitlines()[-1].strip()
        if not win_id:
            return AppContext(session_type=session)

        title_proc = _run_context_command([xdotool, "getwindowname", win_id])
        title = title_proc.stdout.strip() if title_proc.returncode == 0 else ""

        app_name = ""
        app_class = ""
        xprop = shutil.which("xprop")
        if xprop:
            class_proc = _run_context_command([xprop, "-id", win_id, "WM_CLASS"])
            if class_proc.returncode == 0:
                app_name, app_class = _parse_wm_class(class_proc.stdout)

        return AppContext(
            session_type=session,
            app_class=app_class,
            app_name=app_name,
            window_title=title,
        )
    except (IndexError, OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        debug(f"Flow context detection failed: {exc}")
        return AppContext(session_type=session)
