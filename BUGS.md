# WhisprBar V6 - Bug Tracking

This document provides an overview of all known bugs in WhisprBar V6 and their current status.

**Last Updated:** 2026-01-01
**Total Bugs:** 17 (4 core + 13 ElevenLabs)
**Fixed:** 5 | **Open:** 12

---

## Quick Links

- [Bug Dashboard](docs/bugs/README.md) - Statistics and progress
- [Core Bug Reports](docs/bugs/core/) - 4 bugs (1 critical, 3 medium)
- [ElevenLabs Bug Reports](docs/bugs/elevenlabs/) - 13 bugs (3 critical, 3 high, 5 medium, 2 low)
- [Completed Fixes](docs/fixes/FIXES-COMPLETED.md) - 7 previously fixed bugs

---

## Summary by Severity

| Severity | Core | ElevenLabs | Total | Fixed |
|----------|------|------------|-------|-------|
| **CRITICAL** | 1 | 3 | **4** | 2 |
| HIGH | 0 | 3 | 3 | 2 |
| MEDIUM | 3 | 5 | 8 | 1 |
| LOW | 0 | 2 | 2 | 0 |
| **Total** | **4** | **13** | **17** | **5** |

---

## Core Codebase Bugs

| ID | Title | Priority | Status | File |
|----|-------|----------|--------|------|
| [BUG-007](docs/bugs/core/BUG-007-hotkey-listener-deadlock.md) | **Hotkey Listener Deadlock** | **CRITICAL** | ✅ Fixed (V6) | hotkeys.py:465-475 |
| [BUG-008](docs/bugs/core/BUG-008-audio-buffer-inefficiency.md) | Audio Buffer Inefficiency | MEDIUM | ✅ Fixed (V6) | audio.py:148-235 |
| [BUG-010](docs/bugs/core/BUG-010-circular-import-risk.md) | Circular Import Risk | MEDIUM | ✅ No Issue | transcription.py:1-30 |
| [BUG-011](docs/bugs/core/BUG-011-ignored-language-parameter.md) | Ignored Language Parameter | MEDIUM | ✅ Fixed (2026-01-01) | transcription.py:731-853 |

---

## ElevenLabs Scribe v2 Bugs

### Critical

| ID | Title | Status | File |
|----|-------|--------|------|
| [BUG-E01](docs/bugs/elevenlabs/BUG-E01-event-loop-creation.md) | Event Loop Creation in Non-Async Thread | ✅ Mitigated | transcription.py:614 |
| [BUG-E02](docs/bugs/elevenlabs/BUG-E02-connection-race-condition.md) | Race Condition in Transcript Collection | ✅ Fixed (2026-01-01) | transcription.py:564-594 |
| [BUG-E03](docs/bugs/elevenlabs/BUG-E03-unclosed-websocket.md) | Unclosed WebSocket on Error | ✅ Fixed (2026-01-01) | transcription.py:605-611 |

### High

| ID | Title | Status | File |
|----|-------|--------|------|
| [BUG-E04](docs/bugs/elevenlabs/BUG-E04-thread-safety-client.md) | Thread Safety of Client Access | ✅ Verified Safe | transcription.py:471-506 |
| [BUG-E05](docs/bugs/elevenlabs/BUG-E05-async-callback-verification.md) | Async Callback Registration Not Verified | Open | transcription.py:574-577 |
| [BUG-E06](docs/bugs/elevenlabs/BUG-E06-arbitrary-sleep.md) | Arbitrary Sleep in Async Context | ✅ Fixed (2026-01-01) | transcription.py:590-594 |

### Medium

| ID | Title | Status | File |
|----|-------|--------|------|
| [BUG-E07](docs/bugs/elevenlabs/BUG-E07-connection-timeout.md) | Missing Connection Timeout | ✅ Fixed (2026-01-01) | transcription.py:549-559 |
| [BUG-E08](docs/bugs/elevenlabs/BUG-E08-audio-chunking-logic.md) | Audio Chunking Calculation Wrong | Open | transcription.py:579-585 |
| [BUG-E09](docs/bugs/elevenlabs/BUG-E09-api-key-validation.md) | No API Key Validation Before Connect | Open | transcription.py:517-518 |
| [BUG-E10](docs/bugs/elevenlabs/BUG-E10-config-schema-missing.md) | Missing Config Schema for ElevenLabs | Open | config.py |
| [BUG-E11](docs/bugs/elevenlabs/BUG-E11-exception-propagation.md) | Exception Details Not Propagated | Open | transcription.py:602-604 |

### Low

| ID | Title | Status | File |
|----|-------|--------|------|
| [BUG-E12](docs/bugs/elevenlabs/BUG-E12-streaming-support-flag.md) | Wrong Streaming Support Flag | Open | transcription.py:509 |
| [BUG-E13](docs/bugs/elevenlabs/BUG-E13-error-messages.md) | Generic Error Messages | Open | multiple |

---

## Previously Fixed Bugs (12)

These bugs have been fixed in previous commits:

### Fixed 2026-01-01
8. **Language Parameter Lost in Chunked Transcription** - Added language parameter to chunk functions
9. **ElevenLabs WebSocket Resource Leak** - Added finally block for connection cleanup
10. **ElevenLabs Connection Timeout** - Added 30s timeout with asyncio.wait_for()
11. **ElevenLabs Race Condition** - Replaced arbitrary sleep with Event-based synchronization
12. **ElevenLabs Arbitrary Sleep** - Using asyncio.Event() with proper timeout

### Fixed Previously
1. **Signal Handler Race Condition** (commit 35e770e) - Now properly signal-safe
2. **Duplicate Audio Processing** (commit 8c712c1) - Removed double VAD/NR
3. **Thread-safe State Management** (commit 491e75c) - Added locks
4. **Temp File Cleanup Path Injection** (commit 14ea64d) - Secure cleanup
5. **Audio Queue Blocking** (commit 0571805) - Non-blocking queue ops
6. **VAD Queue Mismatch** - Verified: by design (VAD tolerates dropped frames)
7. **Unicode Capitalization** - Verified: works 95%+ with re.UNICODE flag

See [FIXES-COMPLETED.md](docs/fixes/FIXES-COMPLETED.md) for details.

---

## Contributing

When fixing a bug:
1. Reference the bug ID in your commit message (e.g., `fix: resolve BUG-007`)
2. Update the bug report status to "Fixed"
3. Add fix documentation to `docs/fixes/`
4. Update this file's statistics

---

**Repository:** [WhisprBar](https://github.com/henrik092/whisprBar)
**Maintainer:** Henrik W
