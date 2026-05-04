"""Unit tests for whisprbar.paste module."""

from unittest.mock import MagicMock, patch

import pytest

from whisprbar import paste
from whisprbar.flow.models import PastePolicy


@pytest.mark.unit
def test_is_wayland_session_true(monkeypatch):
    """Test is_wayland_session returns True for Wayland."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert paste.is_wayland_session() is True


@pytest.mark.unit
def test_is_wayland_session_false(monkeypatch):
    """Test is_wayland_session returns False for X11."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert paste.is_wayland_session() is False


@pytest.mark.unit
def test_get_paste_delay_seconds_default(mock_config):
    """Test get_paste_delay_seconds with default value."""
    from whisprbar import config

    mock_config["paste_delay_ms"] = 250
    paste.cfg = mock_config

    delay = paste.get_paste_delay_seconds()
    assert delay == 0.25


@pytest.mark.unit
def test_get_paste_delay_seconds_clamped(mock_config):
    """Test get_paste_delay_seconds clamps to max 5 seconds."""
    from whisprbar import config

    # Test clamping large value
    mock_config["paste_delay_ms"] = 10000
    paste.cfg = mock_config
    assert paste.get_paste_delay_seconds() == 5.0

    # Test clamping negative value
    mock_config["paste_delay_ms"] = -100
    paste.cfg = mock_config
    assert paste.get_paste_delay_seconds() == 0.0


@pytest.mark.unit
def test_get_paste_delay_seconds_invalid(mock_config):
    """Test get_paste_delay_seconds with invalid value."""
    from whisprbar import config

    mock_config["paste_delay_ms"] = "invalid"
    paste.cfg = mock_config

    delay = paste.get_paste_delay_seconds()
    assert delay == 0.0


@pytest.mark.unit
def test_detect_auto_paste_sequence_wayland(monkeypatch):
    """Test detect_auto_paste_sequence on Wayland returns clipboard."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")

    result = paste.detect_auto_paste_sequence()
    assert result == "clipboard"


@pytest.mark.unit
def test_detect_auto_paste_sequence_x11_no_xdotool(monkeypatch):
    """Test detect_auto_paste_sequence on X11 without xdotool."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    with patch("shutil.which", return_value=None):
        result = paste.detect_auto_paste_sequence()
        assert result == "ctrl_v"


@pytest.mark.unit
def test_detect_auto_paste_sequence_x11_with_xdotool(monkeypatch):
    """Test detect_auto_paste_sequence on X11 with xdotool available."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    # Mock xdotool commands
    def mock_run(args, **kwargs):
        result = MagicMock()
        result.returncode = 0

        if "getactivewindow" in args:
            result.stdout = "12345678\n"
        elif "getwindowname" in args:
            result.stdout = "Some Window\n"
        else:
            result.stdout = ""

        return result

    with patch("shutil.which", return_value="/usr/bin/xdotool"):
        with patch("whisprbar.paste._run_paste_command", side_effect=mock_run):
            result = paste.detect_auto_paste_sequence()
            # Should default to ctrl_v for non-terminal
            assert result in ["ctrl_v", "ctrl_shift_v"]


@pytest.mark.unit
def test_detect_auto_paste_sequence_terminal_detection(monkeypatch):
    """Test that terminal windows are detected for ctrl+shift+v."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    # Mock xdotool to return terminal window
    def mock_run(args, **kwargs):
        result = MagicMock()
        result.returncode = 0

        if "getactivewindow" in args:
            result.stdout = "12345678\n"
        elif "getwindowname" in args:
            result.stdout = "terminal - bash\n"
        elif "xprop" in args[0]:
            result.stdout = 'WM_CLASS(STRING) = "gnome-terminal"\n'
        else:
            result.stdout = ""

        return result

    with patch("shutil.which", return_value="/usr/bin/xdotool"):
        with patch("whisprbar.paste._run_paste_command", side_effect=mock_run):
            result = paste._detect_auto_paste_sequence_blocking("/usr/bin/xdotool")
            assert result == "ctrl_shift_v"


@pytest.mark.unit
@pytest.mark.skipif(not paste.PYNPUT_AVAILABLE, reason="pynput backend unavailable")
def test_simulate_typing():
    """Test simulate_typing calls controller.type()."""
    text = "Hello world"

    with patch.object(paste._controller, "type") as mock_type:
        paste.simulate_typing(text, delay_ms=0)
        assert mock_type.call_count == len(text)
        assert mock_type.call_args_list[0][0][0] == "H"


@pytest.mark.unit
@pytest.mark.skipif(not paste.PYNPUT_AVAILABLE, reason="pynput backend unavailable")
def test_simulate_typing_empty():
    """Test simulate_typing with empty text does nothing."""
    with patch.object(paste._controller, "type") as mock_type:
        paste.simulate_typing("")
        mock_type.assert_not_called()


@pytest.mark.unit
def test_perform_auto_paste_clipboard_only(monkeypatch, mock_config):
    """Test perform_auto_paste in clipboard-only mode."""
    from whisprbar import config

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    mock_config["paste_sequence"] = "auto"
    paste.cfg = mock_config

    with patch("whisprbar.paste.copy_to_clipboard", return_value=True):
        with patch("whisprbar.paste.notify") as mock_notify:
            result = paste.perform_auto_paste("Test text")

            # Should show notification on Wayland
            mock_notify.assert_called_once()
            assert "clipboard" in mock_notify.call_args[0][0].lower()
            assert result.status == "clipboard_only"
            assert result.sequence == "clipboard"


@pytest.mark.unit
@pytest.mark.skipif(not paste.PYNPUT_AVAILABLE, reason="pynput backend unavailable")
def test_perform_auto_paste_type_simulation(mock_config):
    """Test perform_auto_paste with type simulation."""
    from whisprbar import config

    mock_config["paste_sequence"] = "type"
    mock_config["paste_delay_ms"] = 0
    paste.cfg = mock_config

    with patch.object(paste._controller, "type") as mock_type:
        paste.perform_auto_paste("Hello")
        # perform_auto_paste() appends a trailing space by default
        assert mock_type.call_count == len("Hello ")


@pytest.mark.unit
def test_perform_auto_paste_ctrl_v_with_xdotool(monkeypatch, mock_config):
    """Test perform_auto_paste with Ctrl+V using xdotool."""
    from whisprbar import config

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    mock_config["paste_sequence"] = "ctrl_v"
    mock_config["paste_delay_ms"] = 0
    paste.cfg = mock_config

    mock_run = MagicMock()
    mock_run.returncode = 0

    with patch("whisprbar.paste.copy_to_clipboard", return_value=True):
        with patch("shutil.which", return_value="/usr/bin/xdotool"):
            with patch("subprocess.run", return_value=mock_run) as mock_subprocess:
                result = paste.perform_auto_paste("Test")

                # Should call xdotool
                mock_subprocess.assert_called_once()
                args = mock_subprocess.call_args[0][0]
                assert "xdotool" in args[0]
                assert "key" in args
                assert "ctrl+v" in args
                assert result.status == "inserted"
                assert result.sequence == "ctrl_v"


@pytest.mark.unit
def test_perform_auto_paste_policy_overrides_sequence_and_spacing(monkeypatch, mock_config):
    """PastePolicy can override one paste without mutating global cfg."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    mock_config["paste_sequence"] = "ctrl_v"
    mock_config["auto_paste_add_space"] = True
    mock_config["paste_delay_ms"] = 0
    paste.cfg = mock_config

    mock_run = MagicMock(returncode=0)
    policy = PastePolicy(sequence="ctrl_shift_v", add_space=False)

    with patch("whisprbar.paste.copy_to_clipboard", return_value=True) as mock_copy:
        with patch("shutil.which", return_value="/usr/bin/xdotool"):
            with patch("subprocess.run", return_value=mock_run) as mock_subprocess:
                paste.perform_auto_paste("Test", policy=policy)

    mock_copy.assert_called_once_with("Test", silent=False)
    args = mock_subprocess.call_args[0][0]
    assert "ctrl+Shift+v" in args
    assert paste.cfg["paste_sequence"] == "ctrl_v"


@pytest.mark.unit
def test_perform_auto_paste_policy_clipboard_only(monkeypatch, mock_config):
    """Clipboard-only policy skips key injection."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    mock_config["paste_sequence"] = "ctrl_v"
    paste.cfg = mock_config

    with patch("whisprbar.paste.copy_to_clipboard", return_value=True):
        with patch("subprocess.run") as mock_run:
            result = paste.perform_auto_paste("Test", policy=PastePolicy(clipboard_only=True))

    mock_run.assert_not_called()
    assert result.status == "clipboard_only"


@pytest.mark.unit
def test_perform_auto_paste_reports_failed_keyboard_injection(monkeypatch, mock_config):
    """A copied transcript with no injection backend should report clipboard fallback."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    mock_config["paste_sequence"] = "ctrl_v"
    mock_config["paste_delay_ms"] = 0
    paste.cfg = mock_config

    monkeypatch.setattr(paste, "_controller", None)
    monkeypatch.setattr(paste, "PYNPUT_AVAILABLE", False)

    with patch("whisprbar.paste.copy_to_clipboard", return_value=True):
        with patch("shutil.which", return_value=None):
            with patch("whisprbar.paste.notify") as mock_notify:
                result = paste.perform_auto_paste("Test")

    mock_notify.assert_called_once()
    assert result.status == "failed"
    assert result.sequence == "ctrl_v"


@pytest.mark.unit
def test_perform_auto_paste_policy_press_enter(monkeypatch, mock_config):
    """Press-enter policy sends Return after paste when enabled."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    mock_config["paste_sequence"] = "ctrl_v"
    mock_config["paste_delay_ms"] = 0
    mock_config["flow_press_enter_enabled"] = True
    paste.cfg = mock_config

    with patch("whisprbar.paste.copy_to_clipboard", return_value=True):
        with patch("shutil.which", return_value="/usr/bin/xdotool"):
            with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
                paste.perform_auto_paste(
                    "Test",
                    policy=PastePolicy(press_enter_after_paste=True),
                )

    calls = [call.args[0] for call in mock_run.call_args_list]
    assert ["/usr/bin/xdotool", "key", "ctrl+v"] in calls
    assert ["/usr/bin/xdotool", "key", "Return"] in calls


@pytest.mark.unit
@pytest.mark.skipif(not paste.PYNPUT_AVAILABLE, reason="pynput backend unavailable")
def test_perform_auto_paste_fallback_to_pynput(monkeypatch, mock_config):
    """Test perform_auto_paste falls back to pynput when xdotool unavailable."""
    from whisprbar import config

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    mock_config["paste_sequence"] = "ctrl_v"
    mock_config["paste_delay_ms"] = 0
    paste.cfg = mock_config

    # Mock xdotool as unavailable
    with patch("shutil.which", return_value=None):
        with patch.object(paste._controller, "pressed") as mock_pressed:
            with patch.object(paste, "press_key") as mock_press:
                paste.perform_auto_paste("Test")

                # Should use pynput Controller
                mock_pressed.assert_called()


@pytest.mark.unit
def test_get_paste_sequence_label():
    """Test get_paste_sequence_label returns correct labels."""
    assert paste.get_paste_sequence_label("auto") == "Auto Detect"
    assert paste.get_paste_sequence_label("ctrl_v") == "Ctrl+V"
    assert paste.get_paste_sequence_label("ctrl_shift_v") == "Ctrl+Shift+V"
    assert paste.get_paste_sequence_label("shift_insert") == "Shift+Insert"
    assert paste.get_paste_sequence_label("type") == "Type Simulation"
    assert paste.get_paste_sequence_label("clipboard") == "Clipboard Only"


@pytest.mark.unit
def test_paste_options_constant():
    """Test PASTE_OPTIONS constant has all expected options."""
    assert "auto" in paste.PASTE_OPTIONS
    assert "ctrl_v" in paste.PASTE_OPTIONS
    assert "ctrl_shift_v" in paste.PASTE_OPTIONS
    assert "shift_insert" in paste.PASTE_OPTIONS
    assert "type" in paste.PASTE_OPTIONS
    assert "clipboard" in paste.PASTE_OPTIONS
