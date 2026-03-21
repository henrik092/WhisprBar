"""WhisprBar application class with dependency injection.

Provides a central WhisprBarApp class that wires together all modules
via constructor injection and event bus, replacing the global state
and callback patterns in main.py.

This module is the new architectural core. The existing main.py
continues to work as-is for backwards compatibility, but new code
should use WhisprBarApp for cleaner dependency management.
"""

import threading
from typing import Any, Callable, Dict, Optional

from whisprbar.config import cfg, load_config, save_config
from whisprbar.config_types import AppConfig, typed_config
from whisprbar.events import EventBus, RECORDING_STARTED, RECORDING_STOPPED, RECORDING_CANCELLED
from whisprbar.events import PROCESSING_STARTED, TRANSCRIPTION_STARTED, TRANSCRIPTION_COMPLETE
from whisprbar.events import TRANSCRIPTION_ERROR, STATE_CHANGED, CONFIG_CHANGED
from whisprbar.events import OVERLAY_SHOW, OVERLAY_UPDATE, OVERLAY_HIDE
from whisprbar.state import StateMachine, AppPhase


class WhisprBarApp:
    """Central application class with dependency injection.

    Owns the event bus, state machine, and typed config.
    Coordinates all modules without them needing to know about each other.

    Usage:
        app = WhisprBarApp()
        app.run()  # Blocking (starts GTK main loop)

    For backwards compatibility, the app also exposes the global cfg dict
    and can be used alongside the existing main.py orchestration.
    """

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the application.

        Args:
            config_dict: Optional config dict. If None, loads from disk via load_config().
        """
        # Load config
        if config_dict is None:
            load_config()
            config_dict = cfg
        self._cfg_dict = config_dict

        # Typed config (immutable snapshot)
        self.config: AppConfig = typed_config(config_dict)

        # Core infrastructure
        self.bus = EventBus()
        self.state = StateMachine()

        # Wire state machine to event bus
        self.state.on_change(self._on_state_changed)

        # Module references (lazy-initialized)
        self._audio = None
        self._transcriber = None
        self._hotkeys = None
        self._tray = None

    def _on_state_changed(self, old: AppPhase, new: AppPhase) -> None:
        """Forward state machine changes to the event bus."""
        self.bus.emit(STATE_CHANGED, old=old, new=new)

    def reload_config(self) -> AppConfig:
        """Reload typed config from the global cfg dict.

        Call this after cfg has been modified (e.g., from settings dialog).
        Returns the new AppConfig.
        """
        self.config = typed_config(self._cfg_dict)
        self.bus.emit(CONFIG_CHANGED)
        return self.config

    # --- Module access (lazy initialization) ---

    def get_audio_module(self):
        """Get the audio module (lazy import to avoid import-time side effects)."""
        if self._audio is None:
            from whisprbar import audio
            self._audio = audio
        return self._audio

    def get_transcriber(self):
        """Get the current transcriber instance."""
        if self._transcriber is None:
            from whisprbar.transcription import get_transcriber
            self._transcriber = get_transcriber()
        return self._transcriber

    def get_hotkey_manager(self):
        """Get the hotkey manager (lazy import)."""
        if self._hotkeys is None:
            from whisprbar.hotkeys import get_hotkey_manager
            self._hotkeys = get_hotkey_manager()
        return self._hotkeys

    # --- High-level operations ---

    def start_recording(self) -> bool:
        """Start audio recording.

        Returns:
            True if recording started, False if transition was invalid.
        """
        if not self.state.try_transition(AppPhase.RECORDING):
            return False
        audio = self.get_audio_module()
        audio.start_recording()
        self.bus.emit(RECORDING_STARTED)
        return True

    def stop_recording(self) -> bool:
        """Stop recording and transition to processing.

        Returns:
            True if stopped, False if not currently recording.
        """
        if not self.state.try_transition(AppPhase.PROCESSING):
            return False
        audio = self.get_audio_module()
        audio_data = audio.stop_recording()
        self.bus.emit(RECORDING_STOPPED, audio_data=audio_data)
        self.bus.emit(PROCESSING_STARTED)
        return True

    def cancel_recording(self) -> bool:
        """Cancel recording without processing.

        Returns:
            True if cancelled, False if not recording.
        """
        if self.state.phase != AppPhase.RECORDING:
            return False
        audio = self.get_audio_module()
        audio.stop_recording()
        self.state.try_transition(AppPhase.IDLE)
        self.bus.emit(RECORDING_CANCELLED)
        return True

    def toggle_recording(self) -> None:
        """Toggle recording on/off (for hotkey binding)."""
        if self.state.phase == AppPhase.RECORDING:
            self.stop_recording()
        elif self.state.phase == AppPhase.IDLE:
            self.start_recording()

    def transcribe(self, audio_data, language: Optional[str] = None) -> Optional[str]:
        """Transcribe audio data.

        Args:
            audio_data: numpy array of audio
            language: Override language (default: from config)

        Returns:
            Transcribed text or None on failure.
        """
        if not self.state.try_transition(AppPhase.TRANSCRIBING):
            return None

        self.bus.emit(TRANSCRIPTION_STARTED)
        lang = language or self.config.transcription.language

        try:
            from whisprbar.transcription import transcribe_audio
            text = transcribe_audio(audio_data, lang)
            if text:
                self.bus.emit(TRANSCRIPTION_COMPLETE, text=text)
                self.state.try_transition(AppPhase.PASTING)
                return text
            else:
                self.state.try_transition(AppPhase.IDLE)
                return None
        except Exception as exc:
            self.bus.emit(TRANSCRIPTION_ERROR, error=str(exc))
            self.state.try_transition(AppPhase.ERROR)
            self.state.reset()
            return None

    def auto_paste(self, text: str) -> None:
        """Paste text to the active window.

        Args:
            text: Text to paste.
        """
        if self.config.paste.auto_paste_enabled:
            try:
                from whisprbar.paste import perform_auto_paste
                perform_auto_paste(text)
            except Exception as exc:
                import sys
                print(f"[WARN] Auto-paste failed: {exc}", file=sys.stderr)
        self.state.try_transition(AppPhase.IDLE)

    def shutdown(self) -> None:
        """Graceful shutdown of all components."""
        self.state.reset()
        if self._hotkeys:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
        if self._transcriber:
            try:
                from whisprbar.transcription import get_transcriber
                transcriber = get_transcriber()
                transcriber.unload()
            except Exception:
                pass
        self.bus.clear()

    # --- Properties for backwards compatibility ---

    @property
    def recording(self) -> bool:
        """True if currently recording."""
        return self.state.recording

    @property
    def transcribing(self) -> bool:
        """True if currently transcribing."""
        return self.state.transcribing

    @property
    def phase(self) -> AppPhase:
        """Current application phase."""
        return self.state.phase
