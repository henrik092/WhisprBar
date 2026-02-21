#!/usr/bin/env python3
"""Test unicode capitalization fix."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from whisprbar.transcription import postprocess_fix_capitalization

# Test cases: (language, input, expected_output)
test_cases = [
    ("de", "das ist ein test. über dem berg. äpfel sind gut.",
     "Das ist ein test. Über dem berg. Äpfel sind gut."),
    ("de", "ich mag öl. österreich ist schön.",
     "Ich mag öl. Österreich ist schön."),
    ("fr", "bonjour. état est important. école fermée.",
     "Bonjour. État est important. École fermée."),
    ("es", "hola. ñoño come ñoquis.",
     "Hola. Ñoño come ñoquis."),
    ("en", "hello world. this is a test.",
     "Hello world. This is a test."),
    ("en", "i am good. i'm happy.",
     "I am good. I'm happy."),
]

print("=" * 60)
print("Unicode Capitalization Test")
print("=" * 60)

passed = 0
failed = 0

for lang, input_text, expected in test_cases:
    result = postprocess_fix_capitalization(input_text, lang)

    if result == expected:
        status = "✅ PASS"
        passed += 1
    else:
        status = "❌ FAIL"
        failed += 1

    print(f"\n{status} [{lang}]")
    if result != expected:
        print(f"  Input:    {input_text}")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")

print("\n" + "=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
