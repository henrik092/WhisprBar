"""Unit tests for whisprbar.audio module."""

import queue
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from whisprbar import audio


@pytest.mark.unit
def test_list_input_devices():
    """Test listing audio input devices."""
    devices = audio.list_input_devices()

    assert isinstance(devices, list)
    # Should have at least one device on most systems
    # If no devices, list should be empty (not None)
    for device in devices:
        assert "index" in device
        assert "name" in device
        assert isinstance(device["index"], int)
        assert isinstance(device["name"], str)


@pytest.mark.unit
def test_find_device_index_by_name_exact_match():
    """Test finding device by exact name match."""
    # Mock the list_input_devices function
    mock_devices = [
        {"index": 0, "name": "Default"},
        {"index": 1, "name": "USB Microphone"},
        {"index": 2, "name": "Built-in Audio"},
    ]

    with patch.object(audio, "list_input_devices", return_value=mock_devices):
        # Exact match (case-insensitive)
        assert audio.find_device_index_by_name("USB Microphone") == 1
        assert audio.find_device_index_by_name("usb microphone") == 1


@pytest.mark.unit
def test_find_device_index_by_name_substring_match():
    """Test finding device by substring match."""
    mock_devices = [
        {"index": 0, "name": "Default"},
        {"index": 1, "name": "USB Microphone Pro XLR"},
        {"index": 2, "name": "Built-in Audio"},
    ]

    with patch.object(audio, "list_input_devices", return_value=mock_devices):
        # Substring match
        assert audio.find_device_index_by_name("USB") == 1
        assert audio.find_device_index_by_name("Microphone") == 1


@pytest.mark.unit
def test_find_device_index_by_name_none():
    """Test finding device with None name returns None."""
    assert audio.find_device_index_by_name(None) is None


@pytest.mark.unit
def test_find_device_index_by_name_not_found():
    """Test finding nonexistent device returns None."""
    mock_devices = [
        {"index": 0, "name": "Default"},
        {"index": 1, "name": "USB Microphone"},
    ]

    with patch.object(audio, "list_input_devices", return_value=mock_devices):
        assert audio.find_device_index_by_name("Nonexistent Device") is None


@pytest.mark.unit
def test_apply_noise_reduction_disabled(sample_audio, mock_config):
    """Test noise reduction when disabled in config."""
    from whisprbar import config

    mock_config["noise_reduction_enabled"] = False
    config.cfg.clear()
    config.cfg.update(mock_config)

    result = audio.apply_noise_reduction(sample_audio)

    # Should return original audio unchanged
    np.testing.assert_array_equal(result, sample_audio)


@pytest.mark.unit
@pytest.mark.skipif(not audio.NOISEREDUCE_AVAILABLE, reason="noisereduce not available")
def test_apply_noise_reduction_enabled(sample_audio, mock_config):
    """Test noise reduction when enabled."""
    from whisprbar import config

    mock_config["noise_reduction_enabled"] = True
    mock_config["noise_reduction_strength"] = 0.5
    config.cfg.clear()
    config.cfg.update(mock_config)

    result = audio.apply_noise_reduction(sample_audio)

    # Result should be same shape
    assert result.shape == sample_audio.shape
    assert result.dtype == np.float32


@pytest.mark.unit
def test_apply_vad_disabled(sample_audio, mock_config):
    """Test VAD when disabled in config."""
    from whisprbar import config

    mock_config["use_vad"] = False
    config.cfg.clear()
    config.cfg.update(mock_config)

    result = audio.apply_vad(sample_audio)

    # Should return flattened mono audio
    assert result.ndim == 1
    assert len(result) == len(sample_audio)


@pytest.mark.unit
@pytest.mark.skipif(not audio.VAD_AVAILABLE, reason="webrtcvad not available")
def test_apply_vad_enabled_with_speech(sample_audio, mock_config):
    """Test VAD with audio containing speech (simulated with tone)."""
    from whisprbar import config

    mock_config["use_vad"] = True
    mock_config["vad_energy_ratio"] = 0.05
    mock_config["vad_bridge_ms"] = 300
    mock_config["vad_min_energy_frames"] = 2
    config.cfg.clear()
    config.cfg.update(mock_config)

    result = audio.apply_vad(sample_audio)

    # Should retain some audio (our sample has a tone)
    assert len(result) > 0
    assert result.dtype == np.float32


@pytest.mark.unit
@pytest.mark.skipif(not audio.VAD_AVAILABLE, reason="webrtcvad not available")
def test_apply_vad_with_silence(sample_audio_silent, mock_config):
    """Test VAD with silent audio."""
    from whisprbar import config

    mock_config["use_vad"] = True
    mock_config["vad_energy_ratio"] = 0.05
    config.cfg.clear()
    config.cfg.update(mock_config)

    result = audio.apply_vad(sample_audio_silent)

    # With silent audio, VAD should return original (safety mechanism)
    assert len(result) > 0


@pytest.mark.unit
def test_split_audio_into_chunks(sample_audio_long, mock_config):
    """Test splitting long audio into chunks."""
    from whisprbar import config

    mock_config["chunk_duration_seconds"] = 30.0
    mock_config["chunk_overlap_seconds"] = 2.0
    config.cfg.clear()
    config.cfg.update(mock_config)

    chunks = audio.split_audio_into_chunks(sample_audio_long)

    # Should create multiple chunks for 90s audio with 30s chunks
    assert len(chunks) > 1

    # Each chunk should have metadata
    for chunk_audio, start, end in chunks:
        assert isinstance(chunk_audio, np.ndarray)
        assert isinstance(start, int)
        assert isinstance(end, int)
        assert start < end
        assert len(chunk_audio) == end - start


@pytest.mark.unit
def test_split_audio_into_chunks_short_audio(sample_audio, mock_config):
    """Test that short audio doesn't get chunked unnecessarily."""
    from whisprbar import config

    mock_config["chunk_duration_seconds"] = 30.0
    config.cfg.clear()
    config.cfg.update(mock_config)

    chunks = audio.split_audio_into_chunks(sample_audio)

    # 1-second audio should produce 1 chunk
    assert len(chunks) == 1


@pytest.mark.unit
def test_recording_state_initial():
    """Test initial recording state."""
    assert "recording" in audio.recording_state
    assert "stream" in audio.recording_state
    assert "device_idx" in audio.recording_state
    assert "audio_data" in audio.recording_state

    # Initially not recording
    assert audio.recording_state["recording"] is False


@pytest.mark.unit
def test_get_recording_state():
    """Test get_recording_state returns a copy of state."""
    state = audio.get_recording_state()

    assert isinstance(state, dict)
    assert "recording" in state
    assert "stream" in state

    # Should be a copy, not the same object
    assert state is not audio.recording_state


@pytest.mark.unit
def test_set_recording_callbacks():
    """Test setting recording callbacks."""
    on_start_called = {"value": False}
    on_stop_called = {"value": False}

    def on_start():
        on_start_called["value"] = True

    def on_stop():
        on_stop_called["value"] = True

    audio.set_recording_callbacks(on_start=on_start, on_stop=on_stop)

    # Callbacks should be stored
    assert audio._recording_callbacks["on_start"] is on_start
    assert audio._recording_callbacks["on_stop"] is on_stop
