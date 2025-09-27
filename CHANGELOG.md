# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Tray indicator now highlights an intermediate "Transcribing" state while audio is processed.

### Fixed
- Ensure the audio buffer drains gracefully after recording stops so brief utterances are not lost.

### Changed
- Refreshed README guidance around acquiring an OpenAI API key.

## [0.1.0] - 2025-09-25
### Added
- Initial public release with tray UI, global recording hotkey, OpenAI transcription pipeline, and auto-paste options for X11/Wayland.
- Diagnostics wizard and `--diagnose` CLI report covering session type, tray backend, audio devices, and API key status.
- Interactive installer (`install.sh`) that checks system packages, sets up the virtualenv, and configures `~/.config/whisprbar.env`.
- Update notification mechanism that checks GitHub releases and suggests `git pull && ./install.sh`.

### Changed
- Documentation converted to English for GitHub publication, including README, INSTALL, deploy plan, and work log summaries.

[Unreleased]: https://github.com/henrik092/whisprBar/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/henrik092/whisprBar/releases/tag/v0.1.0
