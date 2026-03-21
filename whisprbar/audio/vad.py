"""Voice Activity Detection (VAD) for WhisprBar.

Handles VAD processing and auto-stop monitoring during recording.
"""

import queue
import threading
import time
from collections import deque
from typing import List, Optional, Tuple

import numpy as np

from whisprbar.config import cfg
from whisprbar.utils import debug
from .processing import SAMPLE_RATE, BLOCK_SIZE

# Check for optional dependencies
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    webrtcvad = None
    VAD_AVAILABLE = False

# VAD monitor queue for auto-stop functionality
VAD_MONITOR_QUEUE: Optional[queue.Queue] = None
vad_monitor_lock = threading.Lock()


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


def vad_auto_stop_monitor() -> None:
    """Monitor recording and auto-stop after sustained silence.

    Runs in separate thread. Uses energy-based voice activity detection
    to automatically stop recording when user stops speaking.
    """
    if not cfg.get("vad_auto_stop_enabled") or not VAD_AVAILABLE:
        return

    # Import here to avoid circular imports
    from .recorder import recording_state, _recording_state_lock, stop_recording

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
        while True:
            with _recording_state_lock:
                if not recording_state.get("recording"):
                    break
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
