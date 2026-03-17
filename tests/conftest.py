"""Pytest configuration and shared fixtures for WhisprBar tests."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary configuration directory.

    Yields:
        Path to temporary config directory
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory.

    Yields:
        Path to temporary data directory
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def mock_config(temp_config_dir, temp_data_dir):
    """Create a mock configuration dictionary with temp paths.

    Returns:
        Dictionary with test configuration
    """
    return {
        "language": "en",
        "device_name": None,
        "hotkey": "F9",
        "notifications_enabled": False,
        "auto_paste_enabled": True,
        "paste_sequence": "auto",
        "paste_delay_ms": 100,
        "use_vad": True,
        "vad_energy_ratio": 0.05,
        "vad_bridge_ms": 300,
        "vad_min_energy_frames": 2,
        "vad_auto_stop_enabled": False,
        "vad_auto_stop_silence_seconds": 2.0,
        "chunking_enabled": True,
        "chunk_duration_seconds": 30.0,
        "chunk_overlap_seconds": 2.0,
        "chunking_threshold_seconds": 60.0,
        "postprocess_enabled": True,
        "postprocess_fix_spacing": True,
        "postprocess_fix_capitalization": True,
        "noise_reduction_enabled": False,
        "transcription_backend": "openai",
        "faster_whisper_model": "tiny",
        "faster_whisper_device": "cpu",
        "faster_whisper_compute_type": "int8",
    }


@pytest.fixture
def sample_audio():
    """Generate sample audio data for testing.

    Returns:
        numpy array of float32 audio samples (1 second at 16kHz)
    """
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0  # A4 note

    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = np.sin(2 * np.pi * frequency * t).astype(np.float32) * 0.3

    return audio


@pytest.fixture
def sample_audio_silent():
    """Generate silent audio data for testing.

    Returns:
        numpy array of float32 zeros (1 second at 16kHz)
    """
    sample_rate = 16000
    duration = 1.0
    return np.zeros(int(sample_rate * duration), dtype=np.float32)


@pytest.fixture
def sample_audio_long():
    """Generate longer sample audio for chunking tests.

    Returns:
        numpy array of float32 audio samples (90 seconds at 16kHz)
    """
    sample_rate = 16000
    duration = 90.0
    frequency = 440.0

    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = np.sin(2 * np.pi * frequency * t).astype(np.float32) * 0.3

    return audio


@pytest.fixture
def env_file_content():
    """Sample .env file content for testing.

    Returns:
        String with sample environment variables
    """
    return """# WhisprBar environment variables
OPENAI_API_KEY=sk-test-FAKE-KEY-FOR-TESTING-ONLY
WHISPRBAR_HOME=/custom/home
# Comment line
EMPTY_VALUE=
"""


@pytest.fixture
def mock_env_file(temp_config_dir, env_file_content):
    """Create a mock environment file.

    Args:
        temp_config_dir: Temporary config directory fixture
        env_file_content: Environment file content fixture

    Returns:
        Path to created .env file
    """
    env_path = temp_config_dir / "whisprbar.env"
    env_path.write_text(env_file_content)
    return env_path


@pytest.fixture
def mock_config_file(temp_config_dir, mock_config):
    """Create a mock configuration JSON file.

    Args:
        temp_config_dir: Temporary config directory fixture
        mock_config: Mock configuration fixture

    Returns:
        Path to created config file
    """
    config_path = temp_config_dir / "whisprbar.json"
    with config_path.open("w") as f:
        json.dump(mock_config, f, indent=2)
    return config_path


@pytest.fixture
def monkeypatch_home(monkeypatch, tmp_path):
    """Monkeypatch Path.home() to return a temporary directory.

    This prevents tests from modifying the actual user's home directory.

    Args:
        monkeypatch: Pytest monkeypatch fixture
        tmp_path: Pytest tmp_path fixture
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch):
    """Automatically isolate config module state for each test.

    This fixture runs automatically for all tests and ensures that
    the global config state is isolated.
    """
    # Store original config
    from whisprbar import config
    cfg_ref = config.cfg
    default_ref = config.DEFAULT_CFG
    original_cfg = copy.deepcopy(cfg_ref)
    original_default = copy.deepcopy(default_ref)

    yield

    # Restore original config
    cfg_ref.clear()
    cfg_ref.update(original_cfg)
    config.cfg = cfg_ref

    default_ref.clear()
    default_ref.update(original_default)
    config.DEFAULT_CFG = default_ref
