#!/usr/bin/env python3
"""
check_api_key.py - Verify OpenAI API key configuration and validity

This script checks:
1. API key exists in environment file
2. API key format is valid
3. API key can authenticate with OpenAI (optional)
"""

import sys
import os
from pathlib import Path


ENV_FILE_PATH = Path.home() / ".config" / "whisprbar.env"


def load_env_file() -> dict:
    """Load environment variables from .env file"""
    env_vars = {}

    if not ENV_FILE_PATH.exists():
        return env_vars

    try:
        with ENV_FILE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as e:
        print(f"✗ Failed to read {ENV_FILE_PATH}: {e}")

    return env_vars


def check_api_key_format(api_key: str) -> tuple[bool, str]:
    """Check if API key has valid format"""
    if not api_key:
        return False, "API key is empty"

    # OpenAI API keys typically start with "sk-" and are 51+ characters
    if not api_key.startswith("sk-"):
        return False, "API key should start with 'sk-'"

    if len(api_key) < 20:
        return False, f"API key too short ({len(api_key)} chars, expected 40+)"

    return True, f"API key format valid ({len(api_key)} chars)"


def test_api_key(api_key: str) -> tuple[bool, str]:
    """Test API key by making a simple API call"""
    try:
        from openai import OpenAI
    except ImportError:
        return False, "openai package not installed (pip install openai)"

    try:
        client = OpenAI(api_key=api_key)

        # Try to list models as a simple API test
        models = client.models.list()

        return True, f"✓ API key valid (authenticated successfully)"

    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg:
            return False, "API key is invalid (401 Unauthorized)"
        elif "429" in error_msg or "Rate limit" in error_msg:
            return False, "Rate limit exceeded (but key is valid)"
        elif "timeout" in error_msg.lower():
            return False, "API request timed out (check internet connection)"
        else:
            return False, f"API test failed: {error_msg[:100]}"


def main():
    print("=" * 60)
    print("WhisprBar V6 - API Key Check")
    print("=" * 60)
    print()

    # Check env file exists
    print("Environment File")
    print("-" * 60)
    if not ENV_FILE_PATH.exists():
        print(f"✗ Environment file not found: {ENV_FILE_PATH}")
        print()
        print("To create environment file:")
        print(f"  echo 'OPENAI_API_KEY=your-api-key-here' > {ENV_FILE_PATH}")
        print(f"  chmod 600 {ENV_FILE_PATH}")
        print()
        print("Get API key from: https://platform.openai.com/api-keys")
        return 1

    print(f"✓ Environment file found: {ENV_FILE_PATH}")
    print()

    # Load environment variables
    print("Environment Variables")
    print("-" * 60)
    env_vars = load_env_file()

    if "OPENAI_API_KEY" not in env_vars:
        print("✗ OPENAI_API_KEY not found in environment file")
        print()
        print("Add to environment file:")
        print(f"  echo 'OPENAI_API_KEY=your-api-key-here' >> {ENV_FILE_PATH}")
        return 1

    api_key = env_vars["OPENAI_API_KEY"]
    masked_key = api_key[:7] + "..." + api_key[-4:] if len(api_key) > 11 else "***"
    print(f"✓ OPENAI_API_KEY found: {masked_key}")
    print()

    # Check API key format
    print("API Key Format")
    print("-" * 60)
    valid, msg = check_api_key_format(api_key)
    if valid:
        print(f"✓ {msg}")
    else:
        print(f"✗ {msg}")
        print()
        print("OpenAI API keys should:")
        print("  - Start with 'sk-'")
        print("  - Be at least 40 characters long")
        print()
        print("Get a valid key from: https://platform.openai.com/api-keys")
        return 1
    print()

    # File permissions check
    print("File Permissions")
    print("-" * 60)
    import stat
    mode = ENV_FILE_PATH.stat().st_mode
    perms = stat.filemode(mode)

    # Check if file is readable only by owner (600 or stricter)
    if mode & 0o077 == 0:  # No group/other permissions
        print(f"✓ {ENV_FILE_PATH.name}: {perms} (secure)")
    else:
        print(f"⚠ {ENV_FILE_PATH.name}: {perms} (should be 600)")
        print(f"  Run: chmod 600 {ENV_FILE_PATH}")
    print()

    # Optional API test
    print("API Authentication Test (Optional)")
    print("-" * 60)
    print("This will make a test API call to verify the key works.")
    print("Requires internet connection and may use minimal API credits.")
    print()

    try:
        response = input("Test API key authentication? [y/N]: ").strip().lower()
        if response == "y":
            print()
            print("Testing API key...")
            valid, msg = test_api_key(api_key)
            print(msg)
            if not valid:
                print()
                print("Troubleshooting:")
                print("  1. Verify key at: https://platform.openai.com/api-keys")
                print("  2. Check account has available credits")
                print("  3. Ensure internet connection works")
                return 1
            print()
        else:
            print("Skipped API authentication test")
            print()
    except (EOFError, KeyboardInterrupt):
        print("\nSkipped API authentication test")
        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print("✓ API key is configured correctly")
    print("  WhisprBar should be able to use OpenAI transcription.")
    print()
    print("Note: To use offline transcription (no API key needed):")
    print("  1. Open Settings → Transcription Backend")
    print("  2. Select 'faster-whisper' or 'sherpa-onnx'")
    print("  3. Install: pip install faster-whisper sherpa-onnx")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
