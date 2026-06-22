"""Unit tests for whisprbar.transcription module."""

import base64
import sys
from types import SimpleNamespace
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


@pytest.mark.unit
def test_transcriber_start_streaming_default_none():
    """Batch-only backends should opt out of live streaming by default."""

    class DummyTranscriber(transcription.Transcriber):
        def transcribe(self, audio, language="de"):
            return None

        def get_name(self):
            return "Dummy"

    transcriber = DummyTranscriber()

    assert transcriber.start_streaming("de") is None


@pytest.mark.unit
def test_elevenlabs_start_streaming_creates_live_session(monkeypatch):
    """ElevenLabs should expose a live session without doing batch transcription."""
    from whisprbar.transcription import elevenlabs as elevenlabs_module

    created = {}

    class FakeSession:
        def __init__(self, client, language):
            created["client"] = client
            created["language"] = language

    client = object()
    transcriber = transcription.ElevenLabsTranscriber()
    transcriber.client = client
    monkeypatch.setattr(transcriber, "ensure_client", lambda: True)
    monkeypatch.setattr(elevenlabs_module, "ElevenLabsRealtimeSession", FakeSession)

    session = transcriber.start_streaming("en")

    assert isinstance(session, FakeSession)
    assert created == {"client": client, "language": "en"}


@pytest.mark.unit
def test_elevenlabs_audio_chunk_to_base64_encodes_pcm16():
    """Realtime audio chunks should be clipped and encoded as PCM16."""
    from whisprbar.transcription.elevenlabs import _audio_chunk_to_base64

    encoded = _audio_chunk_to_base64(
        np.array([-1.0, 0.0, 0.5, 1.0, 2.0], dtype=np.float32)
    )

    pcm16 = np.frombuffer(base64.b64decode(encoded), dtype=np.int16)
    assert pcm16.tolist() == [-32767, 0, 16383, 32767, 32767]


@pytest.mark.unit
def test_elevenlabs_realtime_session_sends_chunks_and_commits(monkeypatch):
    """Live sessions should send pushed audio before committing on finish."""
    from whisprbar.transcription.elevenlabs import ElevenLabsRealtimeSession

    sent_payloads = []
    committed = []
    closed = []

    class FakeRealtimeAudioOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeConnection:
        def __init__(self):
            self.handlers = {}

        def on(self, event, callback):
            self.handlers[event] = callback

        async def send(self, payload):
            sent_payloads.append(payload)

        async def commit(self):
            committed.append(True)
            self.handlers["committed"]({"text": "hello live"})

        async def close(self):
            closed.append(True)

    connection = FakeConnection()

    class FakeRealtime:
        async def connect(self, _options):
            return connection

    client = SimpleNamespace(
        speech_to_text=SimpleNamespace(realtime=FakeRealtime())
    )
    fake_elevenlabs = SimpleNamespace(
        AudioFormat=SimpleNamespace(PCM_16000="pcm_16000"),
        CommitStrategy=SimpleNamespace(MANUAL="manual"),
        RealtimeAudioOptions=FakeRealtimeAudioOptions,
        RealtimeEvents=SimpleNamespace(COMMITTED_TRANSCRIPT="committed"),
    )
    monkeypatch.setitem(sys.modules, "elevenlabs", fake_elevenlabs)

    session = ElevenLabsRealtimeSession(client, "en")
    session.push_audio(np.array([0.1, 0.2], dtype=np.float32))

    assert session.finish() == "hello live"
    assert sent_payloads
    assert sent_payloads[0]["sample_rate"] == 16000
    assert sent_payloads[0]["audio_base_64"]
    assert committed == [True]
    assert closed == [True]


@pytest.mark.unit
def test_elevenlabs_realtime_session_discards_partial_text_after_queue_overflow(monkeypatch):
    """Dropped live audio chunks must force batch fallback instead of returning partial text."""
    from whisprbar.transcription.elevenlabs import ElevenLabsRealtimeSession

    monkeypatch.setattr(ElevenLabsRealtimeSession, "_run_thread", lambda self: None)
    session = ElevenLabsRealtimeSession(object(), "en")
    session._result_parts.append("partial live text")

    while not session._audio_queue.full():
        session._audio_queue.put_nowait(np.ones(1, dtype=np.float32))

    session.push_audio(np.ones(1, dtype=np.float32))

    assert session.finish() is None
