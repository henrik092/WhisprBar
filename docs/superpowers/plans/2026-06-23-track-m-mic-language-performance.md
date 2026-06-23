# Track M Mic Language And Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give users clear microphone health feedback, practical multi-language auto mode, and selectable latency/quality profiles.

**Architecture:** Add pure policy modules for audio health, language choice, and performance profiles, then surface them through diagnostics and settings. Keep backend-specific probing isolated so the app remains Linux-friendly and testable without real audio devices or paid API calls.

**Tech Stack:** Python 3.10+, pytest, sounddevice/numpy where already used, existing diagnostics UI, existing transcription factory, existing config validation.

---

## File Structure

- Create `whisprbar/audio/health.py`: computes microphone signal health from numeric samples and device metadata.
- Create `tests/test_audio_health.py`: tests health classifications without real devices.
- Create `whisprbar/transcription/language.py`: resolves transcription language from config, preferred languages, and optional backend hint.
- Create `tests/test_language_selection.py`: tests deterministic language selection.
- Create `whisprbar/performance_profiles.py`: maps profile names to config overrides.
- Create `tests/test_performance_profiles.py`: tests profile overrides and validation.
- Modify `whisprbar/utils.py` and `whisprbar/ui/diagnostics.py`: include mic health and active performance profile in diagnostics.
- Modify `whisprbar/config.py`, `whisprbar/config_types.py`, `whisprbar/ui/settings_webview.py`, and `whisprbar/i18n.py`: expose settings.
- Modify `whisprbar/main.py` and transcription backend wiring where language is selected.

## Behavior Contract

- Mic health checks are advisory; they must not block dictation.
- Auto language mode uses only configured preferred languages and falls back to the configured language.
- Performance profiles are named presets, not hidden mutable magic. The selected profile must be visible in settings and diagnostics.
- No live API benchmark is required to select a profile.

### Task 1: Add Microphone Health Scoring

**Files:**
- Create: `whisprbar/audio/health.py`
- Create: `tests/test_audio_health.py`
- Modify: `whisprbar/utils.py`

- [ ] **Step 1: Write failing audio-health tests**

```python
"""Tests for microphone health scoring."""

import numpy as np
import pytest

from whisprbar.audio.health import MicHealth, score_audio_health


@pytest.mark.unit
def test_score_audio_health_detects_silence():
    audio = np.zeros(16000, dtype=np.float32)

    result = score_audio_health(audio, sample_rate=16000)

    assert result.status == "warn"
    assert result.reason == "silence"


@pytest.mark.unit
def test_score_audio_health_accepts_clear_signal():
    audio = np.ones(16000, dtype=np.float32) * 0.03

    result = score_audio_health(audio, sample_rate=16000)

    assert result == MicHealth(status="ok", reason="clear_signal", rms=0.03, peak=0.03)
```

- [ ] **Step 2: Run the failing audio-health tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio_health.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.audio.health'
```

- [ ] **Step 3: Add audio health module**

Create `whisprbar/audio/health.py`:

```python
"""Microphone signal health helpers."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MicHealth:
    status: str
    reason: str
    rms: float
    peak: float


def score_audio_health(audio, *, sample_rate: int) -> MicHealth:
    samples = np.asarray(audio, dtype=np.float32)
    if samples.size == 0:
        return MicHealth(status="warn", reason="empty", rms=0.0, peak=0.0)
    rms = round(float(np.sqrt(np.mean(samples ** 2))), 4)
    peak = round(float(np.max(np.abs(samples))), 4)
    if rms < 0.001:
        return MicHealth(status="warn", reason="silence", rms=rms, peak=peak)
    if peak >= 0.98:
        return MicHealth(status="warn", reason="clipping", rms=rms, peak=peak)
    if rms > 0.20:
        return MicHealth(status="warn", reason="very_loud", rms=rms, peak=peak)
    return MicHealth(status="ok", reason="clear_signal", rms=rms, peak=peak)
```

- [ ] **Step 4: Add diagnostics entry**

In `whisprbar/utils.py`, add a diagnostics result from the last recorded health snapshot if available. Store the snapshot in memory only:

```python
_last_mic_health = None


def set_last_mic_health(health) -> None:
    global _last_mic_health
    _last_mic_health = health
```

In `collect_diagnostics()`:

```python
if _last_mic_health is not None:
    status = STATUS_OK if _last_mic_health.status == "ok" else STATUS_WARN
    results.append(
        DiagnosticResult(
            "mic_health",
            tr("diagnostics.mic_health"),
            status,
            f"{_last_mic_health.reason}: rms={_last_mic_health.rms}, peak={_last_mic_health.peak}",
        )
    )
```

- [ ] **Step 5: Verify audio health tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio_health.py tests\test_utils.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 6: Commit mic health scoring**

```bash
git add whisprbar/audio/health.py whisprbar/utils.py tests/test_audio_health.py tests/test_utils.py
git commit -m "feat: add microphone health scoring"
```

### Task 2: Add Deterministic Language Selection

**Files:**
- Create: `whisprbar/transcription/language.py`
- Create: `tests/test_language_selection.py`
- Modify: `whisprbar/main.py`
- Modify: `whisprbar/config.py`
- Modify: `whisprbar/config_types.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing language-selection tests**

```python
"""Tests for language selection policy."""

import pytest

from whisprbar.transcription.language import resolve_transcription_language


@pytest.mark.unit
def test_auto_language_uses_backend_hint_when_preferred():
    cfg = {
        "language": "de",
        "flow_language_auto_detect": True,
        "flow_preferred_languages": ["de", "en"],
    }

    assert resolve_transcription_language(cfg, backend_hint="en") == "en"


@pytest.mark.unit
def test_auto_language_rejects_unpreferred_hint():
    cfg = {
        "language": "de",
        "flow_language_auto_detect": True,
        "flow_preferred_languages": ["de", "en"],
    }

    assert resolve_transcription_language(cfg, backend_hint="fr") == "de"


@pytest.mark.unit
def test_manual_language_ignores_backend_hint():
    cfg = {"language": "de", "flow_language_auto_detect": False}

    assert resolve_transcription_language(cfg, backend_hint="en") == "de"
```

- [ ] **Step 2: Run the failing language tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_language_selection.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.transcription.language'
```

- [ ] **Step 3: Add language policy module**

Create `whisprbar/transcription/language.py`:

```python
"""Transcription language selection policy."""

from typing import Mapping, Optional


def resolve_transcription_language(cfg: Mapping[str, object], *, backend_hint: Optional[str] = None) -> str:
    configured = str(cfg.get("language") or "de")
    if not cfg.get("flow_language_auto_detect", False):
        return configured
    preferred = cfg.get("flow_preferred_languages")
    if not isinstance(preferred, list) or not preferred:
        return configured
    normalized_preferred = [str(item).strip().lower() for item in preferred if str(item).strip()]
    hint = str(backend_hint or "").strip().lower()
    if hint and hint in normalized_preferred:
        return hint
    return configured if configured in normalized_preferred else normalized_preferred[0]
```

- [ ] **Step 4: Wire language selection where transcribe is called**

In `whisprbar/main.py`, import:

```python
from whisprbar.transcription.language import resolve_transcription_language
```

Replace direct `cfg.get("language", "de")` at the transcription call with:

```python
selected_language = resolve_transcription_language(cfg)
text, _transcribe_ms = _transcribe_processed_audio(
    processed,
    selected_language,
    live_finish=live_finish,
)
```

If a live backend later returns language metadata, pass that metadata into `resolve_transcription_language(cfg, backend_hint=hint)` before Flow processing.

- [ ] **Step 5: Verify language tests pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_language_selection.py tests\test_config.py tests\test_main_flow_integration.py -q
```

Expected:

```text
pytest exits 0
```

- [ ] **Step 6: Commit language selection**

```bash
git add whisprbar/transcription/language.py whisprbar/main.py tests/test_language_selection.py tests/test_main_flow_integration.py
git commit -m "feat: add deterministic language auto mode"
```

### Task 3: Add Performance Profiles

**Files:**
- Create: `whisprbar/performance_profiles.py`
- Create: `tests/test_performance_profiles.py`
- Modify: `whisprbar/config.py`
- Modify: `whisprbar/config_types.py`
- Modify: `whisprbar/ui/settings_webview.py`
- Modify: `tests/test_settings_webview.py`

- [ ] **Step 1: Write failing performance-profile tests**

```python
"""Tests for performance profile policy."""

import pytest

from whisprbar.performance_profiles import apply_performance_profile


@pytest.mark.unit
def test_fast_profile_prefers_low_latency_settings():
    cfg = {"performance_profile": "fast", "noise_reduction_enabled": True}

    result = apply_performance_profile(cfg)

    assert result["noise_reduction_enabled"] is False
    assert result["min_drain_timeout_ms"] == 100
    assert result["flow_rewrite_timeout_seconds"] <= 6.0


@pytest.mark.unit
def test_quality_profile_keeps_noise_reduction():
    cfg = {"performance_profile": "quality"}

    result = apply_performance_profile(cfg)

    assert result["noise_reduction_enabled"] is True
    assert result["chunking_enabled"] is True
```

- [ ] **Step 2: Run the failing profile tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_performance_profiles.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'whisprbar.performance_profiles'
```

- [ ] **Step 3: Add performance profile policy**

Create `whisprbar/performance_profiles.py`:

```python
"""Named latency and quality profiles for WhisprBar."""

from copy import deepcopy
from typing import Mapping


PROFILE_OVERRIDES = {
    "fast": {
        "noise_reduction_enabled": False,
        "min_drain_timeout_ms": 100,
        "flow_rewrite_timeout_seconds": 6.0,
        "chunking_enabled": True,
        "chunk_duration_seconds": 20.0,
    },
    "balanced": {
        "noise_reduction_enabled": True,
        "min_drain_timeout_ms": 150,
        "flow_rewrite_timeout_seconds": 12.0,
        "chunking_enabled": True,
        "chunk_duration_seconds": 30.0,
    },
    "quality": {
        "noise_reduction_enabled": True,
        "min_drain_timeout_ms": 250,
        "flow_rewrite_timeout_seconds": 20.0,
        "chunking_enabled": True,
        "chunk_duration_seconds": 45.0,
    },
}


def apply_performance_profile(cfg: Mapping[str, object]) -> dict:
    result = deepcopy(dict(cfg))
    profile = str(result.get("performance_profile") or "balanced")
    if profile not in PROFILE_OVERRIDES:
        profile = "balanced"
    result.update(PROFILE_OVERRIDES[profile])
    result["performance_profile"] = profile
    return result
```

Add config default:

```python
"performance_profile": "balanced",
```

Clamp allowed values to `{"fast", "balanced", "quality"}`.

- [ ] **Step 4: Apply selected profile at runtime**

In `whisprbar/main.py`, after `load_config()` and `validate_config()`, derive runtime config:

```python
from whisprbar.performance_profiles import apply_performance_profile

cfg.update(apply_performance_profile(cfg))
```

Keep saved config unchanged until the user saves Settings.

- [ ] **Step 5: Add Settings select**

In `apply_settings_payload`, save:

```python
config["performance_profile"] = str(
    _setting(settings, "performance_profile", config.get("performance_profile", "balanced"))
)
```

Add Settings row:

```python
_select(
    "performance_profile",
    tr("settings.performance_profile"),
    tr("settings.performance_profile_desc"),
    (("fast", "Fast"), ("balanced", "Balanced"), ("quality", "Quality")),
    config.get("performance_profile", "balanced"),
)
```

- [ ] **Step 6: Run Track M verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_audio_health.py tests\test_language_selection.py tests\test_performance_profiles.py tests\test_settings_webview.py tests\test_config.py tests\test_utils.py -q
.\.venv\Scripts\python.exe -m compileall -q whisprbar tests
git diff --check
```

Expected:

```text
pytest exits 0
compileall exits 0
git diff --check exits 0
```

- [ ] **Step 7: Commit Track M**

```bash
git add whisprbar tests
git commit -m "feat: add mic language performance controls"
```

## Manual QA

- Record a short clear sample, open Diagnostics, and confirm microphone health shows a clear signal.
- Switch to Fast profile, restart WhisprBar, and confirm diagnostics/settings show Fast as active.
- Enable language auto mode with preferred languages `["de", "en"]`, dictate English and German samples, and confirm the selected backend still falls back cleanly when no language hint is available.
