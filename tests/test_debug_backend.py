#!/usr/bin/env python3
"""Debug script for backend selection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from whisprbar import config, transcription

# Enable debug output
import os
os.environ['WHISPRBAR_DEBUG'] = '1'

# Test backend switching
config.cfg['transcription_backend'] = 'openai'
transcription._transcriber = None

print("=" * 60)
print("TEST 1: Setting backend to 'openai'")
print(f"Config backend: {config.cfg['transcription_backend']}")
t1 = transcription.get_transcriber()
print(f"Transcriber type: {type(t1).__name__}")
print(f"Global _transcriber: {type(transcription._transcriber).__name__ if transcription._transcriber else None}")

print("\n" + "=" * 60)
print("TEST 2: Setting backend to 'faster_whisper' (without reset)")
config.cfg['transcription_backend'] = 'faster_whisper'
print(f"Config backend: {config.cfg['transcription_backend']}")
print(f"Before get_transcriber - _transcriber type: {type(transcription._transcriber).__name__}")

# Add manual debug
backend = config.cfg.get("transcription_backend", "openai")
print(f"Backend from config.get(): '{backend}'")

if transcription._transcriber is not None:
    current_backend = (
        "openai"
        if isinstance(transcription._transcriber, transcription.OpenAITranscriber)
        else "faster_whisper"
        if isinstance(transcription._transcriber, transcription.FasterWhisperTranscriber)
        else "streaming"
        if isinstance(transcription._transcriber, transcription.StreamingTranscriber)
        else "unknown"
    )
    print(f"Current backend from isinstance: '{current_backend}'")
    print(f"Backend != current_backend: {backend != current_backend}")

t2 = transcription.get_transcriber()
print(f"After get_transcriber - Transcriber type: {type(t2).__name__}")
print(f"After get_transcriber - _transcriber type: {type(transcription._transcriber).__name__}")

print("\n" + "=" * 60)
print("TEST 3: Manual reset and try again")
transcription._transcriber = None
config.cfg['transcription_backend'] = 'streaming'
print(f"Config backend: {config.cfg['transcription_backend']}")
t3 = transcription.get_transcriber()
print(f"Transcriber type: {type(t3).__name__}")
