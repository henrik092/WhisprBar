"""Audio capture and processing for WhisprBar.

Handles audio recording, voice activity detection (VAD), noise reduction,
and audio chunking for parallel transcription.
"""

import contextlib
import queue
import sys
import threading
import time
from collections import deque
from typing import List, Optional, Tuple

import numpy as np
import sounddevice as sd

from .config import cfg
from .utils import debug

# Audio constants
SAMPLE_RATE = 16000  # 16 kHz sampling rate for Whisper
CHANNELS = 1  # Mono audio
BLOCK_SIZE = 1024  # Audio buffer block size

# Check for optional dependencies
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    webrtcvad = None
    VAD_AVAILABLE = False

try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    nr = None
    NOISEREDUCE_AVAILABLE = False

# Global state for recording (will be managed by main.py later)
AUDIO_QUEUE: Optional[queue.Queue] = None
VAD_MONITOR_QUEUE: Optional[queue.Queue] = None  # Separate queue for VAD monitoring
audio_queue_lock = threading.Lock()
vad_monitor_lock = threading.Lock()
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
}


def list_input_devices() -> List[dict]:
    """List all available audio input devices.

    Returns:
        List of dicts with 'index' and 'name' keys for each input device
    """
    devices = []
    for idx, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) > 0:
            devices.append({
                "index": idx,
                "name": info.get("name", f"Device {idx}"),
            })
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

    # Also feed to VAD monitor queue if it exists
    with vad_monitor_lock:
        vad_queue_obj = VAD_MONITOR_QUEUE
        if vad_queue_obj is not None:
            try:
                vad_queue_obj.put_nowait(data_copy)
            except queue.Full:
                # VAD queue full, skip this chunk (monitor is lagging)
                pass


def vad_auto_stop_monitor() -> None:
    """Monitor recording and auto-stop after sustained silence.

    Runs in separate thread. Uses energy-based voice activity detection
    to automatically stop recording when user stops speaking.
    """
    if not cfg.get("vad_auto_stop_enabled") or not VAD_AVAILABLE:
        return

    silence_threshold = max(0.5, float(cfg.get("vad_auto_stop_silence_seconds", 2.0)))
    check_interval = 0.5  # Check every 500ms
    buffer_seconds = silence_threshold + 1.0  # Buffer slightly more than threshold
    buffer_samples = int(SAMPLE_RATE * buffer_seconds)

    # Use deque with maxlen for O(1) operations instead of list with O(n) pop(0)
    # BUG-008 fix: deque auto-discards oldest items when maxlen is exceeded
    max_chunks = (buffer_samples // BLOCK_SIZE) + 2  # +2 for safety margin
    audio_buffer = deque(maxlen=max_chunks)
    silence_start = None

    debug(f"VAD auto-stop monitor started (threshold: {silence_threshold}s, max_chunks: {max_chunks})")

    try:
        while recording_state.get("recording"):
            time.sleep(check_interval)

            # Get monitor queue reference
            with vad_monitor_lock:
                monitor_queue = VAD_MONITOR_QUEUE
                if monitor_queue is None:
                    break

            # Collect all available chunks from monitor queue (non-blocking)
            try:
                while True:
                    try:
                        chunk = monitor_queue.get_nowait()
                        audio_buffer.append(chunk)  # O(1) with deque, auto-bounded
                    except queue.Empty:
                        break
            except Exception:
                continue

            # No manual trimming needed - deque with maxlen handles it automatically

            # Need enough audio to check
            if not audio_buffer:
                continue

            # Concatenate buffer and check for speech
            buffer_audio = np.concatenate(audio_buffer, axis=0)
            if buffer_audio.shape[0] < int(SAMPLE_RATE * 0.5):  # At least 500ms
                continue

            # Simple energy-based VAD check (lightweight)
            mono = buffer_audio.reshape(-1).astype(np.float32)
            rms = float(np.sqrt(np.mean(np.square(mono))))
            energy_floor = float(cfg.get("vad_energy_floor", 0.0005))
            energy_ratio = float(cfg.get("vad_energy_ratio", 0.05))

            # Detect speech vs silence
            has_speech = rms > max(energy_floor, energy_ratio * 0.1)

            if has_speech:
                # Reset silence counter
                if silence_start is not None:
                    debug("VAD auto-stop: speech detected, resetting silence counter")
                silence_start = None
            else:
                # Start or continue silence tracking
                if silence_start is None:
                    silence_start = time.monotonic()
                    debug(f"VAD auto-stop: silence detected, starting counter (RMS: {rms:.6f})")
                else:
                    silence_duration = time.monotonic() - silence_start
                    if silence_duration >= silence_threshold:
                        debug(f"VAD auto-stop: {silence_duration:.1f}s silence detected, stopping recording")
                        # Note: notify() would be called here but that's in main
                        # Trigger stop in main thread
                        threading.Thread(target=stop_recording, daemon=True).start()
                        break
    finally:
        # Always clear buffer on exit to prevent memory leak
        audio_buffer.clear()
        debug("VAD auto-stop monitor stopped and buffer cleared")


def start_recording() -> None:
    """Start audio recording.

    Opens audio stream and begins capturing audio to queue.
    Optionally starts VAD auto-stop monitor if enabled.
    """
    global AUDIO_QUEUE, VAD_MONITOR_QUEUE

    if recording_state.get("recording"):
        return

    update_device_index()

    try:
        # Use unbounded queue to support recordings of any length
        # Memory usage is self-limiting: bounded by user behavior (hotkey release)
        # Queue is drained immediately after recording stops and then destroyed
        # Example: 5-minute recording = 5min × 60s × 16kHz × 4 bytes = 19.2 MB
        # This is acceptable for modern systems and prevents truncation of long recordings
        queue_obj: queue.Queue = queue.Queue()
        with audio_queue_lock:
            AUDIO_QUEUE = queue_obj

        # Create separate queue for VAD monitoring if auto-stop is enabled
        if cfg.get("vad_auto_stop_enabled") and VAD_AVAILABLE:
            vad_queue_obj: queue.Queue = queue.Queue(maxsize=100)  # Limit size to prevent memory issues
            with vad_monitor_lock:
                VAD_MONITOR_QUEUE = vad_queue_obj

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=BLOCK_SIZE,
            callback=recording_callback,
            dtype="float32",
            device=recording_state.get("device_idx"),
        )
        stream.start()
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
        with vad_monitor_lock:
            VAD_MONITOR_QUEUE = None
        print(f"[ERROR] start_recording failed: {exc}", file=sys.stderr)
        raise


def stop_recording() -> Optional[np.ndarray]:
    """Stop audio recording and return captured audio.

    Stops the audio stream, collects all queued audio data, and
    concatenates it into a single numpy array.

    Returns:
        Audio data as float32 numpy array, or None if no audio captured
    """
    global AUDIO_QUEUE, VAD_MONITOR_QUEUE

    if not recording_state.get("recording"):
        return None

    with audio_queue_lock:
        queue_obj = AUDIO_QUEUE

    stream = recording_state.get("stream")
    recording_state["recording"] = False

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
        with vad_monitor_lock:
            VAD_MONITOR_QUEUE = None

    if not frames:
        debug("No audio captured")
        audio_data = None
    else:
        audio_data = np.concatenate(frames, axis=0)
        duration = audio_data.shape[0] / SAMPLE_RATE
        debug(f"Captured audio duration: {duration:.2f}s, samples: {audio_data.shape[0]}")

    # Store audio data in recording state for main.py to access
    recording_state["audio_data"] = audio_data

    # Call on_stop callback if set
    if _recording_callbacks.get("on_stop"):
        try:
            _recording_callbacks["on_stop"]()
        except Exception as exc:
            debug(f"Recording stop callback error: {exc}")

    return audio_data


def _drop_short_runs(mask: np.ndarray, min_len: int) -> np.ndarray:
    """Remove short runs of True values from boolean mask.

    Helper function for VAD to filter out brief noise spikes.
    Optimized with NumPy vectorization instead of Python loops.

    Args:
        mask: Boolean numpy array
        min_len: Minimum run length to keep

    Returns:
        Cleaned mask with short runs removed
    """
    if min_len <= 1:
        return mask

    cleaned = mask.copy()

    # Find boundaries of True runs using vectorized diff
    # Pad with False to handle runs at start/end
    padded = np.pad(cleaned, (1, 1), mode='constant', constant_values=False)
    diff = np.diff(padded.astype(int))

    # Run starts where diff == 1, ends where diff == -1
    # The indices from diff correspond directly to the original array
    # (padding offset is automatically handled by np.diff behavior)
    run_starts = np.where(diff == 1)[0]
    run_ends = np.where(diff == -1)[0]

    # Calculate run lengths
    run_lengths = run_ends - run_starts

    # Find runs that are too short
    short_runs = run_lengths < min_len

    # Zero out short runs (indices work directly on original array)
    for start, end in zip(run_starts[short_runs], run_ends[short_runs]):
        cleaned[start:end] = False

    return cleaned


def apply_noise_reduction(audio: np.ndarray) -> np.ndarray:
    """Apply noise reduction to audio.

    Uses noisereduce library to remove stationary background noise
    (fan, hum, keyboard clicks, etc.).

    Args:
        audio: Input audio as numpy array

    Returns:
        Noise-reduced audio, or original if reduction disabled/fails
    """
    if not cfg.get("noise_reduction_enabled") or not NOISEREDUCE_AVAILABLE:
        return audio

    if nr is None:
        return audio

    try:
        strength = max(0.0, min(1.0, float(cfg.get("noise_reduction_strength", 0.7))))
        debug(f"Applying noise reduction (strength: {strength:.2f})")

        # noisereduce expects mono float32
        mono = audio.reshape(-1).astype(np.float32)

        # Apply noise reduction
        reduced = nr.reduce_noise(
            y=mono,
            sr=SAMPLE_RATE,
            stationary=True,  # Assume stationary noise (background hum, fan, etc.)
            prop_decrease=strength,
        )

        debug(f"Noise reduction applied: {mono.shape[0]} samples processed")
        return reduced.astype(np.float32)

    except Exception as exc:
        debug(f"Noise reduction failed ({exc}), using original audio")
        return audio


def apply_vad(audio: np.ndarray) -> np.ndarray:
    """Apply Voice Activity Detection to remove silence.

    Uses webrtcvad with energy-based fallback to detect and keep only
    speech segments. Removes silence before/after speech and bridges
    short pauses.

    Args:
        audio: Input audio as numpy array

    Returns:
        Filtered audio with silence removed, or original if VAD disabled/unavailable
    """
    # Optimize: Use view instead of copy where possible
    if audio.dtype == np.float32:
        mono = audio.reshape(-1)
    else:
        mono = np.asarray(audio, dtype=np.float32).reshape(-1)

    if not cfg.get("use_vad") or not VAD_AVAILABLE:
        return mono

    # Convert to 16-bit PCM for webrtcvad
    # Optimize: Combine clip and multiply in one operation to save memory
    pcm16 = np.clip(mono * 32767, -32768, 32767).astype(np.int16)

    # Frame setup (webrtcvad requires 10/20/30ms frames)
    frame_ms = 30
    frame_length = int(SAMPLE_RATE * frame_ms / 1000)
    if frame_length <= 0:
        return mono

    total_frames = len(pcm16) // frame_length
    if total_frames == 0:
        return mono

    # Split into frames (drop remainder for now)
    usable_samples = total_frames * frame_length
    trimmed_pcm = pcm16[:usable_samples]
    remainder = pcm16[usable_samples:]
    if remainder.ndim > 1:
        remainder = remainder.reshape(-1)
    frames = trimmed_pcm.reshape(total_frames, frame_length)

    # Initialize VAD
    vad_mode = int(cfg.get("vad_mode", 1))
    vad_mode = max(0, min(3, vad_mode))
    try:
        vad = webrtcvad.Vad(vad_mode)
    except (ValueError, TypeError) as exc:
        debug(f"Invalid VAD mode {vad_mode} ({exc}); falling back to default")
        vad = webrtcvad.Vad(1)

    # Run VAD on each frame
    speech_mask = np.zeros(total_frames, dtype=bool)
    for idx, frame in enumerate(frames):
        try:
            speech_mask[idx] = vad.is_speech(frame.tobytes(), SAMPLE_RATE)
        except (ValueError, TypeError) as exc:
            debug(f"VAD frame failed ({exc}); disabling")
            return mono

    # Energy-based safety net for quiet speech
    # Optimize: Compute RMS directly from int16 to avoid float conversion
    rms = np.sqrt(np.mean(np.square(frames.astype(np.float32)), axis=1)) / 32767.0
    max_rms = float(rms.max()) if rms.size else 0.0

    energy_floor = float(cfg.get("vad_energy_floor", 0.0005))
    energy_ratio_cfg = float(cfg.get("vad_energy_ratio", 0.05))
    energy_ratio = max(0.005, min(energy_ratio_cfg, 0.3))
    energy_threshold = max(energy_floor, max_rms * energy_ratio)

    # Adaptive threshold based on percentile
    nonzero_rms = rms[rms > energy_floor]
    if nonzero_rms.size:
        percentile = float(np.percentile(nonzero_rms, 75))
        energy_threshold = min(energy_threshold, max(energy_floor, percentile))

    energy_mask = rms >= energy_threshold if rms.size else np.zeros_like(speech_mask)

    # Soft energy mask for very quiet speech
    soft_ratio = max(0.002, energy_ratio * 0.5)
    soft_threshold = max(energy_floor * 1.5, max_rms * soft_ratio)
    soft_mask = rms >= soft_threshold if rms.size else np.zeros_like(speech_mask)

    min_energy_frames = max(1, int(cfg.get("vad_min_energy_frames", 3)))
    if soft_mask.any():
        soft_mask = _drop_short_runs(soft_mask, min_energy_frames)

    # Combine all masks
    combined_mask = speech_mask | energy_mask | soft_mask

    if not combined_mask.any():
        debug("VAD+energy found no speech; returning original audio")
        return mono

    extra_frames = int(np.count_nonzero(energy_mask & ~speech_mask))
    if extra_frames:
        debug(f"Energy boost added {extra_frames} frames to VAD (threshold {energy_threshold:.4f})")

    soft_extra = int(np.count_nonzero(soft_mask & ~(speech_mask | energy_mask)))
    if soft_extra:
        debug(f"Soft energy added {soft_extra} frames to VAD (threshold {soft_threshold:.4f})")

    # Bridge short gaps between speech segments
    bridge_ms = int(cfg.get("vad_bridge_ms", 120))
    bridge_ms = max(0, bridge_ms)
    bridge_frames = int(round(bridge_ms / frame_ms)) if bridge_ms else 0

    if bridge_frames > 0:
        kernel = np.ones(bridge_frames * 2 + 1, dtype=int)
        combined_mask = np.convolve(combined_mask.astype(int), kernel, mode="same") > 0

    if min_energy_frames > 1:
        combined_mask = _drop_short_runs(combined_mask, min_energy_frames)

    voiced_indices = np.flatnonzero(combined_mask)
    if voiced_indices.size == 0:
        return mono

    # Padding around speech segments
    padding_ms = int(cfg.get("vad_padding_ms", 200))
    padding_ms = max(0, padding_ms)
    padding_frames = max(1, int(round(padding_ms / frame_ms)))

    # Check if remainder has energy
    remainder_flat = remainder.reshape(-1)
    remainder_rms = (
        float(np.sqrt(np.mean(np.square(remainder_flat.astype(np.float32) / 32767.0))))
        if remainder_flat.size
        else 0.0
    )

    # Group consecutive voiced frames into segments
    segments: List[Tuple[int, int]] = []
    segment_start = int(voiced_indices[0])
    prev_idx = int(voiced_indices[0])

    for raw_idx in voiced_indices[1:]:
        idx = int(raw_idx)
        if idx - prev_idx > 1:
            segments.append((segment_start, prev_idx))
            segment_start = idx
        prev_idx = idx
    segments.append((segment_start, prev_idx))

    # Extract segments with padding
    segment_buffers: List[np.ndarray] = []
    tail_appended = False

    for seg_start, seg_end in segments:
        start_idx = max(0, seg_start - padding_frames)
        end_idx = min(total_frames, seg_end + padding_frames + 1)

        segment_frames = frames[start_idx:end_idx]
        if segment_frames.size == 0:
            continue

        segment_int = segment_frames.reshape(-1)

        # Append remainder to last segment if it has energy
        if (
            not tail_appended
            and remainder_flat.size
            and end_idx >= total_frames
            and remainder_rms >= energy_floor
        ):
            segment_int = np.concatenate((segment_int, remainder_flat))
            tail_appended = True

        segment_buffers.append(segment_int)

    if not segment_buffers:
        return mono

    # Optimize: Concatenate and convert in one step to save memory
    processed_int = np.concatenate(segment_buffers)
    # Use *= for in-place operation to reduce memory allocation
    processed_pcm = processed_int.astype(np.float32)
    processed_pcm /= 32767.0  # In-place division

    # Safety check: don't remove too much audio
    retained_ratio = processed_pcm.size / mono.size if mono.size else 1.0
    min_ratio = float(cfg.get("vad_min_output_ratio", 0.4))
    if retained_ratio < min_ratio:
        debug(f"VAD output ratio {retained_ratio:.2f} below {min_ratio:.2f}; using original audio")
        return mono

    debug(f"VAD retained {retained_ratio:.2%} of audio ({len(segment_buffers)} segments)")
    return processed_pcm


def split_audio_into_chunks(audio: np.ndarray) -> List[Tuple[np.ndarray, int, int]]:
    """Split audio into overlapping chunks for parallel transcription.

    Args:
        audio: Input audio as numpy array

    Returns:
        List of tuples (chunk_audio, start_sample, end_sample)
    """
    duration_seconds = audio.size / SAMPLE_RATE
    chunk_duration = max(5.0, float(cfg.get("chunk_duration_seconds", 30.0)))
    overlap_duration = max(0.5, min(chunk_duration * 0.2, float(cfg.get("chunk_overlap_seconds", 2.0))))

    chunk_samples = int(chunk_duration * SAMPLE_RATE)
    overlap_samples = int(overlap_duration * SAMPLE_RATE)
    step_samples = chunk_samples - overlap_samples

    chunks: List[Tuple[np.ndarray, int, int]] = []
    start = 0

    while start < audio.size:
        end = min(start + chunk_samples, audio.size)
        chunk = audio[start:end]

        # Skip chunks that are too short
        if chunk.size < int(SAMPLE_RATE * 1.0):  # Min 1 second
            break

        chunks.append((chunk, start, end))

        # If we've reached the end, stop
        if end >= audio.size:
            break

        start += step_samples

    debug(f"Split {duration_seconds:.1f}s audio into {len(chunks)} chunks "
          f"(chunk={chunk_duration:.1f}s, overlap={overlap_duration:.1f}s)")
    return chunks


# =============================================================================
# Callback Management
# =============================================================================

def set_recording_callbacks(on_start=None, on_stop=None):
    """Set callbacks for recording events.
    
    Args:
        on_start: Function to call when recording starts
        on_stop: Function to call when recording stops
    """
    _recording_callbacks["on_start"] = on_start
    _recording_callbacks["on_stop"] = on_stop


def get_recording_state() -> dict:
    """Get current recording state.
    
    Returns:
        Dictionary with recording state information
    """
    return recording_state.copy()
