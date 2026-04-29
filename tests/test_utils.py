"""Unit tests for whisprbar.utils module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from whisprbar import utils


class _ImmediateThread:
    """Thread stub that runs the target immediately during tests."""

    def __init__(self, target=None, args=(), kwargs=None, **_extra):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


@pytest.mark.unit
def test_command_exists_with_existing_command():
    """Test command_exists returns True for existing commands."""
    # ls should exist on all Linux systems
    assert utils.command_exists("ls") is True


@pytest.mark.unit
def test_command_exists_with_nonexistent_command():
    """Test command_exists returns False for nonexistent commands."""
    assert utils.command_exists("this_command_definitely_does_not_exist_12345") is False


@pytest.mark.unit
def test_detect_session_type_x11(monkeypatch):
    """Test session type detection for X11."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert utils.detect_session_type() == "x11"

    monkeypatch.setenv("XDG_SESSION_TYPE", "xorg")
    assert utils.detect_session_type() == "x11"


@pytest.mark.unit
def test_detect_session_type_wayland(monkeypatch):
    """Test session type detection for Wayland."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert utils.detect_session_type() == "wayland"


@pytest.mark.unit
def test_detect_session_type_fallback(monkeypatch):
    """Test session type detection with fallback methods."""
    # Clear XDG_SESSION_TYPE
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)

    # Test Wayland fallback
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert utils.detect_session_type() == "wayland"

    # Test X11 fallback
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert utils.detect_session_type() == "x11"

    # Test unknown
    monkeypatch.delenv("DISPLAY", raising=False)
    assert utils.detect_session_type() == "unknown"


@pytest.mark.unit
def test_build_icon_creates_valid_image():
    """Test that build_icon creates a valid PIL Image."""
    icon = utils.build_icon(size=64)

    assert isinstance(icon, Image.Image)
    assert icon.size == (64, 64)
    assert icon.mode == "RGBA"


@pytest.mark.unit
def test_build_icon_custom_colors():
    """Test build_icon with custom colors."""
    accent = (255, 0, 0, 255)  # Red
    body = (0, 255, 0, 255)  # Green
    bg = (0, 0, 255, 255)  # Blue

    icon = utils.build_icon(
        size=64,
        accent_color=accent,
        body_color=body,
        background_color=bg,
    )

    assert isinstance(icon, Image.Image)
    # Check that non-transparent pixels exist
    pixels = icon.getdata()
    non_transparent = [p for p in pixels if p[3] > 0]
    assert len(non_transparent) > 0


@pytest.mark.unit
def test_build_notification_icon():
    """Test build_notification_icon creates a valid 64x64 icon."""
    icon = utils.build_notification_icon()

    assert isinstance(icon, Image.Image)
    assert icon.size == (64, 64)
    assert icon.mode == "RGBA"


@pytest.mark.unit
def test_write_history_creates_jsonl(monkeypatch_home, tmp_path, monkeypatch):
    """Test that write_history appends to history file."""
    from whisprbar import config

    hist_file = tmp_path / ".local" / "share" / "whisprbar" / "history.jsonl"
    data_dir = hist_file.parent

    monkeypatch.setattr(config, "HIST_FILE", hist_file)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(utils, "HIST_FILE", hist_file)
    monkeypatch.setattr(utils, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "cfg", {"language": "en"})

    # Write first entry
    utils.write_history("Test transcript 1", 2.5, 3)

    assert hist_file.exists()

    # Write second entry
    utils.write_history("Test transcript 2", 5.0, 5)

    # Verify both entries exist
    lines = hist_file.read_text().strip().split("\n")
    assert len(lines) == 2

    # Parse and verify JSON
    entry1 = json.loads(lines[0])
    assert entry1["text"] == "Test transcript 1"
    assert entry1["duration_seconds"] == 2.5
    assert entry1["word_count"] == 3
    assert entry1["language"] == "en"

    entry2 = json.loads(lines[1])
    assert entry2["text"] == "Test transcript 2"
    assert entry2["duration_seconds"] == 5.0
    assert entry2["word_count"] == 5


@pytest.mark.unit
def test_write_history_preserves_metadata(tmp_path, monkeypatch):
    """Flow metadata is stored with history entries."""
    from whisprbar import config

    hist_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(utils, "HIST_FILE", hist_file)
    monkeypatch.setattr(utils, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "cfg", {"language": "en", "flow_history_storage": "normal"})

    utils.write_history(
        "Final text",
        1.25,
        2,
        metadata={"raw_text": "raw text", "profile_id": "email"},
    )

    entry = json.loads(hist_file.read_text(encoding="utf-8").strip())
    assert entry["text"] == "Final text"
    assert entry["metadata"]["raw_text"] == "raw text"
    assert entry["metadata"]["profile_id"] == "email"


@pytest.mark.unit
def test_write_history_respects_never_store(tmp_path, monkeypatch):
    """Flow privacy mode can disable local history writes."""
    from whisprbar import config

    hist_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(utils, "HIST_FILE", hist_file)
    monkeypatch.setattr(utils, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "cfg", {"language": "en", "flow_history_storage": "never"})

    utils.write_history("Private", 1.0, 1)

    assert not hist_file.exists()


@pytest.mark.unit
def test_is_newer_version_basic():
    """Test version comparison logic."""
    assert utils.is_newer_version("1.0.1", "1.0.0") is True
    assert utils.is_newer_version("1.1.0", "1.0.9") is True
    assert utils.is_newer_version("2.0.0", "1.9.9") is True

    assert utils.is_newer_version("1.0.0", "1.0.1") is False
    assert utils.is_newer_version("1.0.0", "1.0.0") is False
    assert utils.is_newer_version("0.9.9", "1.0.0") is False


@pytest.mark.unit
def test_is_newer_version_invalid_inputs():
    """Test version comparison with invalid inputs."""
    assert utils.is_newer_version("invalid", "1.0.0") is False
    assert utils.is_newer_version("1.0.0", "invalid") is False
    assert utils.is_newer_version("", "") is False


@pytest.mark.unit
def test_collect_diagnostics_basic(monkeypatch):
    """Test basic diagnostic collection."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    # Mock command_exists to simulate xdotool availability
    def mock_command_exists(cmd):
        return cmd == "xdotool" or cmd == "notify-send"

    monkeypatch.setattr(utils, "command_exists", mock_command_exists)

    # Mock env values
    from whisprbar import config
    monkeypatch.setattr(config, "load_env_file_values", lambda: {"OPENAI_API_KEY": "sk-test-key"})

    results = utils.collect_diagnostics()

    assert len(results) > 0

    # Find session diagnostic
    session_diag = next((r for r in results if r.key == "session"), None)
    assert session_diag is not None
    assert session_diag.status == utils.STATUS_OK
    assert "X11" in session_diag.detail

    # Find auto-paste diagnostic
    paste_diag = next((r for r in results if r.key == "auto_paste"), None)
    assert paste_diag is not None
    assert paste_diag.status == utils.STATUS_OK

    # Find API key diagnostic
    api_diag = next((r for r in results if r.key == "api_key"), None)
    assert api_diag is not None
    assert api_diag.status == utils.STATUS_OK


@pytest.mark.unit
def test_collect_diagnostics_wayland_warning(monkeypatch):
    """Test diagnostics show warning for Wayland session."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")

    # Mock wl-clipboard availability
    def mock_command_exists(cmd):
        return cmd == "wl-clipboard" or cmd == "notify-send"

    monkeypatch.setattr(utils, "command_exists", mock_command_exists)

    results = utils.collect_diagnostics()

    # Find session diagnostic
    session_diag = next((r for r in results if r.key == "session"), None)
    assert session_diag is not None
    assert session_diag.status == utils.STATUS_WARN
    assert "Wayland" in session_diag.detail


@pytest.mark.unit
def test_play_audio_feedback_handles_invalid_volume(monkeypatch):
    """Invalid audio feedback volume should fall back without raising."""
    utils._audio_feedback_cache.clear()
    monkeypatch.setitem(utils.cfg, "audio_feedback_enabled", True)
    monkeypatch.setitem(utils.cfg, "audio_feedback_volume", "invalid")
    monkeypatch.setattr(utils, "command_exists", lambda _cmd: False)

    utils.play_audio_feedback("start")


@pytest.mark.unit
def test_play_audio_feedback_prefers_canberra_backend(monkeypatch):
    """canberra-gtk-play should be preferred over file-based backends."""
    proc = MagicMock()
    proc.communicate.return_value = (b"", b"")
    proc.returncode = 0

    utils._audio_feedback_cache.clear()
    monkeypatch.setitem(utils.cfg, "audio_feedback_enabled", True)
    monkeypatch.setitem(utils.cfg, "audio_feedback_volume", 0.3)
    monkeypatch.setattr(utils.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(utils, "command_exists", lambda cmd: cmd in {"canberra-gtk-play", "paplay", "aplay"})
    monkeypatch.setattr(utils.subprocess, "Popen", MagicMock(return_value=proc))

    utils.play_audio_feedback("start")

    utils.subprocess.Popen.assert_called_once()
    command = utils.subprocess.Popen.call_args.args[0]
    assert command[0] == "canberra-gtk-play"
    assert "--id" in command
    assert "button-pressed" in command


@pytest.mark.unit
def test_play_audio_feedback_aplay_uses_wav_candidate(monkeypatch):
    """aplay fallback must resolve WAV assets instead of OGG/OGA files."""
    proc = MagicMock()
    proc.communicate.return_value = (b"", b"")
    proc.returncode = 0

    utils._audio_feedback_cache.clear()
    monkeypatch.setitem(utils.cfg, "audio_feedback_enabled", True)
    monkeypatch.setitem(utils.cfg, "audio_feedback_volume", 0.3)
    monkeypatch.setattr(utils.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(utils, "command_exists", lambda cmd: cmd == "aplay")
    monkeypatch.setattr(utils.os.path, "exists", lambda path: path == "/usr/share/sounds/linuxmint-login.wav")
    monkeypatch.setattr(utils.subprocess, "Popen", MagicMock(return_value=proc))

    utils.play_audio_feedback("done")

    utils.subprocess.Popen.assert_called_once_with(
        ["aplay", "-q", "/usr/share/sounds/linuxmint-login.wav"],
        stdout=utils.subprocess.DEVNULL,
        stderr=utils.subprocess.PIPE,
    )


@pytest.mark.unit
def test_play_audio_feedback_falls_back_from_canberra_to_paplay(monkeypatch):
    """If canberra fails at runtime, playback should continue with paplay."""
    proc_fail = MagicMock()
    proc_fail.communicate.return_value = (b"", b"theme missing")
    proc_fail.returncode = 1

    proc_ok = MagicMock()
    proc_ok.communicate.return_value = (b"", b"")
    proc_ok.returncode = 0

    utils._audio_feedback_cache.clear()
    monkeypatch.setitem(utils.cfg, "audio_feedback_enabled", True)
    monkeypatch.setitem(utils.cfg, "audio_feedback_volume", 0.3)
    monkeypatch.setattr(utils.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(utils, "command_exists", lambda cmd: cmd in {"canberra-gtk-play", "paplay"})
    monkeypatch.setattr(
        utils.os.path,
        "exists",
        lambda path: path == "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga",
    )
    monkeypatch.setattr(utils.subprocess, "Popen", MagicMock(side_effect=[proc_fail, proc_ok]))

    utils.play_audio_feedback("done")

    assert utils.subprocess.Popen.call_count == 2
    first_command = utils.subprocess.Popen.call_args_list[0].args[0]
    second_command = utils.subprocess.Popen.call_args_list[1].args[0]
    assert first_command[0] == "canberra-gtk-play"
    assert second_command[0] == "paplay"


@pytest.mark.unit
def test_store_icon_creates_file(monkeypatch_home, tmp_path, monkeypatch):
    """Test that store_icon saves icon to disk."""
    from whisprbar import config

    data_dir = tmp_path / ".local" / "share" / "whisprbar"
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(utils, "DATA_DIR", data_dir)

    icon = utils.build_icon(size=32)
    path = utils.store_icon("test_icon", icon)

    assert path.exists()
    assert path.name == "test_icon.png"
    assert path.suffix == ".png"

    # Verify it's a valid image
    loaded = Image.open(path)
    assert loaded.size == (32, 32)
