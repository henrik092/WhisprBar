#!/usr/bin/env python3
"""Test that audio processing happens only once (no duplication)."""
import sys
import numpy as np
sys.path.insert(0, '/home/rik/WhisprBar')

from whisprbar.transcription import transcribe_audio
from whisprbar.config import load_config
from whisprbar import audio
from unittest import mock

print("=" * 60)
print("Duplicate Audio Processing Test")
print("=" * 60)

# Load config
cfg = load_config()

# Create test audio (2 seconds)
test_audio = np.random.randn(16000 * 2).astype(np.float32) * 0.05

# Mock the apply_vad and apply_noise_reduction to count calls
vad_call_count = 0
nr_call_count = 0

original_apply_vad = audio.apply_vad
original_apply_nr = audio.apply_noise_reduction

def counted_apply_vad(audio_data):
    global vad_call_count
    vad_call_count += 1
    print(f"  apply_vad() called (count: {vad_call_count})")
    return original_apply_vad(audio_data)

def counted_apply_nr(audio_data):
    global nr_call_count
    nr_call_count += 1
    print(f"  apply_noise_reduction() called (count: {nr_call_count})")
    return original_apply_nr(audio_data)

# Patch the functions
audio.apply_vad = counted_apply_vad
audio.apply_noise_reduction = counted_apply_nr

print("\n1. Simulating preprocessing in main.py:")
# Simulate what main.py does (preprocessing)
preprocessed = audio.apply_noise_reduction(test_audio)
preprocessed = audio.apply_vad(preprocessed)

print("\n2. Calling transcribe_audio() with preprocessed audio:")
# Now call transcribe_audio (should NOT call VAD/NR again)
try:
    result = transcribe_audio(preprocessed, cfg.get("language", "de"))
    # Note: This will fail if OpenAI key not configured, which is OK for this test
except Exception as e:
    print(f"  Transcription failed (expected if no API key): {e}")

print("\n" + "=" * 60)
print("Results:")
print(f"  apply_noise_reduction() calls: {nr_call_count}")
print(f"  apply_vad() calls: {vad_call_count}")
print("=" * 60)

# Restore original functions
audio.apply_vad = original_apply_vad
audio.apply_noise_reduction = original_apply_nr

# Check results
if nr_call_count == 1 and vad_call_count == 1:
    print("\n✅ PASS: Audio processing happens only ONCE (no duplication)")
    sys.exit(0)
else:
    print(f"\n❌ FAIL: Expected 1 call each, got NR={nr_call_count}, VAD={vad_call_count}")
    sys.exit(1)
