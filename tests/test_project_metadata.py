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


def test_pyproject_python_floor_matches_syntax_usage():
    """Package metadata should not advertise unsupported Python versions."""
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    classifiers = set(metadata["project"]["classifiers"])

    assert metadata["project"]["requires-python"] == ">=3.10"
    assert "Programming Language :: Python :: 3.8" not in classifiers
    assert "Programming Language :: Python :: 3.9" not in classifiers
