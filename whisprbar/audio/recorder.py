"""Audio recording for WhisprBar.

Handles audio stream management, recording start/stop, and device selection.
"""

import contextlib
import queue
import sys
import threading
import time
from typing import List, Optional

import numpy as np

from whisprbar.config import cfg
from whisprbar.utils import debug
from .processing import SAMPLE_RATE, CHANNELS, BLOCK_SIZE

# Global state for recording
AUDIO_QUEUE: Optional[queue.Queue] = None
audio_queue_lock = threading.Lock()
_recording_state_lock = threading.Lock()  # Protects recording_state from concurrent access
recording_state = {
    "recording": False,
    "stream": None,
    "device_idx": None,
    "audio_data": None,
}

# Callbacks for recording events
_recording_callbacks = {
    "on_start": None,
    "on_stop": None,
    "on_audio_level": None,
}

# Lazy-loaded sounddevice module (import can block/fail in headless CI)
_sd_module = None
_sd_import_error: Optional[str] = None
_sd_lock = threading.Lock()


def _get_sounddevice():
    """Lazily import sounddevice only when audio I/O is needed."""
    global _sd_module, _sd_import_error
    with _sd_lock:
        if _sd_import_error is not None:
            raise RuntimeError(_sd_import_error)
        if _sd_module is None:
            result = {"module": None, "error": None}

            def _import_worker() -> None:
                try:
                    import sounddevice as sd
                    result["module"] = sd
                except Exception as exc:
                    result["error"] = str(exc)

            worker = threading.Thread(target=_import_worker, daemon=True)
            worker.start()
            worker.join(timeout=2.0)

            if worker.is_alive():
                _sd_import_error = "sounddevice import timed out"
                raise RuntimeError(_sd_import_error)
            if result["error"]:
                _sd_import_error = result["error"]
                raise RuntimeError(_sd_import_error)

            _sd_module = result["module"]
    return _sd_module


def list_input_devices() -> List[dict]:
    """List all available audio input devices.

    Returns:
        List of dicts with 'index' and 'name' keys for each input device
    """
    devices = []
    try:
        sd = _get_sounddevice()
        query_result = sd.query_devices()
    except Exception as exc:
        debug(f"Failed to query audio devices: {exc}")
        return devices

    for idx, info in enumerate(query_result):
        if info.get("max_input_channels", 0) > 0:
            devices.append(
                {
                    "index": idx,
                    "name": info.get("name", f"Device {idx}"),
                }
            )
    return devices


def find_device_index_by_name(name: Optional[str]) -> Optional[int]:
    """Find audio device index by name.

    First tries exact match (case-insensitive), then substring match.

    Args:
        name: Device name to search for, or None for system default

    Returns:
        Device index or None if not found
    """
    if not name:
        return None

    # Try exact match first
    for device in list_input_devices():
        if device["name"].lower() == name.lower():
            return device["index"]

    # Try substring match
    for device in list_input_devices():
        if name.lower() in device["name"].lower():
            return device["index"]

    return None


def update_device_index() -> None:
    """Update device index from current config."""
    idx = find_device_index_by_name(cfg.get("device_name"))
    with _recording_state_lock:
        recording_state["device_idx"] = idx


def recording_callback(indata, frames, time_info, status):
    """Sounddevice callback for audio recording.

    Called by sounddevice in audio thread. Copies audio data to queue
    for main thread processing.

    Args:
        indata: Audio data from sounddevice
        frames: Number of frames
        time_info: Timing information
        status: Stream status flags
    """
    if status and status.input_overflow:
        print(f"[WARN] Audio overflow: {status}", file=sys.stderr)

    # Copy data once to avoid multiple copies
    data_copy = indata.copy()

    # Use non-blocking put to prevent callback thread blocking (defensive programming)
    # Queue is unbounded so this should never raise queue.Full, but we handle it anyway
    with audio_queue_lock:
        queue_obj = AUDIO_QUEUE
        if queue_obj is not None:
            try:
                queue_obj.put_nowait(data_copy)
            except queue.Full:
                # Should never happen with unbounded queue, but handle defensively
                print("[ERROR] Audio queue unexpectedly full, dropping frame", file=sys.stderr)

    # Feed audio level to recording indicator
    if _recording_callbacks.get("on_audio_level"):
        try:
            import numpy as np
            rms = float(np.sqrt(np.mean(data_copy.astype(np.float32) ** 2)))
            # Normalize: typical speech RMS ~0.01-0.1, scale to 0.0-1.0
            level = min(1.0, rms * 10.0)
            _recording_callbacks["on_audio_level"](level)
        except Exception:
            pass

    # Also feed to VAD monitor queue if it exists
    from .vad import vad_monitor_lock, VAD_MONITOR_QUEUE
    with vad_monitor_lock:
        vad_queue_obj = VAD_MONITOR_QUEUE
        if vad_queue_obj is not None:
            try:
                vad_queue_obj.put_nowait(data_copy)
            except queue.Full:
                # VAD queue full, skip this chunk (monitor is lagging)
                pass


def start_recording() -> None:
    """Start audio recording.

    Opens audio stream and begins capturing audio to queue.
    Optionally starts VAD auto-stop monitor if enabled.
    """
    global AUDIO_QUEUE

    if recording_state.get("recording"):
        return

    update_device_index()

    try:
        sd = _get_sounddevice()

        # Use unbounded queue to support recordings of any length
        # Memory usage is self-limiting: bounded by user behavior (hotkey release)
        # Queue is drained immediately after recording stops and then destroyed
        # Example: 5-minute recording = 5min x 60s x 16kHz x 4 bytes = 19.2 MB
        # This is acceptable for modern systems and prevents truncation of long recordings
        queue_obj: queue.Queue = queue.Queue()
        with audio_queue_lock:
            AUDIO_QUEUE = queue_obj

        # Create separate queue for VAD monitoring if auto-stop is enabled
        from .vad import VAD_AVAILABLE, VAD_MONITOR_QUEUE, vad_monitor_lock, vad_auto_stop_monitor
        import whisprbar.audio.vad as _vad_module

        if cfg.get("vad_auto_stop_enabled") and VAD_AVAILABLE:
            vad_queue_obj: queue.Queue = queue.Queue(maxsize=100)  # Limit size to prevent memory issues
            with vad_monitor_lock:
                _vad_module.VAD_MONITOR_QUEUE = vad_queue_obj

        with _recording_state_lock:
            device_idx = recording_state.get("device_idx")

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=BLOCK_SIZE,
            callback=recording_callback,
            dtype="float32",
            device=device_idx,
        )
        stream.start()
        with _recording_state_lock:
            recording_state["stream"] = stream
            recording_state["recording"] = True
            recording_state["audio_data"] = None

        debug("Recording started")

        # Call on_start callback if set
        if _recording_callbacks.get("on_start"):
            try:
                _recording_callbacks["on_start"]()
            except Exception as exc:
                debug(f"Recording start callback error: {exc}")

        # Start auto-stop monitor if enabled
        if cfg.get("vad_auto_stop_enabled") and VAD_AVAILABLE:
            threading.Thread(target=vad_auto_stop_monitor, daemon=True).start()

    except Exception as exc:
        with audio_queue_lock:
            AUDIO_QUEUE = None
        import whisprbar.audio.vad as _vad_module
        from .vad import vad_monitor_lock
        with vad_monitor_lock:
            _vad_module.VAD_MONITOR_QUEUE = None
        print(f"[ERROR] start_recording failed: {exc}", file=sys.stderr)
        raise


def stop_recording() -> Optional[np.ndarray]:
    """Stop audio recording and return captured audio.

    Stops the audio stream, collects all queued audio data, and
    concatenates it into a single numpy array.

    Returns:
        Audio data as float32 numpy array, or None if no audio captured
    """
    global AUDIO_QUEUE

    with _recording_state_lock:
        if not recording_state.get("recording"):
            return None
        recording_state["recording"] = False
        stream = recording_state.get("stream")

    with audio_queue_lock:
        queue_obj = AUDIO_QUEUE

    frames: List[np.ndarray] = []

    # Calculate single unified grace period for queue draining
    # This is the time we wait after stopping the stream for buffered audio to arrive
    grace_ms = max(100, min(2000, int(cfg.get("stop_tail_grace_ms", 500))))
    grace_seconds = grace_ms / 1000.0

    # Minimum drain timeout (configurable, default 100ms for fast response)
    min_drain_ms = max(100, min(500, int(cfg.get("min_drain_timeout_ms", 100))))
    min_drain_timeout = min_drain_ms / 1000.0
    drain_timeout_seconds = max(grace_seconds, min_drain_timeout)

    # Stop the stream first to prevent new data
    if stream:
        with contextlib.suppress(Exception):
            stream.stop()
            stream.close()
    with _recording_state_lock:
        recording_state["stream"] = None

    # Drain all remaining frames from queue with early-exit optimization
    # After the stream is stopped, buffered frames arrive briefly then stop.
    # Break early after consecutive empty polls instead of waiting full timeout.
    if queue_obj is not None:
        drain_deadline = time.monotonic() + drain_timeout_seconds
        consecutive_empty = 0
        # 3 consecutive empty polls (150ms) = no more data coming
        max_consecutive_empty = 3
        while time.monotonic() < drain_deadline:
            try:
                frame = queue_obj.get(timeout=0.05)
                frames.append(frame)
                consecutive_empty = 0  # Reset on successful read
            except queue.Empty:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    debug(f"Queue drain: early exit after {consecutive_empty} empty polls")
                    break

        # Final non-blocking drain to catch any stragglers
        while True:
            try:
                frame = queue_obj.get_nowait()
                frames.append(frame)
            except queue.Empty:
                break

        with audio_queue_lock:
            AUDIO_QUEUE = None

        # Clean up VAD monitor queue
        import whisprbar.audio.vad as _vad_module
        from .vad import vad_monitor_lock
        with vad_monitor_lock:
            _vad_module.VAD_MONITOR_QUEUE = None

    if not frames:
        debug("No audio captured")
        audio_data = None
    else:
        audio_data = np.concatenate(frames, axis=0)
        duration = audio_data.shape[0] / SAMPLE_RATE
        debug(f"Captured audio duration: {duration:.2f}s, samples: {audio_data.shape[0]}")

    # Store audio data in recording state for main.py to access
    with _recording_state_lock:
        recording_state["audio_data"] = audio_data

    # Call on_stop callback if set
    if _recording_callbacks.get("on_stop"):
        try:
            _recording_callbacks["on_stop"]()
        except Exception as exc:
            debug(f"Recording stop callback error: {exc}")

    return audio_data


# =============================================================================
# Callback Management
# =============================================================================

def set_recording_callbacks(on_start=None, on_stop=None, on_audio_level=None):
    """Set callbacks for recording events.

    Args:
        on_start: Function to call when recording starts
        on_stop: Function to call when recording stops
        on_audio_level: Function(float) called per audio frame with level 0.0-1.0
    """
    _recording_callbacks["on_start"] = on_start
    _recording_callbacks["on_stop"] = on_stop
    _recording_callbacks["on_audio_level"] = on_audio_level


def get_recording_state() -> dict:
    """Get current recording state (thread-safe snapshot).

    Returns:
        Dictionary with recording state information
    """
    with _recording_state_lock:
        return recording_state.copy()
