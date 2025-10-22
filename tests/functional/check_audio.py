#!/usr/bin/env python3
"""
check_audio.py - Verify audio device detection and recording capability

This script checks:
1. sounddevice can list input devices
2. At least one input device is available
3. Default device configuration
4. Test recording capability (optional)
"""

import sys
from typing import List, Dict


def check_sounddevice() -> bool:
    """Check if sounddevice module is available"""
    try:
        import sounddevice as sd
        return True
    except ImportError:
        print("✗ sounddevice module not installed")
        print("  Install: pip install sounddevice")
        return False


def list_input_devices() -> List[Dict]:
    """List all audio input devices"""
    import sounddevice as sd

    devices = []
    try:
        for idx, dev in enumerate(sd.query_devices()):
            # Only include devices with input channels
            if dev["max_input_channels"] > 0:
                devices.append({
                    "index": idx,
                    "name": dev["name"],
                    "channels": dev["max_input_channels"],
                    "sample_rate": dev["default_samplerate"],
                    "is_default": idx == sd.default.device[0],
                })
    except Exception as e:
        print(f"✗ Failed to query devices: {e}")

    return devices


def test_recording(device_index: int = None, duration: float = 1.0) -> bool:
    """Test recording from device"""
    import sounddevice as sd
    import numpy as np

    try:
        print(f"  Testing recording for {duration}s...")
        audio = sd.rec(
            int(duration * 16000),
            samplerate=16000,
            channels=1,
            device=device_index,
            dtype=np.float32
        )
        sd.wait()

        # Check if audio was captured
        if audio is not None and len(audio) > 0:
            rms = np.sqrt(np.mean(audio ** 2))
            print(f"  ✓ Recording successful (RMS: {rms:.4f})")
            if rms < 0.001:
                print(f"  ⚠ Warning: Very low audio level (check microphone)")
            return True
        else:
            print(f"  ✗ Recording failed: no data captured")
            return False

    except Exception as e:
        print(f"  ✗ Recording failed: {e}")
        return False


def main():
    print("=" * 60)
    print("WhisprBar V6 - Audio Device Check")
    print("=" * 60)
    print()

    # Check sounddevice module
    if not check_sounddevice():
        return 1

    import sounddevice as sd

    # List devices
    print("Available Input Devices")
    print("-" * 60)
    devices = list_input_devices()

    if not devices:
        print("✗ No input devices found")
        print()
        print("Troubleshooting:")
        print("  1. Check microphone is connected")
        print("  2. Check PulseAudio: pactl list sources")
        print("  3. Check ALSA: arecord -l")
        print("  4. Verify user in audio group: groups $USER")
        return 1

    for dev in devices:
        marker = "→" if dev["is_default"] else " "
        print(f"{marker} [{dev['index']}] {dev['name']}")
        print(f"      Channels: {dev['channels']}, Sample Rate: {dev['sample_rate']} Hz")
        if dev["is_default"]:
            print(f"      (System default)")
    print()

    # Show default device
    print("Default Configuration")
    print("-" * 60)
    default_device = next((d for d in devices if d["is_default"]), devices[0] if devices else None)

    if default_device:
        print(f"✓ Default device: [{default_device['index']}] {default_device['name']}")
        print(f"  Channels: {default_device['channels']}")
        print(f"  Sample Rate: {default_device['sample_rate']} Hz")
    else:
        print("⚠ No default device set")
    print()

    # Optional recording test
    print("Recording Test (Optional)")
    print("-" * 60)
    print("This will test recording from the default device.")
    print("Speak into your microphone during the 2-second test.")
    print()

    try:
        response = input("Run recording test? [y/N]: ").strip().lower()
        if response == "y":
            print()
            if default_device:
                success = test_recording(default_device["index"], duration=2.0)
                if success:
                    print("✓ Recording test passed")
                else:
                    print("✗ Recording test failed")
            else:
                print("✗ No device to test")
            print()
        else:
            print("Skipped recording test")
            print()
    except (EOFError, KeyboardInterrupt):
        print("\nSkipped recording test")
        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Input Devices Found: {len(devices)}")
    print(f"Default Device: {default_device['name'] if default_device else 'None'}")
    print()

    if devices:
        print("✓ Audio devices are configured correctly")
        print("  WhisprBar should be able to record audio.")
        return 0
    else:
        print("✗ No audio input devices available")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
