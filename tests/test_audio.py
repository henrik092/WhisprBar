"""Unit tests for whisprbar.audio module."""

import queue
import threading
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

    with patch("whisprbar.audio.recorder.list_input_devices", return_value=mock_devices):
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

    with patch("whisprbar.audio.recorder.list_input_devices", return_value=mock_devices):
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

    with patch("whisprbar.audio.recorder.list_input_devices", return_value=mock_devices):
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


@pytest.mark.unit
def test_recording_callback_forwards_audio_chunks_to_streaming_callback(monkeypatch):
    """Captured frames should be available to a live transcription session."""
    from whisprbar.audio import recorder

    chunks = []
    frame = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)

    monkeypatch.setattr(recorder, "AUDIO_QUEUE", queue.Queue())
    monkeypatch.setattr(recorder.time, "monotonic", lambda: 123.456)
    monkeypatch.setattr(
        recorder,
        "_recording_callbacks",
        {
            "on_start": None,
            "on_stop": None,
            "on_audio_level": None,
            "on_audio_chunk": chunks.append,
        },
    )
    with recorder._recording_state_lock:
        recorder.recording_state["first_audio_at_monotonic"] = None

    recorder.recording_callback(frame, len(frame), None, None)

    assert len(chunks) == 1
    np.testing.assert_array_equal(chunks[0], frame)
    assert chunks[0] is not frame
    assert recorder.recording_state["first_audio_at_monotonic"] == 123.456


@pytest.mark.unit
def test_indicator_level_mapping_makes_normal_speech_visible():
    """Typical speech RMS should drive the recording indicator clearly."""
    from whisprbar.audio.recorder import _audio_rms_to_indicator_level

    assert _audio_rms_to_indicator_level(0.0) == 0.0
    assert _audio_rms_to_indicator_level(0.0015) < 0.08
    assert _audio_rms_to_indicator_level(0.015) >= 0.35
    assert _audio_rms_to_indicator_level(0.05) >= 0.70
    assert _audio_rms_to_indicator_level(0.40) == 1.0


@pytest.mark.unit
def test_start_recording_ignores_concurrent_start_while_stream_initializes(monkeypatch):
    """A second start request during stream setup must not open another stream."""
    from whisprbar.audio import recorder

    created_streams = 0
    first_stream_entered = threading.Event()
    release_first_stream = threading.Event()

    class FakeStream:
        def __init__(self, **_kwargs):
            nonlocal created_streams
            created_streams += 1
            if created_streams == 1:
                first_stream_entered.set()
                release_first_stream.wait(timeout=2.0)

        def start(self):
            return None

        def stop(self):
            return None

        def close(self):
            return None

    class FakeSoundDevice:
        InputStream = FakeStream

    with recorder._recording_state_lock:
        recorder.recording_state.update(
            {
                "recording": False,
                "stream": None,
                "device_idx": None,
                "audio_data": None,
                "generation": 0,
            }
        )
        recorder.recording_state.pop("starting", None)

    monkeypatch.setitem(recorder.cfg, "flow_mode_enabled", False)
    monkeypatch.setitem(recorder.cfg, "vad_auto_stop_enabled", False)
    monkeypatch.setattr(recorder, "_get_sounddevice", lambda: FakeSoundDevice())
    monkeypatch.setattr(recorder, "update_device_index", lambda: None)
    monkeypatch.setattr(recorder, "_recording_callbacks", {"on_start": None, "on_stop": None, "on_audio_level": None})

    first_start = threading.Thread(target=recorder.start_recording)
    first_start.start()
    assert first_stream_entered.wait(timeout=1.0)

    recorder.start_recording()

    release_first_stream.set()
    first_start.join(timeout=2.0)

    try:
        assert created_streams == 1
    finally:
        recorder.stop_recording()


@pytest.mark.unit
def test_start_recording_prepares_live_session_before_stream_callbacks(monkeypatch):
    """Live streaming setup must run before sounddevice can emit frames."""
    from whisprbar.audio import recorder

    order = []
    monotonic_values = [100.0, 100.005]
    monotonic_current = [100.005]

    def fake_monotonic():
        if monotonic_values:
            monotonic_current[0] = monotonic_values.pop(0)
        else:
            monotonic_current[0] += 0.05
        return monotonic_current[0]

    class FakeStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]

        def start(self):
            order.append("stream_start")
            self.callback(np.ones((2, 1), dtype=np.float32), 2, None, None)

        def stop(self):
            return None

        def close(self):
            return None

    class FakeSoundDevice:
        InputStream = FakeStream

    with recorder._recording_state_lock:
        recorder.recording_state.update(
            {
                "recording": False,
                "stream": None,
                "device_idx": None,
                "audio_data": None,
                "generation": 0,
                "started_at_monotonic": None,
                "first_audio_at_monotonic": None,
                "stopped_at_monotonic": None,
            }
        )
        recorder.recording_state.pop("starting", None)

    monkeypatch.setattr(recorder.time, "monotonic", fake_monotonic)
    monkeypatch.setitem(recorder.cfg, "flow_mode_enabled", False)
    monkeypatch.setitem(recorder.cfg, "vad_auto_stop_enabled", False)
    monkeypatch.setattr(recorder, "_get_sounddevice", lambda: FakeSoundDevice())
    monkeypatch.setattr(recorder, "update_device_index", lambda: None)
    monkeypatch.setattr(recorder, "_start_max_recording_monitor", lambda _generation: None)
    monkeypatch.setattr(
        recorder,
        "_recording_callbacks",
        {
            "on_before_start": lambda: order.append("before_start"),
            "on_start": lambda: order.append("on_start"),
            "on_stop": None,
            "on_audio_level": None,
            "on_audio_chunk": lambda _chunk: order.append("audio_chunk"),
        },
    )

    try:
        recorder.start_recording()

        assert order == ["before_start", "stream_start", "audio_chunk", "on_start"]
        assert recorder.recording_state["started_at_monotonic"] == 100.0
        assert recorder.recording_state["first_audio_at_monotonic"] == 100.005
    finally:
        recorder.stop_recording()


@pytest.mark.unit
def test_max_recording_monitor_stops_active_matching_generation(monkeypatch):
    """Flow max-duration monitor stops the active recording for the same generation."""
    from whisprbar.audio import recorder

    called = []
    monkeypatch.setattr(recorder, "stop_recording", lambda: called.append(True))

    with recorder._recording_state_lock:
        recorder.recording_state["recording"] = True
        recorder.recording_state["generation"] = 42

    recorder._max_recording_monitor(42, 0)

    assert called == [True]


@pytest.mark.unit
def test_max_recording_monitor_ignores_stale_generation(monkeypatch):
    """A stale max-duration monitor must not stop a newer recording."""
    from whisprbar.audio import recorder

    called = []
    monkeypatch.setattr(recorder, "stop_recording", lambda: called.append(True))

    with recorder._recording_state_lock:
        recorder.recording_state["recording"] = True
        recorder.recording_state["generation"] = 43

    recorder._max_recording_monitor(42, 0)

    assert called == []
