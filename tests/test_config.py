"""Unit tests for whisprbar.config module."""

import json
from pathlib import Path

import pytest

from whisprbar import config


@pytest.mark.unit
def test_load_env_file_values_basic(mock_env_file, monkeypatch):
    """Test loading environment variables from .env file."""
    monkeypatch.setattr(config, "get_env_file_path", lambda: mock_env_file)

    values = config.load_env_file_values()

    assert "OPENAI_API_KEY" in values
    assert values["OPENAI_API_KEY"] == "sk-test-1234567890abcdef"
    assert values["WHISPRBAR_HOME"] == "/custom/home"
    assert "EMPTY_VALUE" in values
    assert values["EMPTY_VALUE"] == ""


@pytest.mark.unit
def test_load_env_file_values_nonexistent():
    """Test loading environment variables when file doesn't exist."""
    values = config.load_env_file_values()

    # Should return empty dict without error
    assert isinstance(values, dict)


@pytest.mark.unit
def test_load_config_with_defaults(monkeypatch_home, monkeypatch):
    """Test that load_config returns default values when no config file exists."""
    data_dir = monkeypatch_home / ".local" / "share" / "whisprbar"
    hist_file = data_dir / "history.jsonl"
    config_path = monkeypatch_home / ".config" / "whisprbar.json"
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "HIST_FILE", hist_file)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    config.load_config()

    # Check that essential defaults are present
    assert config.cfg["language"] == "de"
    assert config.cfg["hotkey"] == "F9"
    assert config.cfg["use_vad"] is True
    assert config.cfg["transcription_backend"] == "openai"


@pytest.mark.unit
def test_load_config_merges_with_defaults(mock_config_file, monkeypatch):
    """Test that load_config merges file config with defaults."""
    # Monkeypatch CONFIG_PATH to use our test file
    monkeypatch.setattr(config, "CONFIG_PATH", mock_config_file)

    config.load_config()

    # Check that custom values are loaded
    assert config.cfg["language"] == "en"  # From mock_config
    assert config.cfg["paste_delay_ms"] == 100  # From mock_config

    # Check that missing values still have defaults
    assert "check_updates" in config.cfg  # Should be filled from DEFAULT_CFG


@pytest.mark.unit
def test_save_config_creates_file(monkeypatch_home, tmp_path, monkeypatch):
    """Test that save_config creates a valid JSON file."""
    config_path = tmp_path / ".config" / "whisprbar.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    # Update config and save
    config.cfg["language"] = "fr"
    config.cfg["hotkey"] = "F10"
    config.save_config()

    # Verify file was created and contains correct data
    assert config_path.exists()

    with config_path.open("r") as f:
        saved_data = json.load(f)

    assert saved_data["language"] == "fr"
    assert saved_data["hotkey"] == "F10"


@pytest.mark.unit
def test_validate_config_clamps_paste_delay():
    """Test that validate_config clamps paste_delay_ms to valid range."""
    # Test clamping large value
    config.cfg["paste_delay_ms"] = 10000
    config.validate_config()
    assert config.cfg["paste_delay_ms"] == 5000

    # Test clamping negative value
    config.cfg["paste_delay_ms"] = -100
    config.validate_config()
    assert config.cfg["paste_delay_ms"] == 0

    # Test valid value unchanged
    config.cfg["paste_delay_ms"] = 250
    config.validate_config()
    assert config.cfg["paste_delay_ms"] == 250


@pytest.mark.unit
def test_validate_config_clamps_vad_energy_ratio():
    """Test that validate_config clamps vad_energy_ratio to valid range."""
    # Test clamping large value
    config.cfg["vad_energy_ratio"] = 0.5
    config.validate_config()
    assert config.cfg["vad_energy_ratio"] == 0.3

    # Test clamping small value
    config.cfg["vad_energy_ratio"] = 0.001
    config.validate_config()
    assert config.cfg["vad_energy_ratio"] == 0.002

    # Test valid value unchanged
    config.cfg["vad_energy_ratio"] = 0.05
    config.validate_config()
    assert config.cfg["vad_energy_ratio"] == 0.05


@pytest.mark.unit
def test_ensure_directories_creates_paths(monkeypatch_home, tmp_path, monkeypatch):
    """Test that ensure_directories creates necessary directories and files."""
    data_dir = tmp_path / ".local" / "share" / "whisprbar"
    hist_file = data_dir / "history.jsonl"
    config_dir = tmp_path / ".config"

    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "HIST_FILE", hist_file)
    monkeypatch.setattr(config, "CONFIG_PATH", config_dir / "whisprbar.json")

    config.ensure_directories()

    assert data_dir.exists()
    assert hist_file.exists()
    assert config_dir.exists()


@pytest.mark.unit
def test_get_env_file_path_respects_xdg(monkeypatch):
    """Test that get_env_file_path respects XDG_CONFIG_HOME."""
    xdg_config = "/custom/config"
    monkeypatch.setenv("XDG_CONFIG_HOME", xdg_config)

    env_path = config.get_env_file_path()

    assert str(env_path) == f"{xdg_config}/whisprbar.env"


@pytest.mark.unit
def test_get_env_file_path_default(monkeypatch):
    """Test that get_env_file_path uses default when XDG_CONFIG_HOME not set."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    env_path = config.get_env_file_path()

    # Should use ~/.config/whisprbar.env
    assert env_path.name == "whisprbar.env"
    assert ".config" in str(env_path)
