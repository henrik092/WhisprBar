"""Tests for project packaging metadata."""

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib
from pathlib import Path

from whisprbar import __version__


def test_pyproject_version_matches_package_version():
    """Package metadata should not drift from the runtime version."""
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == __version__
