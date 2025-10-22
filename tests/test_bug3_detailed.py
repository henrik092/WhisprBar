#!/usr/bin/env python3
"""Detailed test for BUG #3."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from whisprbar import config, transcription

test_text = "hello world"

print("Initial state:")
print(f"  config.cfg['postprocess_enabled']: {config.cfg.get('postprocess_enabled')}")
print(f"  transcription.cfg['postprocess_enabled']: {transcription.cfg.get('postprocess_enabled')}")

print("\nSetting postprocess_enabled to False in config.cfg:")
config.cfg['postprocess_enabled'] = False
print(f"  config.cfg['postprocess_enabled']: {config.cfg.get('postprocess_enabled')}")
print(f"  transcription.cfg['postprocess_enabled']: {transcription.cfg.get('postprocess_enabled')}")

print("\nCalling postprocess_transcript:")
result = transcription.postprocess_transcript(test_text, "en")
print(f"  Input:  '{test_text}'")
print(f"  Output: '{result}'")
print(f"  Changed: {result != test_text}")
