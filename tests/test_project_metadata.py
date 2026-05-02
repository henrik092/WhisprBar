"""Tests for project packaging metadata."""

import tomllib
from pathlib import Path

from whisprbar import __version__


def test_pyproject_version_matches_package_version():
    """Package metadata should not drift from the runtime version."""
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == __version__
