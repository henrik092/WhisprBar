"""Audio chunking and main transcription orchestration for WhisprBar."""

import sys
from typing import List, Optional, Tuple

import numpy as np

from .base import Transcriber
from .factory import get_transcriber
from .postprocess import postprocess_transcript
from whisprbar.config import cfg
from whisprbar.utils import debug, notify
from whisprbar.ui import show_live_overlay, update_live_overlay, hide_live_overlay
from whisprbar.audio import SAMPLE_RATE, split_audio_into_chunks


def transcribe_chunk(
    chunk_audio: np.ndarray, chunk_index: int, total_chunks: int, language: str = "de"
) -> Optional[str]:
    """Transcribe a single chunk using current transcriber backend.

    Args:
        chunk_audio: Audio chunk as float32 numpy array
        chunk_index: Index of this chunk (0-based)
        total_chunks: Total number of chunks
        language: Language code (e.g., "de", "en")

    Returns:
        Transcribed text or None on error
    """
    try:
        chunk_duration = chunk_audio.size / SAMPLE_RATE
        debug(
            f"Transcribing chunk {chunk_index + 1}/{total_chunks} "
            f"({chunk_duration:.1f}s)"
        )

        transcriber = get_transcriber()
        transcript = transcriber.transcribe_chunk(chunk_audio, language)

        if transcript:
            debug(f"Chunk {chunk_index + 1}/{total_chunks}: {len(transcript)} chars")

        return transcript

    except Exception as exc:
        print(
            f"[ERROR] Chunk {chunk_index + 1} transcription failed: {exc}",
            file=sys.stderr,
        )
        return None


def merge_chunk_transcripts(
    transcripts: List[str], chunks_info: List[Tuple[np.ndarray, int, int]]
) -> str:
    """Merge overlapping chunk transcripts intelligently.

    Attempts to detect and remove duplicate text at chunk boundaries.

    Args:
        transcripts: List of transcript strings
        chunks_info: List of chunk metadata (not currently used)

    Returns:
        Merged transcript
    """
    if not transcripts:
        return ""

    if len(transcripts) == 1:
        return transcripts[0]

    # Start with first transcript
    merged = transcripts[0]

    # Merge remaining transcripts
    for i, transcript in enumerate(transcripts[1:], start=1):
        if not transcript:
            continue

        # Try to find overlap by checking last N words of merged
        # with first N words of current
        merged_words = merged.split()
        transcript_words = transcript.split()

        # Check for overlapping phrases (up to 10 words)
        overlap_found = False
        for overlap_len in range(
            min(10, len(merged_words), len(transcript_words)), 0, -1
        ):
            if merged_words[-overlap_len:] == transcript_words[:overlap_len]:
                # Found overlap, merge by skipping the duplicate
                merged = " ".join(merged_words + transcript_words[overlap_len:])
                overlap_found = True
                debug(f"Merged chunk {i} with {overlap_len}-word overlap")
                break

        if not overlap_found:
            # No overlap found, just append with space
            merged = merged + " " + transcript

    return merged


def transcribe_audio_chunked(audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio using chunking for better performance on long recordings.

    Splits audio into chunks, transcribes in parallel, and merges results.

    Args:
        audio: Audio data as float32 numpy array
        language: Language code (e.g., "de", "en")

    Returns:
        Transcribed text or None on error
    """
    chunks = split_audio_into_chunks(audio)

    if not chunks:
        debug("No chunks created, audio too short")
        return None

    notify(f"Transcribing {len(chunks)} chunks...")
    update_live_overlay(
        f"Transcribing {len(chunks)} chunks...", f"0/{len(chunks)} completed"
    )

    # Transcribe chunks in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed

    max_workers = min(5, len(chunks))  # Max 5 parallel requests
    transcripts: List[Optional[str]] = [None] * len(chunks)
    completed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(transcribe_chunk, chunk_audio, idx, len(chunks), language): idx
            for idx, (chunk_audio, _, _) in enumerate(chunks)
        }

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                transcripts[idx] = future.result()
                completed_count += 1

                # Update overlay with progress
                partial_text = " ".join(t for t in transcripts if t is not None)
                update_live_overlay(
                    partial_text or "Processing...",
                    f"Chunk {completed_count}/{len(chunks)} completed",
                )
            except Exception as exc:
                print(f"[ERROR] Chunk {idx + 1} failed: {exc}", file=sys.stderr)
                transcripts[idx] = None
                completed_count += 1

    # Filter out failed chunks
    valid_transcripts = [t for t in transcripts if t]

    if not valid_transcripts:
        debug("All chunks failed transcription")
        return None

    # Merge transcripts
    merged = merge_chunk_transcripts(valid_transcripts, chunks)
    debug(
        f"Final merged transcript: {len(merged)} chars from "
        f"{len(valid_transcripts)}/{len(chunks)} chunks"
    )

    return merged


def transcribe_audio(audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio and return the text.

    IMPORTANT: Expects audio to be already preprocessed (VAD + noise reduction)
    by the caller (main.py). This function focuses on transcription only.

    This function:
    1. Checks if transcriber is available
    2. Validates audio has sufficient content
    3. Chooses between chunked or single-chunk transcription
    4. Applies postprocessing
    5. Returns the transcript text

    The caller is responsible for:
    - Audio preprocessing (VAD, noise reduction)
    - Clipboard operations
    - Auto-paste
    - Notifications

    Args:
        audio: Preprocessed audio data as float32 numpy array
        language: Language code (e.g., "de", "en")

    Returns:
        Transcribed text or None on error
    """
    # Check if transcriber is available
    from .openai import OpenAITranscriber
    transcriber = get_transcriber()
    if isinstance(transcriber, OpenAITranscriber) and not transcriber.ensure_client():
        debug("OpenAI API key not configured")
        return None

    # NOTE: show_live_overlay() is intentionally NOT called here.
    # main.py's transcribe_thread already called it before invoking this function.
    # Calling it again would duplicate the overlay and cause UI glitches.

    try:
        # Audio is already preprocessed (VAD + noise reduction done in main.py)
        processed = audio
        duration = processed.shape[0] / SAMPLE_RATE
        # NOTE: No notify() here — desktop notifications for normal processing are noisy.
        # Errors are notified by the caller (main.py).
        debug(f"Transcribing {duration:.2f}s of preprocessed audio")

        # Check if enough speech remains
        if processed.size < int(SAMPLE_RATE * 0.25):
            debug("Transcription skipped: audio too short (< 0.25s)")
            hide_live_overlay()
            return None

        # Check if we should use chunking
        chunking_enabled = cfg.get("chunking_enabled", True)
        chunking_threshold = max(
            30.0, float(cfg.get("chunking_threshold_seconds", 60.0))
        )
        use_chunking = chunking_enabled and duration >= chunking_threshold

        # Transcribe
        if use_chunking:
            debug(
                f"Using chunked transcription (duration {duration:.1f}s >= "
                f"threshold {chunking_threshold:.1f}s)"
            )
            transcript = transcribe_audio_chunked(processed, language)
            if transcript is None:
                hide_live_overlay()
                return None
        else:
            # Single-chunk transcription
            debug(f"Using single-chunk transcription (duration {duration:.1f}s)")

            transcript = transcriber.transcribe(processed, language)

            if transcript is None:
                hide_live_overlay()
                return None

            debug(f"Received transcript length: {len(transcript)}")

    except Exception as exc:
        debug(f"Transcription failed: {exc}")
        hide_live_overlay()
        return None

    if not transcript:
        hide_live_overlay()
        return None

    # Apply post-processing
    transcript = postprocess_transcript(transcript, language=language)

    # Update overlay with final transcript
    update_live_overlay(transcript, "Complete!")

    debug(f"Transcription complete: {len(transcript)} chars")
    return transcript
