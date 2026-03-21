"""Audio processing utilities for WhisprBar.

Contains audio constants, noise reduction, and chunking functions.
"""

from typing import List, Tuple

import numpy as np

from whisprbar.config import cfg
from whisprbar.utils import debug

# Audio constants
SAMPLE_RATE = 16000  # 16 kHz sampling rate for Whisper
CHANNELS = 1  # Mono audio
BLOCK_SIZE = 1024  # Audio buffer block size

# Check for optional dependencies
try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    nr = None
    NOISEREDUCE_AVAILABLE = False


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
