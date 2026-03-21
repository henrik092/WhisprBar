"""State machine for WhisprBar application lifecycle.

Replaces boolean flags (recording, transcribing) with an enum-based
state machine that enforces valid transitions and prevents impossible states.
"""

import threading
from enum import Enum
from typing import Callable, Dict, List, Optional, Set


class AppPhase(Enum):
    """Application lifecycle phases."""

    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    TRANSCRIBING = "transcribing"
    PASTING = "pasting"
    ERROR = "error"


class InvalidTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current: AppPhase, target: AppPhase):
        self.current = current
        self.target = target
        super().__init__(f"Invalid transition: {current.value} -> {target.value}")


class StateMachine:
    """Thread-safe state machine for application lifecycle.

    Enforces valid transitions between AppPhase states.
    Provides backwards-compatible properties (recording, transcribing)
    and an observer mechanism for state change notifications.
    """

    TRANSITIONS: Dict[AppPhase, Set[AppPhase]] = {
        AppPhase.IDLE: {AppPhase.RECORDING},
        AppPhase.RECORDING: {AppPhase.PROCESSING, AppPhase.IDLE},  # IDLE = cancel
        AppPhase.PROCESSING: {AppPhase.TRANSCRIBING, AppPhase.ERROR, AppPhase.IDLE},
        AppPhase.TRANSCRIBING: {AppPhase.PASTING, AppPhase.IDLE, AppPhase.ERROR},
        AppPhase.PASTING: {AppPhase.IDLE, AppPhase.ERROR},
        AppPhase.ERROR: {AppPhase.IDLE},
    }

    def __init__(self) -> None:
        self._phase = AppPhase.IDLE
        self._lock = threading.RLock()
        self._observers: List[Callable[[AppPhase, AppPhase], None]] = []
        self._extra_state: Dict[str, object] = {}

    @property
    def phase(self) -> AppPhase:
        """Current application phase (thread-safe read)."""
        with self._lock:
            return self._phase

    def transition(self, target: AppPhase) -> None:
        """Transition to a new phase.

        Args:
            target: The target AppPhase to transition to.

        Raises:
            InvalidTransition: If the transition is not allowed.
        """
        with self._lock:
            old = self._phase
            if target not in self.TRANSITIONS.get(old, set()):
                raise InvalidTransition(old, target)
            self._phase = target

        # Notify observers outside the lock to prevent deadlocks
        for observer in self._observers:
            try:
                observer(old, target)
            except Exception:
                pass  # Observers must not break the state machine

    def try_transition(self, target: AppPhase) -> bool:
        """Try to transition; return False instead of raising on invalid transition."""
        try:
            self.transition(target)
            return True
        except InvalidTransition:
            return False

    def reset(self) -> None:
        """Reset to IDLE state (always valid, bypasses transition rules)."""
        with self._lock:
            old = self._phase
            self._phase = AppPhase.IDLE
        if old != AppPhase.IDLE:
            for observer in self._observers:
                try:
                    observer(old, AppPhase.IDLE)
                except Exception:
                    pass

    def on_change(self, callback: Callable[[AppPhase, AppPhase], None]) -> None:
        """Register an observer for state changes.

        Args:
            callback: Called with (old_phase, new_phase) after each transition.
        """
        self._observers.append(callback)

    # --- Backwards-compatible properties ---

    @property
    def recording(self) -> bool:
        """True if currently recording (compat with old AppState)."""
        return self.phase == AppPhase.RECORDING

    @recording.setter
    def recording(self, value: bool) -> None:
        """Compat setter: transition to RECORDING or IDLE."""
        if value:
            self.try_transition(AppPhase.RECORDING)
        elif self.phase == AppPhase.RECORDING:
            self.try_transition(AppPhase.PROCESSING)

    @property
    def transcribing(self) -> bool:
        """True if currently transcribing (compat with old AppState)."""
        return self.phase == AppPhase.TRANSCRIBING

    @transcribing.setter
    def transcribing(self, value: bool) -> None:
        """Compat setter: transition to TRANSCRIBING or IDLE."""
        if value:
            self.try_transition(AppPhase.TRANSCRIBING)
        elif self.phase == AppPhase.TRANSCRIBING:
            self.try_transition(AppPhase.IDLE)

    # --- Extra state dict (compat with old AppState["key"] access) ---

    def __getitem__(self, key: str) -> object:
        return self._extra_state.get(key)

    def __setitem__(self, key: str, value: object) -> None:
        self._extra_state[key] = value

    def get(self, key: str, default: object = None) -> object:
        return self._extra_state.get(key, default)
