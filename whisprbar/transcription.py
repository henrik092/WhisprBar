"""Transcription backends and processing for WhisprBar.

Provides multiple transcription backends (OpenAI API, faster-whisper, sherpa-onnx),
audio chunking for long recordings, and text postprocessing.
"""

import contextlib
import json
import os
import sys
import tempfile
import threading
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

# Import from whisprbar modules
from .config import cfg, load_env_file_values
from .utils import debug, notify, write_history
from .ui import show_live_overlay, update_live_overlay, hide_live_overlay

# Import audio processing functions - no circular import exists
# (audio.py does not import from transcription.py)
from .audio import apply_vad, apply_noise_reduction, SAMPLE_RATE, CHANNELS

# Transcription model
OPENAI_MODEL = os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe")


class Transcriber:
    """Abstract base class for transcription backends."""

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio and return text. Returns None on error.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code (e.g., "de", "en")

        Returns:
            Transcribed text or None on error
        """
        raise NotImplementedError("Subclasses must implement transcribe()")

    def transcribe_chunk(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe a single chunk. Default implementation uses transcribe().

        Args:
            audio: Audio chunk as float32 numpy array
            language: Language code

        Returns:
            Transcribed text or None on error
        """
        return self.transcribe(audio, language)

    def supports_streaming(self) -> bool:
        """Check if this backend supports streaming transcription.

        Returns:
            True if streaming is supported
        """
        return False

    def get_name(self) -> str:
        """Get backend name for display.

        Returns:
            Human-readable backend name
        """
        raise NotImplementedError("Subclasses must implement get_name()")


class OpenAITranscriber(Transcriber):
    """OpenAI Whisper API transcription backend.

    Transcribes audio using OpenAI's cloud API. Requires OPENAI_API_KEY.
    """

    def __init__(self):
        """Initialize OpenAI transcriber."""
        self.client = None
        self.client_lock = threading.Lock()

    def ensure_client(self) -> bool:
        """Ensure OpenAI client is initialized.

        Returns:
            True if client is ready, False if API key missing
        """
        with self.client_lock:
            if self.client is not None:
                return True

            # Try environment variable first
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                # Try config file
                env_values = load_env_file_values()
                api_key = env_values.get("OPENAI_API_KEY")

            if not api_key:
                debug("OpenAI API key not found")
                return False

            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=api_key)
                debug("OpenAI client initialized")
                return True
            except Exception as exc:
                debug(f"Failed to initialize OpenAI client: {exc}")
                return False

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using OpenAI Whisper API.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code

        Returns:
            Transcribed text or None on error
        """
        if not self.ensure_client():
            return None

        try:
            # Prepare audio: clip to [-1, 1] and convert to PCM16
            pcm = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm * 32767).astype(np.int16)

            # Write to temp WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                # Create WAV file
                with wave.open(str(tmp_path), "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(pcm16.tobytes())

                # Call OpenAI API
                with tmp_path.open("rb") as handle:
                    response = self.client.audio.transcriptions.create(
                        model=OPENAI_MODEL,
                        file=handle,
                        language=language,
                        temperature=0.0,
                    )

                transcript = response.text.strip()
                debug(f"OpenAI transcription: {len(transcript)} chars")
                return transcript

            finally:
                # Clean up temp file
                with contextlib.suppress(Exception):
                    tmp_path.unlink()

        except Exception as exc:
            debug(f"OpenAI transcription failed: {exc}")
            return None

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            "OpenAI Whisper API"
        """
        return "OpenAI Whisper API"


class FasterWhisperTranscriber(Transcriber):
    """Local faster-whisper transcription backend (CPU/GPU).

    Transcribes audio locally using faster-whisper. Supports CPU and GPU.
    Model is downloaded to ~/.cache/huggingface/hub/ on first use.
    """

    def __init__(self):
        """Initialize faster-whisper transcriber."""
        self.model = None
        self.model_lock = threading.Lock()
        self.model_size = None
        self.device = None

    def ensure_model(self) -> bool:
        """Ensure faster-whisper model is loaded.

        Returns:
            True if model is ready, False on error
        """
        with self.model_lock:
            if self.model is not None:
                return True

            # Get model settings from config
            model_size = cfg.get("faster_whisper_model", "medium")
            device = cfg.get("faster_whisper_device", "cpu")
            compute_type = cfg.get("faster_whisper_compute_type", "int8")

            try:
                from faster_whisper import WhisperModel

                debug(
                    f"Loading faster-whisper: {model_size} on {device} ({compute_type})"
                )

                # Model will be downloaded to cache automatically
                self.model = WhisperModel(
                    model_size,
                    device=device,
                    compute_type=compute_type,
                    download_root=None,  # Use default cache
                )

                self.model_size = model_size
                self.device = device
                debug("faster-whisper model loaded successfully")
                return True

            except Exception as exc:
                debug(f"Failed to load faster-whisper model: {exc}")
                return False

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using faster-whisper.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code

        Returns:
            Transcribed text or None on error
        """
        if not self.ensure_model():
            return None

        try:
            # Prepare audio (faster-whisper expects float32)
            pcm = np.clip(audio, -1.0, 1.0).astype(np.float32)

            # Transcribe
            segments, info = self.model.transcribe(
                pcm,
                language=language,
                beam_size=5,
                vad_filter=False,  # We already do VAD preprocessing
                word_timestamps=False,
            )

            # Collect all segments
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            result = " ".join(text_parts).strip()
            debug(f"faster-whisper transcription: {len(result)} chars")
            return result

        except Exception as exc:
            debug(f"faster-whisper transcription failed: {exc}")
            return None

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            Backend name with model info if available
        """
        if self.model_size:
            return f"faster-whisper ({self.model_size}, {self.device})"
        return "faster-whisper (offline)"


class StreamingTranscriber(Transcriber):
    """Streaming transcription backend using sherpa-onnx Whisper models.

    Transcribes audio using sherpa-onnx ONNX runtime. Supports streaming.
    Model is downloaded from Hugging Face on first use.
    """

    def __init__(self):
        """Initialize sherpa-onnx transcriber."""
        self.recognizer = None
        self.model_lock = threading.Lock()
        self.model_name = None

    def ensure_model(self) -> bool:
        """Ensure sherpa-onnx model is loaded.

        Returns:
            True if model is ready, False on error
        """
        with self.model_lock:
            if self.recognizer is not None:
                return True

            model_name = cfg.get("streaming_model", "tiny")

            # Import sherpa_onnx
            try:
                import sherpa_onnx
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                debug(f"sherpa-onnx import failed: {exc}")
                return False

            # Download model if needed
            try:
                model_dir = snapshot_download(
                    repo_id=f"csukuangfj/sherpa-onnx-whisper-{model_name}",
                    cache_dir=os.path.expanduser("~/.cache/sherpa-onnx"),
                )
                debug(f"sherpa-onnx model downloaded to: {model_dir}")
            except Exception as exc:
                debug(f"Model download failed: {exc}")
                return False

            # Create recognizer
            try:
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                    encoder=os.path.join(model_dir, f"{model_name}-encoder.int8.onnx"),
                    decoder=os.path.join(model_dir, f"{model_name}-decoder.int8.onnx"),
                    tokens=os.path.join(model_dir, f"{model_name}-tokens.txt"),
                    language=cfg.get("language", "de"),
                    task="transcribe",
                    num_threads=2,
                    provider="cpu",
                )
                self.model_name = model_name
                debug(f"sherpa-onnx recognizer created with model: {model_name}")
                return True
            except Exception as exc:
                debug(f"Failed to create recognizer: {exc}")
                return False

    def transcribe(self, audio: np.ndarray, language: str = "de") -> Optional[str]:
        """Transcribe audio using sherpa-onnx.

        Args:
            audio: Audio data as float32 numpy array
            language: Language code (currently not used by sherpa-onnx)

        Returns:
            Transcribed text or None on error
        """
        debug("StreamingTranscriber.transcribe() called")
        if not self.ensure_model():
            debug("sherpa-onnx model not available")
            return None

        try:
            # Resample to 16kHz if needed (Whisper always uses 16kHz)
            target_sr = 16000
            if audio.shape[0] > 0:
                current_sr = SAMPLE_RATE
                if current_sr != target_sr:
                    debug(f"Resampling audio from {current_sr}Hz to {target_sr}Hz")
                    # Simple resampling using numpy
                    duration = len(audio) / current_sr
                    target_length = int(duration * target_sr)
                    indices = np.linspace(0, len(audio) - 1, target_length)
                    audio = np.interp(indices, np.arange(len(audio)), audio)

            # Normalize audio to float32 [-1, 1]
            pcm = np.clip(audio, -1.0, 1.0).astype(np.float32)
            debug(f"Audio prepared: {len(pcm)} samples")

            # Create stream and transcribe
            debug("Creating sherpa-onnx stream...")
            stream = self.recognizer.create_stream()
            debug("Feeding audio to stream...")
            stream.accept_waveform(target_sr, pcm)
            debug("Decoding stream...")
            self.recognizer.decode_stream(stream)
            debug("Decoding complete, getting result...")

            text = stream.result.text.strip()
            debug(f"Raw transcription result: '{text}'")

            # Filter out Whisper hallucinations
            if text in ("[Musik]", "[Music]", "[Silence]", "[BLANK_AUDIO]", ""):
                debug("Filtered out hallucination")
                return None

            debug(f"sherpa-onnx transcription: {text[:100]}...")
            return text

        except Exception as exc:
            debug(f"sherpa-onnx transcription failed: {exc}")
            import traceback

            debug(traceback.format_exc())
            return None

    def supports_streaming(self) -> bool:
        """Check if streaming is supported.

        Returns:
            True (sherpa-onnx supports streaming)
        """
        return True

    def get_name(self) -> str:
        """Get backend name.

        Returns:
            Backend name with model info if available
        """
        if self.model_name:
            return f"sherpa-onnx streaming ({self.model_name})"
        return "sherpa-onnx streaming"


# Global transcriber instance
_transcriber: Optional[Transcriber] = None
_transcriber_lock = threading.Lock()


def get_transcriber() -> Transcriber:
    """Get the current transcriber instance based on config.

    Creates a new transcriber if backend has changed or none exists.
    Thread-safe.

    Returns:
        Transcriber instance (OpenAI, FasterWhisper, or Streaming)
    """
    global _transcriber

    backend = cfg.get("transcription_backend", "openai")

    with _transcriber_lock:
        # Reset transcriber if backend changed
        if _transcriber is not None:
            current_backend = (
                "openai"
                if isinstance(_transcriber, OpenAITranscriber)
                else "faster_whisper"
                if isinstance(_transcriber, FasterWhisperTranscriber)
                else "streaming"
                if isinstance(_transcriber, StreamingTranscriber)
                else "unknown"
            )
            if current_backend != backend:
                debug(f"Backend changed from {current_backend} to {backend}")
                _transcriber = None

        # Create transcriber if needed
        if _transcriber is None:
            if backend == "streaming":
                debug("Creating StreamingTranscriber")
                _transcriber = StreamingTranscriber()
            elif backend == "faster_whisper":
                debug("Creating FasterWhisperTranscriber")
                _transcriber = FasterWhisperTranscriber()
            else:
                # Default to OpenAI
                debug("Creating OpenAITranscriber")
                _transcriber = OpenAITranscriber()

        return _transcriber


def split_audio_into_chunks(
    audio: np.ndarray,
) -> List[Tuple[np.ndarray, int, int]]:
    """Split audio into overlapping chunks for parallel processing.

    Args:
        audio: Audio data as float32 numpy array

    Returns:
        List of (chunk_audio, start_sample, end_sample) tuples
    """
    duration_seconds = audio.size / SAMPLE_RATE
    chunk_duration = max(5.0, float(cfg.get("chunk_duration_seconds", 30.0)))
    overlap_duration = max(
        0.5, min(chunk_duration * 0.2, float(cfg.get("chunk_overlap_seconds", 2.0)))
    )

    chunk_samples = int(chunk_duration * SAMPLE_RATE)
    overlap_samples = int(overlap_duration * SAMPLE_RATE)
    step_samples = chunk_samples - overlap_samples

    chunks: List[Tuple[np.ndarray, int, int]] = []
    start = 0

    while start < audio.size:
        end = min(start + chunk_samples, audio.size)
        chunk = audio[start:end]

        # Skip chunks that are too short (min 1 second)
        if chunk.size < int(SAMPLE_RATE * 1.0):
            break

        chunks.append((chunk, start, end))

        # If we've reached the end, stop
        if end >= audio.size:
            break

        start += step_samples

    debug(
        f"Split {duration_seconds:.1f}s audio into {len(chunks)} chunks "
        f"(chunk={chunk_duration:.1f}s, overlap={overlap_duration:.1f}s)"
    )
    return chunks


def transcribe_chunk(
    chunk_audio: np.ndarray, chunk_index: int, total_chunks: int
) -> Optional[str]:
    """Transcribe a single chunk using current transcriber backend.

    Args:
        chunk_audio: Audio chunk as float32 numpy array
        chunk_index: Index of this chunk (0-based)
        total_chunks: Total number of chunks

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
        language = cfg.get("language", "de")
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


def transcribe_audio_chunked(audio: np.ndarray) -> Optional[str]:
    """Transcribe audio using chunking for better performance on long recordings.

    Splits audio into chunks, transcribes in parallel, and merges results.

    Args:
        audio: Audio data as float32 numpy array

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
            executor.submit(transcribe_chunk, chunk_audio, idx, len(chunks)): idx
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


def postprocess_fix_spacing(text: str) -> str:
    """Fix spacing issues in transcribed text.

    Removes multiple spaces, fixes punctuation spacing, and cleans up quotes/parens.

    Args:
        text: Input text

    Returns:
        Text with fixed spacing
    """
    import re

    # Remove multiple spaces
    text = re.sub(r" +", " ", text)

    # Fix punctuation spacing: remove space before, ensure space after
    # Handles: . , ! ? : ;
    text = re.sub(r"\s+([.,!?:;])", r"\1", text)  # Remove space before
    text = re.sub(r"([.,!?:;])(?=[^\s])", r"\1 ", text)  # Add space after if missing

    # Fix quotes and parentheses
    text = re.sub(r"\(\s+", "(", text)  # No space after opening paren
    text = re.sub(r"\s+\)", ")", text)  # No space before closing paren
    text = re.sub(r'"\s+', '"', text)  # No space after opening quote
    text = re.sub(r'\s+"', '"', text)  # No space before closing quote

    # Fix common formatting issues
    text = re.sub(r"\s+\.", ".", text)  # Remove space before period
    text = re.sub(r"\.\s*\)", ".)", text)  # Fix ". )" to ".)"
    text = re.sub(r"\(\s*\.", "(.", text)  # Fix "( ." to "(."

    return text.strip()


def postprocess_fix_capitalization(text: str, language: str = "de") -> str:
    """Fix capitalization issues in transcribed text.

    Capitalizes first character, after sentence punctuation, and applies
    language-specific rules.

    Args:
        text: Input text
        language: Language code for language-specific rules

    Returns:
        Text with fixed capitalization
    """
    import re

    if not text:
        return text

    # Capitalize first character
    text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()

    # Capitalize after sentence-ending punctuation (. ! ?)
    def capitalize_after_punct(match):
        punct = match.group(1)
        space = match.group(2)
        char = match.group(3)
        return punct + space + char.upper()

    text = re.sub(r"([.!?])(\s+)([a-z])", capitalize_after_punct, text)

    # Language-specific fixes
    if language == "en":
        # Fix standalone "i" → "I"
        text = re.sub(r"\bi\b", "I", text)
        # Fix "i'" contractions (I'm, I'll, I've, etc.)
        text = re.sub(r"\bi'", "I'", text)

    return text


def postprocess_transcript(text: str, language: str = "de") -> str:
    """Apply all post-processing rules to the transcript.

    Args:
        text: Input transcript
        language: Language code

    Returns:
        Postprocessed transcript
    """
    if not cfg.get("postprocess_enabled"):
        return text

    original_length = len(text)
    debug(f"Post-processing transcript ({original_length} chars)")

    # Apply fixes in order
    if cfg.get("postprocess_fix_spacing", True):
        text = postprocess_fix_spacing(text)

    if cfg.get("postprocess_fix_capitalization", True):
        text = postprocess_fix_capitalization(text, language)

    # TODO: Advanced punctuation correction with transformer model
    if cfg.get("postprocess_fix_punctuation", False):
        debug("Advanced punctuation correction not yet implemented")

    final_length = len(text)
    if final_length != original_length:
        debug(
            f"Post-processing: {original_length} → {final_length} chars "
            f"(Δ{final_length - original_length:+d})"
        )

    return text




def transcribe_audio(audio: np.ndarray, language: str = "de") -> Optional[str]:
    """Transcribe audio and return the text.

    This is the main transcription function. It:
    1. Checks if transcriber is available
    2. Applies noise reduction
    3. Applies VAD
    4. Chooses between chunked or single-chunk transcription
    5. Applies postprocessing
    6. Returns the transcript text

    The caller is responsible for clipboard, auto-paste, notifications, etc.

    Args:
        audio: Audio data as float32 numpy array
        language: Language code (e.g., "de", "en")

    Returns:
        Transcribed text or None on error
    """
    # Check if transcriber is available
    transcriber = get_transcriber()
    if isinstance(transcriber, OpenAITranscriber) and not transcriber.ensure_client():
        debug("OpenAI API key not configured")
        return None

    # Show live overlay if enabled
    show_live_overlay(cfg, "Processing audio...")

    try:
        duration = audio.shape[0] / SAMPLE_RATE
        notify("Processing audio...")
        debug(f"Transcribing {duration:.2f}s of audio")

        # Apply noise reduction first (before VAD)
        audio_nr = apply_noise_reduction(audio)

        # Then apply VAD
        processed = apply_vad(audio_nr)
        input_samples = audio.shape[0] if audio.ndim >= 1 else audio.size
        input_seconds = input_samples / SAMPLE_RATE if input_samples else 0.0
        output_seconds = processed.size / SAMPLE_RATE if processed.size else 0.0
        saved_seconds = max(0.0, input_seconds - output_seconds)
        ratio = (output_seconds / input_seconds) if input_seconds else 1.0
        debug(
            f"VAD throughput: input {input_seconds:.2f}s → output {output_seconds:.2f}s "
            f"(saved {saved_seconds:.2f}s, ratio {ratio:.2f})"
        )

        # Check if enough speech remains
        if processed.size < int(SAMPLE_RATE * 0.25):
            debug("Transcription skipped: insufficient speech after VAD")
            hide_live_overlay()
            return None

        # Check if we should use chunking
        chunking_enabled = cfg.get("chunking_enabled", True)
        chunking_threshold = max(
            30.0, float(cfg.get("chunking_threshold_seconds", 60.0))
        )
        use_chunking = chunking_enabled and output_seconds >= chunking_threshold

        # Transcribe
        if use_chunking:
            debug(
                f"Using chunked transcription (duration {output_seconds:.1f}s >= "
                f"threshold {chunking_threshold:.1f}s)"
            )
            transcript = transcribe_audio_chunked(processed)
            if transcript is None:
                hide_live_overlay()
                return None
        else:
            # Single-chunk transcription
            debug(f"Using single-chunk transcription (duration {output_seconds:.1f}s)")

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
