"""Tests for command-line entry points."""

import runpy
import sys
from pathlib import Path

import pytest

from whisprbar import __version__


def test_package_module_version_exits_without_starting_app(monkeypatch, capsys):
    """`python -m whisprbar --version` should behave like the legacy wrapper."""
    import whisprbar.main as main_module

    def fail_if_app_starts():
        raise AssertionError("package module entry point started the tray app")

    monkeypatch.setattr(sys, "argv", ["python -m whisprbar", "--version"])
    monkeypatch.setattr(main_module, "main", fail_if_app_starts)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("whisprbar.__main__", run_name="__main__")

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"whisprbar {__version__}"


def test_console_script_uses_cli_entry_point():
    """Installed console scripts should parse CLI flags before starting the tray app."""
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        import tomli as tomllib

    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["scripts"]["whisprbar"] == "whisprbar.main:cli_main"


def test_parse_args_accepts_dictionary_learning_flags():
    """Dictionary learning should be runnable from CLI without starting the tray app."""
    import whisprbar.main as main_module

    args = main_module.parse_args([
        "--learn-dictionary",
        "--apply-safe-dictionary-candidates",
        "--learning-limit",
        "25",
        "--learning-min-count",
        "3",
    ])

    assert args.learn_dictionary is True
    assert args.apply_safe_dictionary_candidates is True
    assert args.learning_limit == 25
    assert args.learning_min_count == 3
