"""Unit tests for whisprbar.transcription module."""

from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from whisprbar import transcription


@pytest.mark.unit
def test_postprocess_fix_spacing_removes_multiple_spaces():
    """Test that postprocess_fix_spacing removes multiple spaces."""
    text = "Hello    world   this  is  a   test"
    result = transcription.postprocess_fix_spacing(text)
    assert "  " not in result
    assert result == "Hello world this is a test"


@pytest.mark.unit
def test_postprocess_fix_spacing_fixes_punctuation():
    """Test that postprocess_fix_spacing fixes punctuation spacing."""
    text = "Hello , world . How are you ?"
    result = transcription.postprocess_fix_spacing(text)
    assert result == "Hello, world. How are you?"


@pytest.mark.unit
def test_postprocess_fix_spacing_fixes_quotes():
    """Test that postprocess_fix_spacing fixes quote spacing."""
    text = '" Hello " and ( test )'
    result = transcription.postprocess_fix_spacing(text)
    assert result == '"Hello" and (test)'


@pytest.mark.unit
def test_postprocess_fix_capitalization_first_char():
    """Test that postprocess_fix_capitalization capitalizes first character."""
    text = "hello world"
    result = transcription.postprocess_fix_capitalization(text)
    assert result[0].isupper()
    assert result == "Hello world"


@pytest.mark.unit
def test_postprocess_fix_capitalization_after_period():
    """Test capitalization after sentence-ending punctuation."""
    text = "Hello. world is great! really? yes."
    result = transcription.postprocess_fix_capitalization(text)
    assert result == "Hello. World is great! Really? Yes."


@pytest.mark.unit
def test_postprocess_fix_capitalization_english_i():
    """Test that English 'i' is capitalized to 'I'."""
    text = "i think i am going to the store"
    result = transcription.postprocess_fix_capitalization(text, language="en")
    assert result == "I think I am going to the store"

    text = "i'm sure i'll be there"
    result = transcription.postprocess_fix_capitalization(text, language="en")
    assert result == "I'm sure I'll be there"


@pytest.mark.unit
def test_postprocess_transcript_disabled(mock_config):
    """Test postprocessing when disabled."""
    from whisprbar import config

    mock_config["postprocess_enabled"] = False
    config.cfg.clear()
    config.cfg.update(mock_config)

    text = "hello   world . this is   a test"
    result = transcription.postprocess_transcript(text)

    # Should return unchanged
    assert result == text


@pytest.mark.unit
def test_postprocess_transcript_enabled(mock_config):
    """Test full postprocessing pipeline."""
    from whisprbar import config

    mock_config["postprocess_enabled"] = True
    mock_config["postprocess_fix_spacing"] = True
    mock_config["postprocess_fix_capitalization"] = True
    config.cfg.clear()
    config.cfg.update(mock_config)

    text = "hello   world . this is   a test  !"
    result = transcription.postprocess_transcript(text, language="en")

    # Should fix spacing and capitalization
    assert "  " not in result
    assert result[0].isupper()
    assert result == "Hello world. This is a test!"


@pytest.mark.unit
def test_split_audio_into_chunks_creates_correct_chunks(sample_audio_long, mock_config):
    """Test audio chunking creates correct number of chunks."""
    from whisprbar import config

    mock_config["chunk_duration_seconds"] = 30.0
    mock_config["chunk_overlap_seconds"] = 2.0
    config.cfg.clear()
    config.cfg.update(mock_config)

    # 90 seconds with 30s chunks and 2s overlap should create 4 chunks
    # Chunk 1: 0-30s, Chunk 2: 28-58s, Chunk 3: 56-86s, Chunk 4: 84-90s
    chunks = transcription.split_audio_into_chunks(sample_audio_long)

    assert len(chunks) >= 3  # At least 3 chunks for 90s audio


@pytest.mark.unit
def test_merge_chunk_transcripts_single_chunk():
    """Test merging single transcript returns it unchanged."""
    transcripts = ["Hello world"]
    chunks_info = []  # Not used in current implementation

    result = transcription.merge_chunk_transcripts(transcripts, chunks_info)

    assert result == "Hello world"


@pytest.mark.unit
def test_merge_chunk_transcripts_no_overlap():
    """Test merging transcripts with no overlap."""
    transcripts = ["Hello world.", "This is a test."]
    chunks_info = []

    result = transcription.merge_chunk_transcripts(transcripts, chunks_info)

    # Should concatenate with space
    assert "Hello world." in result
    assert "This is a test." in result


@pytest.mark.unit
def test_merge_chunk_transcripts_with_overlap():
    """Test merging transcripts with overlapping words."""
    transcripts = ["Hello world this is", "this is a test"]
    chunks_info = []

    result = transcription.merge_chunk_transcripts(transcripts, chunks_info)

    # Should detect "this is" overlap and merge properly
    # Expected: "Hello world this is a test"
    assert result.count("this is") == 1


@pytest.mark.unit
def test_get_transcriber_returns_openai_by_default(mock_config):
    """Test that get_transcriber returns OpenAI transcriber by default."""
    from whisprbar import config

    mock_config["transcription_backend"] = "openai"
    config.cfg.clear()
    config.cfg.update(mock_config)

    # Reset global transcriber
    transcription._transcriber = None

    transcriber = transcription.get_transcriber()

    assert isinstance(transcriber, transcription.OpenAITranscriber)


@pytest.mark.unit
def test_get_transcriber_returns_faster_whisper(mock_config):
    """Test that get_transcriber returns FasterWhisper when configured."""
    from whisprbar import config

    mock_config["transcription_backend"] = "faster_whisper"
    config.cfg.clear()
    config.cfg.update(mock_config)

    # Reset global transcriber
    transcription._transcriber = None

    transcriber = transcription.get_transcriber()

    assert isinstance(transcriber, transcription.FasterWhisperTranscriber)


@pytest.mark.unit
def test_get_transcriber_returns_streaming(mock_config):
    """Test that get_transcriber returns StreamingTranscriber when configured."""
    from whisprbar import config

    mock_config["transcription_backend"] = "streaming"
    config.cfg.clear()
    config.cfg.update(mock_config)

    # Reset global transcriber
    transcription._transcriber = None

    transcriber = transcription.get_transcriber()

    assert isinstance(transcriber, transcription.StreamingTranscriber)


@pytest.mark.unit
def test_get_transcriber_caches_instance(mock_config):
    """Test that get_transcriber caches transcriber instance."""
    from whisprbar import config

    mock_config["transcription_backend"] = "openai"
    config.cfg.clear()
    config.cfg.update(mock_config)

    # Reset global transcriber
    transcription._transcriber = None

    transcriber1 = transcription.get_transcriber()
    transcriber2 = transcription.get_transcriber()

    # Should return same instance
    assert transcriber1 is transcriber2


@pytest.mark.unit
def test_get_transcriber_resets_on_backend_change(mock_config):
    """Test that get_transcriber creates new instance when backend changes."""
    from whisprbar import config

    # Start with OpenAI
    mock_config["transcription_backend"] = "openai"
    config.cfg.clear()
    config.cfg.update(mock_config)
    transcription._transcriber = None

    transcriber1 = transcription.get_transcriber()
    assert isinstance(transcriber1, transcription.OpenAITranscriber)

    # Change to faster_whisper
    mock_config["transcription_backend"] = "faster_whisper"
    config.cfg.clear()
    config.cfg.update(mock_config)

    transcriber2 = transcription.get_transcriber()
    assert isinstance(transcriber2, transcription.FasterWhisperTranscriber)

    # Should be different instances
    assert transcriber1 is not transcriber2


@pytest.mark.unit
def test_openai_transcriber_get_name():
    """Test OpenAITranscriber.get_name()."""
    transcriber = transcription.OpenAITranscriber()
    assert transcriber.get_name() == "OpenAI Whisper API"


@pytest.mark.unit
def test_faster_whisper_transcriber_get_name():
    """Test FasterWhisperTranscriber.get_name()."""
    transcriber = transcription.FasterWhisperTranscriber()

    # Without model loaded
    assert "faster-whisper" in transcriber.get_name()

    # With model info
    transcriber.model_size = "tiny"
    transcriber.device = "cpu"
    name = transcriber.get_name()
    assert "tiny" in name
    assert "cpu" in name


@pytest.mark.unit
def test_streaming_transcriber_supports_streaming():
    """Test that StreamingTranscriber.supports_streaming() returns True."""
    transcriber = transcription.StreamingTranscriber()
    assert transcriber.supports_streaming() is True
