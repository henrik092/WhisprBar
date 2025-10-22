#!/usr/bin/env python3
"""Detailed test for BUG #2."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from whisprbar import config, transcription

print("Initial state:")
print(f"  config.cfg id: {id(config.cfg)}")
print(f"  transcription.cfg id: {id(transcription.cfg)}")
print(f"  Are they the same object? {config.cfg is transcription.cfg}")

print("\nTest: Setting backend to 'faster_whisper'")
config.cfg['transcription_backend'] = 'faster_whisper'
print(f"  config.cfg['transcription_backend']: {config.cfg.get('transcription_backend')}")
print(f"  transcription.cfg['transcription_backend']: {transcription.cfg.get('transcription_backend')}")

transcription._transcriber = None
t = transcription.get_transcriber()
print(f"  Result: {type(t).__name__}")

print("\nInside get_transcriber, what does it see?")
backend_value = transcription.cfg.get("transcription_backend", "openai")
print(f"  Backend from transcription.cfg.get(): '{backend_value}'")
