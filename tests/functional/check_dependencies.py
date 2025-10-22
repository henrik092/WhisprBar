#!/usr/bin/env python3
"""
check_dependencies.py - Verify all WhisprBar dependencies are installed

This script checks for:
1. Python version
2. System dependencies (GTK, AppIndicator, xdotool, etc.)
3. Python packages (from requirements.txt)
4. Optional dependencies
"""

import sys
import subprocess
import importlib
from pathlib import Path
from typing import List, Tuple


def check_python_version() -> Tuple[bool, str]:
    """Check Python version is 3.10+"""
    version = sys.version_info
    if version >= (3, 10):
        return True, f"✓ Python {version.major}.{version.minor}.{version.micro}"
    else:
        return False, f"✗ Python {version.major}.{version.minor}.{version.micro} (need 3.10+)"


def check_system_command(cmd: str) -> Tuple[bool, str]:
    """Check if a system command is available"""
    try:
        result = subprocess.run(
            ["which", cmd],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, f"✓ {cmd} found"
        else:
            return False, f"✗ {cmd} not found"
    except Exception as e:
        return False, f"✗ {cmd} check failed: {e}"


def check_python_package(package: str, import_name: str = None) -> Tuple[bool, str]:
    """Check if a Python package is installed"""
    if import_name is None:
        import_name = package.replace("-", "_")

    try:
        importlib.import_module(import_name)
        return True, f"✓ {package} installed"
    except ImportError:
        return False, f"✗ {package} not installed"


def check_gi_module(module: str, version: str = None) -> Tuple[bool, str]:
    """Check if a GObject Introspection module is available"""
    try:
        import gi
        if version:
            gi.require_version(module, version)
        gi.repository.__import__(module)
        version_str = f" {version}" if version else ""
        return True, f"✓ GI: {module}{version_str}"
    except (ImportError, ValueError) as e:
        version_str = f" {version}" if version else ""
        return False, f"✗ GI: {module}{version_str} - {e}"


def main():
    print("=" * 60)
    print("WhisprBar V6 - Dependency Check")
    print("=" * 60)
    print()

    results: List[Tuple[bool, str]] = []

    # Python version
    print("Python Environment")
    print("-" * 60)
    result = check_python_version()
    results.append(result)
    print(result[1])
    print()

    # System commands
    print("System Commands")
    print("-" * 60)
    system_commands = [
        ("xdotool", "X11 auto-paste support"),
        ("notify-send", "Desktop notifications"),
        ("arecord", "Audio recording test"),
    ]

    for cmd, description in system_commands:
        result = check_system_command(cmd)
        results.append(result)
        print(f"{result[1]:<40} ({description})")
    print()

    # Python packages (required)
    print("Required Python Packages")
    print("-" * 60)
    required_packages = [
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("pystray", "pystray"),
        ("Pillow", "PIL"),
        ("pyperclip", "pyperclip"),
        ("openai", "openai"),
        ("pynput", "pynput"),
    ]

    for package, import_name in required_packages:
        result = check_python_package(package, import_name)
        results.append(result)
        print(result[1])
    print()

    # Python packages (optional but recommended)
    print("Optional Python Packages")
    print("-" * 60)
    optional_packages = [
        ("webrtcvad", "webrtcvad", "Voice Activity Detection"),
        ("noisereduce", "noisereduce", "Noise reduction"),
        ("faster-whisper", "faster_whisper", "Local transcription"),
        ("sherpa-onnx", "sherpa_onnx", "Streaming transcription"),
    ]

    for package, import_name, description in optional_packages:
        result = check_python_package(package, import_name)
        status = "✓" if result[0] else "○"
        print(f"{status} {package:<20} ({description})")
    print()

    # GObject Introspection modules
    print("GTK / GObject Introspection")
    print("-" * 60)
    gi_modules = [
        ("Gtk", "3.0", "GTK 3.0 (UI framework)"),
        ("Gdk", "3.0", "GDK 3.0 (drawing)"),
        ("GLib", "2.0", "GLib 2.0 (utilities)"),
        ("AppIndicator3", "0.1", "AppIndicator (tray icon)"),
    ]

    for module, version, description in gi_modules:
        result = check_gi_module(module, version)
        results.append(result)
        status = "✓" if result[0] else "✗"
        print(f"{status} {module} {version:<10} ({description})")
    print()

    # Test packages (for development)
    print("Testing Packages")
    print("-" * 60)
    test_packages = [
        ("pytest", "pytest"),
        ("pytest-cov", "pytest_cov"),
        ("pytest-mock", "pytest_mock"),
    ]

    for package, import_name in test_packages:
        result = check_python_package(package, import_name)
        status = "✓" if result[0] else "○"
        print(f"{status} {package}")
    print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    passed = sum(1 for ok, _ in results if ok)
    failed = len(results) - passed

    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")
    print()

    if failed == 0:
        print("✓ All required dependencies are installed!")
        print("  WhisprBar should work correctly.")
        return 0
    else:
        print("✗ Some dependencies are missing.")
        print()
        print("To install missing dependencies:")
        print()
        print("System packages (Ubuntu/Debian):")
        print("  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \\")
        print("                   gir1.2-appindicator3-0.1 xdotool libnotify-bin \\")
        print("                   portaudio19-dev")
        print()
        print("Python packages:")
        print("  pip install -r requirements.txt")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
