#!/usr/bin/env python3
"""Test cfg reference issue."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from whisprbar import config, transcription

print("Before reassignment:")
print(f"  config.cfg is transcription.cfg: {config.cfg is transcription.cfg}")
print(f"  config.cfg id: {id(config.cfg)}")
print(f"  transcription.cfg id: {id(transcription.cfg)}")

print("\nReassigning config.cfg (simulating test_bug1):")
config.cfg = config.DEFAULT_CFG.copy()

print(f"  config.cfg is transcription.cfg: {config.cfg is transcription.cfg}")
print(f"  config.cfg id: {id(config.cfg)}")
print(f"  transcription.cfg id: {id(transcription.cfg)}")

print("\nSetting backend in config.cfg:")
config.cfg['transcription_backend'] = 'faster_whisper'
print(f"  config.cfg['transcription_backend']: {config.cfg.get('transcription_backend')}")
print(f"  transcription.cfg['transcription_backend']: {transcription.cfg.get('transcription_backend')}")

print("\nThis is the bug! transcription module still sees old cfg object!")
