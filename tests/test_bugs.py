#!/usr/bin/env python3
"""Test script to verify the three critical bugs."""

import sys
import json
from pathlib import Path

# Add whisprbar to path
sys.path.insert(0, str(Path(__file__).parent))

from whisprbar import config, transcription
import numpy as np


def test_bug1_config_migration():
    """Test BUG #1: Config migration from legacy hotkey."""
    print("\n=== Testing BUG #1: Config Migration ===")

    # Simulate old config with legacy hotkey
    old_config = {
        "language": "de",
        "hotkey": "F9",  # Legacy single hotkey
        "transcription_backend": "openai"
    }

    # Save old config
    config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.CONFIG_PATH.open("w") as f:
        json.dump(old_config, f)

    # Load config (should trigger migration)
    config.reset_config()  # Reset without breaking references
    config.load_config()

    print(f"Legacy hotkey: {config.cfg.get('hotkey')}")
    print(f"New hotkeys dict: {config.cfg.get('hotkeys')}")
    print(f"toggle_recording: {config.cfg.get('hotkeys', {}).get('toggle_recording')}")

    # Verify migration
    if config.cfg.get('hotkeys', {}).get('toggle_recording') == 'F9':
        print("✓ BUG #1: Migration appears correct")
        return True
    else:
        print("✗ BUG #1: Migration FAILED - toggle_recording not set to F9")
        return False


def test_bug2_backend_selection():
    """Test BUG #2: Backend selection."""
    print("\n=== Testing BUG #2: Backend Selection ===")

    # Test 1: OpenAI backend
    config.cfg['transcription_backend'] = 'openai'
    transcription._transcriber = None  # Reset cache
    t = transcription.get_transcriber()
    print(f"Backend 'openai' → {type(t).__name__}")
    if not isinstance(t, transcription.OpenAITranscriber):
        print("✗ BUG #2: OpenAI backend FAILED")
        return False

    # Test 2: faster-whisper backend
    config.cfg['transcription_backend'] = 'faster_whisper'
    transcription._transcriber = None  # Reset cache
    t = transcription.get_transcriber()
    print(f"Backend 'faster_whisper' → {type(t).__name__}")
    if not isinstance(t, transcription.FasterWhisperTranscriber):
        print("✗ BUG #2: FasterWhisper backend FAILED")
        return False

    # Test 3: streaming backend
    config.cfg['transcription_backend'] = 'streaming'
    transcription._transcriber = None  # Reset cache
    t = transcription.get_transcriber()
    print(f"Backend 'streaming' → {type(t).__name__}")
    if not isinstance(t, transcription.StreamingTranscriber):
        print("✗ BUG #2: Streaming backend FAILED")
        return False

    # Test 4: invalid backend (should default to openai)
    config.cfg['transcription_backend'] = 'invalid_backend'
    transcription._transcriber = None  # Reset cache
    t = transcription.get_transcriber()
    print(f"Backend 'invalid_backend' → {type(t).__name__}")
    if not isinstance(t, transcription.OpenAITranscriber):
        print("✗ BUG #2: Invalid backend fallback FAILED")
        return False

    print("✓ BUG #2: All backend selections correct")
    return True


def test_bug3_postprocessing_flag():
    """Test BUG #3: Postprocessing flag ignored."""
    print("\n=== Testing BUG #3: Postprocessing Flag ===")

    # Test text with spacing and capitalization issues
    test_text = "hello world .  this is a test  sentence. another one here  ."

    # Test 1: postprocessing enabled
    config.cfg['postprocess_enabled'] = True
    config.cfg['postprocess_fix_spacing'] = True
    config.cfg['postprocess_fix_capitalization'] = True
    result_enabled = transcription.postprocess_transcript(test_text, "en")
    print(f"Input:  '{test_text}'")
    print(f"Enabled: '{result_enabled}'")

    # Test 2: postprocessing disabled
    config.cfg['postprocess_enabled'] = False
    result_disabled = transcription.postprocess_transcript(test_text, "en")
    print(f"Disabled: '{result_disabled}'")

    # Verify that disabled returns unchanged text
    if result_disabled == test_text:
        print("✓ BUG #3: Postprocessing flag respected")
        return True
    else:
        print("✗ BUG #3: Postprocessing flag IGNORED - text was modified when disabled")
        print(f"  Expected: '{test_text}'")
        print(f"  Got:      '{result_disabled}'")
        return False


def main():
    """Run all bug tests."""
    print("WhisprBar V6 - Critical Bug Tests")
    print("=" * 50)

    results = []

    try:
        results.append(("BUG #1", test_bug1_config_migration()))
    except Exception as e:
        print(f"✗ BUG #1: Exception - {e}")
        import traceback
        traceback.print_exc()
        results.append(("BUG #1", False))

    try:
        results.append(("BUG #2", test_bug2_backend_selection()))
    except Exception as e:
        print(f"✗ BUG #2: Exception - {e}")
        import traceback
        traceback.print_exc()
        results.append(("BUG #2", False))

    try:
        results.append(("BUG #3", test_bug3_postprocessing_flag()))
    except Exception as e:
        print(f"✗ BUG #3: Exception - {e}")
        import traceback
        traceback.print_exc()
        results.append(("BUG #3", False))

    print("\n" + "=" * 50)
    print("SUMMARY:")
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"  {name}: {status}")

    all_passed = all(passed for _, passed in results)
    print("\n" + ("All tests PASSED ✓" if all_passed else "Some tests FAILED ✗"))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
