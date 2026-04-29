"""Tests for Flow Mode active app context detection."""

import subprocess

import pytest

from whisprbar.flow.context import detect_app_context


@pytest.mark.unit
def test_detect_app_context_wayland_skips_x11_tools(monkeypatch):
    calls = []
    monkeypatch.setattr("whisprbar.flow.context.detect_session_type", lambda: "wayland")
    monkeypatch.setattr("whisprbar.flow.context.shutil.which", lambda name: calls.append(name))

    context = detect_app_context()

    assert context.session_type == "wayland"
    assert context.app_class == ""
    assert context.window_title == ""
    assert calls == []


@pytest.mark.unit
def test_detect_app_context_x11_missing_xdotool_returns_unknown(monkeypatch):
    monkeypatch.setattr("whisprbar.flow.context.detect_session_type", lambda: "x11")
    monkeypatch.setattr("whisprbar.flow.context.shutil.which", lambda name: None)

    context = detect_app_context()

    assert context.session_type == "x11"
    assert context.app_class == ""
    assert context.window_title == ""


@pytest.mark.unit
def test_detect_app_context_x11_reads_window_class_and_title(monkeypatch):
    monkeypatch.setattr("whisprbar.flow.context.detect_session_type", lambda: "x11")
    monkeypatch.setattr(
        "whisprbar.flow.context.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"xdotool", "xprop"} else None,
    )

    def fake_run(args, **kwargs):
        if args[:2] == ["/usr/bin/xdotool", "getactivewindow"]:
            return subprocess.CompletedProcess(args, 0, "12345\n", "")
        if args[:2] == ["/usr/bin/xdotool", "getwindowname"]:
            return subprocess.CompletedProcess(args, 0, "Inbox - Mozilla Thunderbird\n", "")
        if args[:3] == ["/usr/bin/xprop", "-id", "12345"]:
            return subprocess.CompletedProcess(args, 0, 'WM_CLASS(STRING) = "Mail", "thunderbird"\n', "")
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr("whisprbar.flow.context.subprocess.run", fake_run)

    context = detect_app_context()

    assert context.session_type == "x11"
    assert context.app_class == "thunderbird"
    assert context.app_name == "Mail"
    assert context.window_title == "Inbox - Mozilla Thunderbird"


@pytest.mark.unit
def test_detect_app_context_timeout_returns_unknown(monkeypatch):
    monkeypatch.setattr("whisprbar.flow.context.detect_session_type", lambda: "x11")
    monkeypatch.setattr("whisprbar.flow.context.shutil.which", lambda name: "/usr/bin/xdotool")

    def timeout_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 0.2)

    monkeypatch.setattr("whisprbar.flow.context.subprocess.run", timeout_run)

    context = detect_app_context()

    assert context.session_type == "x11"
    assert context.app_class == ""
    assert context.window_title == ""
