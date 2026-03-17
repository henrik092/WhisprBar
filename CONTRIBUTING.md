# Contributing to WhisprBar

Thank you for your interest in contributing to WhisprBar! This guide will help you get started with development, understand our code standards, and successfully contribute to the project.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Environment](#development-environment)
3. [Code Style Guidelines](#code-style-guidelines)
4. [Architecture Overview](#architecture-overview)
5. [Making Changes](#making-changes)
6. [Testing](#testing)
7. [Pull Request Process](#pull-request-process)
8. [Reporting Bugs](#reporting-bugs)
9. [Suggesting Features](#suggesting-features)
10. [Community Guidelines](#community-guidelines)

---

## Getting Started

### Prerequisites

- **Git**: Version control
- **Python 3.8+**: Programming language
- **Linux**: WhisprBar is Linux-only
- **GTK 3.0**: GUI framework
- **Basic Knowledge**: Python, Linux system programming

### First Steps

1. **Fork the Repository**
   ```bash
   # Fork on GitHub, then clone your fork
   git clone https://github.com/YOUR_USERNAME/whisprBar.git
   cd whisprBar
   ```

2. **Set Up Upstream Remote**
   ```bash
   git remote add upstream https://github.com/henrik092/whisprBar.git
   git fetch upstream
   ```

3. **Create a Development Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## Development Environment

### System Dependencies

**Ubuntu/Debian**:
```bash
sudo apt install python3 python3-venv python3-pip \
                 python3-gi python3-gi-cairo \
                 gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
                 xdotool libnotify-bin portaudio19-dev \
                 git
```

**Fedora**:
```bash
sudo dnf install python3 python3-pip python3-gobject \
                 gtk3 libappindicator-gtk3 xdotool \
                 libnotify portaudio-devel git
```

**Arch Linux**:
```bash
sudo pacman -S python python-pip python-gobject \
               gtk3 libappindicator-gtk3 xdotool \
               libnotify portaudio git
```

### Python Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development tools
pip install pylint black mypy pytest pytest-cov
```

### Running from Source

```bash
# Run application
.venv/bin/python whisprbar.py

# Run with debug logging
WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py

# Run diagnostics
.venv/bin/python whisprbar.py --diagnose

# Check version
.venv/bin/python whisprbar.py --version
```

### Development Tools

**Recommended IDE**: VS Code, PyCharm, or vim/emacs with Python extensions

**Useful VS Code Extensions**:
- Python (Microsoft)
- Pylance
- GitLens
- Better Comments

---

## Code Style Guidelines

WhisprBar follows **PEP 8** with some project-specific conventions.

### General Principles

- **Readability First**: Code is read more than written
- **Clear Intent**: Variable and function names should be self-documenting
- **Minimal Complexity**: Keep functions focused and simple
- **Document Complex Logic**: Add comments for non-obvious behavior

### Python Style (PEP 8)

#### Naming Conventions

```python
# Module names: lowercase with underscores
# whisprbar/audio.py

# Constants: UPPERCASE with underscores
SAMPLE_RATE = 16000
DEFAULT_LANGUAGE = "en"

# Variables and functions: lowercase with underscores
def transcribe_audio(audio_data, cfg):
    recording_duration = calculate_duration(audio_data)
    return result

# Classes: PascalCase
class OpenAITranscriber:
    pass

# Private/internal: leading underscore
def _internal_helper():
    pass

_module_state = {}
```

#### Formatting

```python
# Line length: 100 characters (flexible for readability)
def long_function_name(
    parameter_one,
    parameter_two,
    parameter_three
):
    pass

# Indentation: 4 spaces (never tabs)
if condition:
    do_something()
    do_another_thing()

# Blank lines
# - 2 blank lines between top-level definitions
# - 1 blank line between method definitions
# - 1 blank line to separate logical sections

# Imports: grouped and ordered
import sys           # stdlib first
import signal

import numpy as np   # third-party second
from gi.repository import Gtk

from whisprbar.config import load_config  # local third
from whisprbar.utils import debug
```

#### Type Hints

```python
# Use type hints on public functions
def transcribe_audio(audio: np.ndarray, cfg: dict) -> str:
    """Transcribe audio data."""
    pass

# Optional for private functions
def _helper(data):
    pass

# Use typing module for complex types
from typing import List, Dict, Optional, Callable

def process_chunks(
    chunks: List[np.ndarray],
    callback: Callable[[str], None]
) -> Dict[str, str]:
    pass
```

#### Docstrings

```python
# Module docstring at top of file
"""
whisprbar/audio.py - Audio capture and processing

This module handles all audio-related functionality including recording,
voice activity detection, and noise reduction.
"""

# Function docstrings: Google or NumPy style
def transcribe_audio(audio: np.ndarray, cfg: dict) -> str:
    """
    Transcribe audio data using configured backend.

    Args:
        audio: Audio data as numpy array (float32, mono, 16kHz)
        cfg: Configuration dictionary with transcription settings

    Returns:
        Transcribed text string, empty string if transcription fails

    Raises:
        ValueError: If audio data is invalid
        RuntimeError: If transcription backend unavailable
    """
    pass

# Class docstrings
class OpenAITranscriber:
    """
    OpenAI Whisper API transcription backend.

    This transcriber uses the OpenAI API for cloud-based transcription.
    Requires OPENAI_API_KEY environment variable.

    Attributes:
        client: OpenAI client instance
        model: Model name (default: "whisper-1")
    """
    pass
```

### Module Organization

```python
#!/usr/bin/env python3
"""
Module docstring here.
"""

# Standard library imports
import sys
import os

# Third-party imports
import numpy as np
from gi.repository import Gtk

# Local imports
from whisprbar.config import load_config
from whisprbar.utils import debug

# Constants
SAMPLE_RATE = 16000
CHANNELS = 1

# Module-level variables
_transcriber_cache = {}

# Classes
class MyClass:
    pass

# Functions
def public_function():
    pass

def _private_function():
    pass

# Main entry point (if applicable)
if __name__ == "__main__":
    main()
```

### Comments

```python
# Good comments explain WHY, not WHAT

# Bad: Sets x to 5
x = 5

# Good: Use 5-second timeout to prevent hanging
timeout_seconds = 5

# Use inline comments sparingly
result = calculate()  # Only when truly needed

# Multi-line comments for complex logic
# This algorithm uses a sliding window approach to detect
# voice activity by analyzing energy ratios across frames.
# See: https://webrtc.org/architecture/#voice-activity-detection
def detect_voice_activity(audio):
    pass
```

### Error Handling

```python
# Specific exceptions
try:
    result = transcribe_audio(data)
except ValueError as exc:
    debug(f"Invalid audio data: {exc}")
    return ""
except RuntimeError as exc:
    debug(f"Transcription failed: {exc}")
    notify("Transcription error")
    return ""

# Graceful degradation
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    debug("WebRTC VAD not available, VAD disabled")
    VAD_AVAILABLE = False

# User-friendly error messages
if not api_key:
    notify("OpenAI API key not configured. Please edit ~/.config/whisprbar.env")
    return False
```

---

## Architecture Overview

WhisprBar V6 uses a modular architecture with 11 focused modules. Understanding the structure is essential for contributing.

### Module Hierarchy

```
main.py (orchestrator)
  ├── config.py (no dependencies)
  ├── utils.py → config.py
  ├── audio.py → config.py, utils.py
  ├── transcription.py → config.py, utils.py, audio.py
  ├── hotkeys.py → config.py, utils.py
  ├── paste.py → config.py, utils.py
  ├── ui.py → config.py, utils.py, audio.py, hotkeys.py, paste.py
  └── tray.py → config.py, utils.py
```

**Rule**: Dependencies flow downward only. Never create circular dependencies.

### Module Responsibilities

| Module | Responsibility | Max Lines |
|--------|---------------|-----------|
| `config.py` | Configuration load/save/defaults | 300 |
| `utils.py` | Shared utilities (icons, diagnostics, history) | 500 |
| `audio.py` | Audio recording, VAD, noise reduction | 700 |
| `transcription.py` | All transcription backends, postprocessing | 1200 |
| `hotkeys.py` | Global hotkey parsing and listening | 500 |
| `paste.py` | Auto-paste detection and execution | 400 |
| `ui.py` | GUI components (settings, overlay, dialogs) | 1300 |
| `tray.py` | System tray integration (all backends) | 700 |
| `main.py` | Application orchestration, lifecycle | 600 |

**Rule**: Keep modules under their max line count. If exceeding, consider splitting.

### Adding New Features

#### Adding a New Transcription Backend

1. Create new class in `whisprbar/transcription.py`:
   ```python
   class MyBackendTranscriber(Transcriber):
       """My custom transcription backend."""

       def __init__(self, cfg: dict):
           super().__init__(cfg)
           # Initialize your backend

       def transcribe(self, audio: np.ndarray) -> str:
           """Transcribe audio."""
           # Your implementation
           return transcribed_text
   ```

2. Update `get_transcriber()` factory:
   ```python
   def get_transcriber(backend: str, cfg: dict) -> Transcriber:
       if backend == "mybackend":
           return MyBackendTranscriber(cfg)
       # ... existing backends
   ```

3. Add to settings UI in `whisprbar/ui.py`:
   ```python
   # In open_settings_window()
   backend_combo.append_text("mybackend")
   ```

4. Add to config defaults in `whisprbar/config.py`:
   ```python
   DEFAULT_CFG = {
       # ...
       "mybackend_option": "default_value",
   }
   ```

5. Update documentation (CLAUDE.md, README.md)

#### Adding a New Menu Item

1. Add callback function in `whisprbar/main.py`:
   ```python
   def my_menu_action() -> None:
       """Handle my menu action."""
       # Your implementation
   ```

2. Register callback in `get_callbacks()`:
   ```python
   def get_callbacks() -> Dict[str, Any]:
       return {
           # ... existing callbacks
           "my_action": my_menu_action,
       }
   ```

3. Add menu item in `whisprbar/tray.py`:
   ```python
   # In build_menu_data()
   menu_data.append({
       "type": "item",
       "label": "My Action",
       "callback": "my_action"
   })
   ```

---

## Making Changes

### Workflow

1. **Update Your Branch**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make Your Changes**
   - Edit relevant module(s)
   - Follow code style guidelines
   - Add/update docstrings
   - Add/update comments

3. **Test Your Changes**
   ```bash
   # Import test
   .venv/bin/python -c "from whisprbar.mymodule import myfunction"

   # Run application
   .venv/bin/python whisprbar.py

   # Run diagnostics
   .venv/bin/python whisprbar.py --diagnose
   ```

4. **Update Documentation**
   - Update CLAUDE.md if architecture changed
   - Update README.md if user-facing changes
   - Update CHANGELOG.md (Unreleased section)

5. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "feat: add new feature

   - Detailed description of changes
   - Why the change was made
   - Any breaking changes or migrations needed"
   ```

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring (no functional change)
- `docs`: Documentation changes
- `test`: Adding/updating tests
- `chore`: Maintenance tasks (dependencies, etc.)
- `style`: Code style changes (formatting, no logic change)

**Examples**:
```
feat(transcription): add support for Whisper.cpp backend

- Implement WhisperCppTranscriber class
- Add configuration options for model path
- Update settings dialog with new backend option

Closes #42
```

```
fix(audio): prevent VAD from clipping speech at start

The VAD was too aggressive and cut off the first syllable.
Adjusted energy threshold and added 200ms padding.

Fixes #38
```

```
docs: update README with Wayland limitations

Added FAQ section explaining why auto-paste is clipboard-only
on Wayland due to security model restrictions.
```

---

## Testing

### Manual Testing

**After EVERY change**, test at minimum:

1. **Import Test**
   ```bash
   .venv/bin/python -c "from whisprbar import config, audio, transcription"
   ```

2. **Diagnostics**
   ```bash
   .venv/bin/python whisprbar.py --diagnose
   ```

3. **Basic Flow**
   - Start application
   - Press hotkey
   - Record 3-5 seconds of speech
   - Verify transcription appears
   - Verify auto-paste (if enabled)

### Comprehensive Testing

Before submitting a PR, complete the following checklist:

- All recording functions (start, stop, auto-stop)
- All transcription backends (OpenAI, faster-whisper, sherpa)
- All auto-paste modes (X11, Wayland)
- Settings dialog (all options)
- Hotkey capture
- Diagnostics wizard
- Edge cases (no API key, no audio device, etc.)

### Future: Unit Tests

We're working on adding pytest-based unit tests. If you'd like to contribute:

```python
# tests/test_config.py
import pytest
from whisprbar.config import load_config, save_config

def test_load_default_config():
    """Test loading default configuration."""
    cfg = load_config()
    assert "language" in cfg
    assert cfg["use_vad"] is True

def test_save_and_load_config(tmp_path):
    """Test saving and loading configuration."""
    cfg = {"language": "de", "hotkey": "F10"}
    save_config(cfg)
    loaded = load_config()
    assert loaded["language"] == "de"
    assert loaded["hotkey"] == "F10"
```

---

## Pull Request Process

### Before Submitting

- [ ] Code follows style guidelines (PEP 8)
- [ ] All functions have type hints
- [ ] Complex functions have docstrings
- [ ] No circular dependencies introduced
- [ ] Changes tested manually (basic flow works)
- [ ] Comprehensive testing completed (checklist)
- [ ] Documentation updated (CLAUDE.md, README.md, CHANGELOG.md)
- [ ] Commit messages follow conventional format
- [ ] Branch is up-to-date with upstream/main

### Submitting

1. **Push Your Branch**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request**
   - Go to GitHub repository
   - Click "New Pull Request"
   - Select your branch
   - Fill out PR template

3. **PR Template**
   ```markdown
   ## Description
   Brief description of changes

   ## Type of Change
   - [ ] Bug fix (non-breaking change fixing an issue)
   - [ ] New feature (non-breaking change adding functionality)
   - [ ] Breaking change (fix or feature causing existing functionality to change)
   - [ ] Documentation update

   ## Testing
   - [ ] Import test passed
   - [ ] Diagnostics passed
   - [ ] Basic flow tested
   - [ ] Comprehensive testing completed (checklist)
   - [ ] Tested on X11
   - [ ] Tested on Wayland (if applicable)

   ## Documentation
   - [ ] CLAUDE.md updated (if architecture changed)
   - [ ] README.md updated (if user-facing changes)
   - [ ] CHANGELOG.md updated (Unreleased section)
   - [ ] Inline documentation added/updated

   ## Checklist
   - [ ] Code follows PEP 8 style guidelines
   - [ ] Type hints added to public functions
   - [ ] Docstrings added to complex functions
   - [ ] No circular dependencies
   - [ ] No breaking changes (or documented if unavoidable)
   - [ ] Commit messages follow conventional format
   ```

### Review Process

1. **Automated Checks**
   - Code style (pylint, black)
   - Import tests
   - Build tests

2. **Manual Review**
   - Code quality
   - Architecture fit
   - Documentation completeness
   - Test coverage

3. **Feedback**
   - Address review comments
   - Push updates to same branch
   - PR updates automatically

4. **Approval**
   - At least one maintainer approval required
   - All checks must pass
   - Merge when approved

---

## Reporting Bugs

### Before Reporting

1. **Search Existing Issues**
   - Check if bug already reported
   - Add comment to existing issue if relevant

2. **Verify Bug**
   - Run diagnostics: `.venv/bin/python whisprbar.py --diagnose`
   - Check with debug logging: `WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py`
   - Try with fresh config (backup and delete `~/.config/whisprbar.json`)

### Bug Report Template

```markdown
## Bug Description
Clear description of what the bug is.

## Steps to Reproduce
1. Start WhisprBar
2. Click on '...'
3. Press hotkey
4. See error

## Expected Behavior
What you expected to happen.

## Actual Behavior
What actually happened.

## Environment
- OS: Ubuntu 22.04
- Desktop Environment: GNOME 42
- Display Server: X11 / Wayland
- WhisprBar Version: 1.0.0
- Python Version: 3.10.6

## Diagnostics Output
```
Paste output of: .venv/bin/python whisprbar.py --diagnose
```

## Debug Log
```
Paste relevant portions of debug log
```

## Configuration
```json
{
  "language": "en",
  "transcription_backend": "openai",
  ...
}
```

## Additional Context
Screenshots, recordings, or other relevant information.
```

### What Makes a Good Bug Report

- **Specific**: Clearly describe the issue
- **Reproducible**: List exact steps to reproduce
- **Complete**: Include all requested information
- **Minimal**: Simplest steps to reproduce
- **Evidence**: Logs, screenshots, etc.

---

## Suggesting Features

### Feature Request Template

```markdown
## Feature Description
Clear description of the feature you'd like.

## Use Case
Why is this feature useful? What problem does it solve?

## Proposed Solution
How would you like this feature to work?

## Alternative Solutions
Have you considered any alternative approaches?

## Additional Context
Screenshots, mockups, examples from other software.

## Implementation Notes
(Optional) Technical details if you have ideas
```

### Feature Discussion

- Features are discussed in GitHub Issues
- Maintainers will label as `enhancement`
- Community feedback is encouraged
- Implementation priority based on:
  - Number of users affected
  - Complexity of implementation
  - Fit with project goals
  - Available maintainer time

---

## Community Guidelines

### Code of Conduct

We are committed to providing a welcoming and inclusive environment. All contributors are expected to:

- **Be Respectful**: Treat everyone with respect and kindness
- **Be Constructive**: Provide helpful feedback and suggestions
- **Be Collaborative**: Work together toward common goals
- **Be Patient**: Everyone is learning and growing

### Communication

- **GitHub Issues**: Bug reports, feature requests, discussions
- **Pull Requests**: Code contributions, reviews
- **Private Contact**: Open a GitHub issue with the label `private` for sensitive matters

### Recognition

Contributors are recognized in:
- Git commit history
- CHANGELOG.md for significant contributions
- README.md credits section (for major contributions)

---

## Getting Help

### Resources

- **Developer Guide**: [CLAUDE.md](CLAUDE.md) - Comprehensive architecture documentation
- **User Guide**: [README.md](README.md) - Usage instructions
- **Changelog**: [CHANGELOG.md](CHANGELOG.md) - Version history
- **Testing**: See the [Testing](#testing) section below

### Questions

- **GitHub Issues**: For bugs and features
- **GitHub Issues**: For general questions and discussion

---

## Development Tips

### Debugging

```python
# Use debug() function for logging
from whisprbar.utils import debug

debug("Starting transcription...")
debug(f"Audio length: {len(audio)} samples")
```

```bash
# Enable debug output
WHISPRBAR_DEBUG=1 .venv/bin/python whisprbar.py
```

### Hot Reload

```bash
# After changing code, restart app
pkill -f whisprbar
.venv/bin/python whisprbar.py
```

### Testing Individual Modules

```python
# Test config module
.venv/bin/python -c "
from whisprbar.config import load_config
cfg = load_config()
print(cfg['language'])
"

# Test icon generation
.venv/bin/python -c "
from whisprbar.utils import build_icon
icon = build_icon('ready')
icon.show()
"
```

### Common Pitfalls

1. **Circular Imports**: Always check dependency direction
2. **Threading**: Use locks for shared state, GLib.idle_add() for GTK updates
3. **Config Changes**: Remember to call save_config() after modifying cfg
4. **API Keys**: Never commit .env files or log API keys

---

## Release Process (Maintainers)

For maintainers preparing releases:

1. **Update Version**
   ```python
   # whisprbar/__init__.py
   __version__ = "1.1.0"
   ```

2. **Update CHANGELOG.md**
   - Move Unreleased changes to new version section
   - Add release date

3. **Create Git Tag**
   ```bash
   git tag -a v1.1.0 -m "Release v1.1.0"
   git push origin v1.1.0
   ```

4. **Create GitHub Release**
   - Use CHANGELOG.md content
   - Upload any release artifacts

5. **Announce**
   - GitHub Discussions
   - Social media (if applicable)

---

## Thank You!

Your contributions make WhisprBar better for everyone. Whether you're fixing bugs, adding features, improving documentation, or helping other users, your efforts are appreciated!

**Happy Coding!** 🚀

---

**Maintainer**: Henrik W (henrik092)
**Last Updated**: 2025-10-15
**Version**: 1.0.0
