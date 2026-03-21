"""Unit tests for whisprbar.state module."""

import threading

import pytest

from whisprbar.state import AppPhase, InvalidTransition, StateMachine


@pytest.mark.unit
class TestAppPhase:
    """Tests for AppPhase enum."""

    def test_all_phases_exist(self):
        """All expected phases are defined."""
        phases = {p.value for p in AppPhase}
        assert phases == {"idle", "recording", "processing", "transcribing", "pasting", "error"}

    def test_phase_values_are_strings(self):
        """Phase values are lowercase strings."""
        for phase in AppPhase:
            assert isinstance(phase.value, str)
            assert phase.value == phase.value.lower()


@pytest.mark.unit
class TestInvalidTransition:
    """Tests for InvalidTransition exception."""

    def test_attributes(self):
        exc = InvalidTransition(AppPhase.IDLE, AppPhase.PASTING)
        assert exc.current == AppPhase.IDLE
        assert exc.target == AppPhase.PASTING

    def test_message(self):
        exc = InvalidTransition(AppPhase.IDLE, AppPhase.PASTING)
        assert "idle" in str(exc)
        assert "pasting" in str(exc)


@pytest.mark.unit
class TestStateMachine:
    """Tests for the StateMachine class."""

    def test_initial_phase_is_idle(self):
        """State machine starts in IDLE."""
        sm = StateMachine()
        assert sm.phase == AppPhase.IDLE

    def test_valid_transition_idle_to_recording(self):
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        assert sm.phase == AppPhase.RECORDING

    def test_valid_transition_recording_to_processing(self):
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        assert sm.phase == AppPhase.PROCESSING

    def test_valid_full_happy_path(self):
        """Complete flow: IDLE→RECORDING→PROCESSING→TRANSCRIBING→PASTING→IDLE."""
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        sm.transition(AppPhase.TRANSCRIBING)
        sm.transition(AppPhase.PASTING)
        sm.transition(AppPhase.IDLE)
        assert sm.phase == AppPhase.IDLE

    def test_valid_cancel_recording(self):
        """RECORDING→IDLE (cancel) is valid."""
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.IDLE)
        assert sm.phase == AppPhase.IDLE

    def test_valid_error_from_processing(self):
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        sm.transition(AppPhase.ERROR)
        assert sm.phase == AppPhase.ERROR

    def test_valid_error_recovery(self):
        """ERROR→IDLE is valid."""
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        sm.transition(AppPhase.ERROR)
        sm.transition(AppPhase.IDLE)
        assert sm.phase == AppPhase.IDLE

    def test_invalid_transition_raises(self):
        """IDLE→PASTING is not valid."""
        sm = StateMachine()
        with pytest.raises(InvalidTransition) as exc_info:
            sm.transition(AppPhase.PASTING)
        assert exc_info.value.current == AppPhase.IDLE
        assert exc_info.value.target == AppPhase.PASTING

    def test_invalid_idle_to_processing(self):
        """IDLE→PROCESSING is not valid (must record first)."""
        sm = StateMachine()
        with pytest.raises(InvalidTransition):
            sm.transition(AppPhase.PROCESSING)

    def test_invalid_idle_to_transcribing(self):
        sm = StateMachine()
        with pytest.raises(InvalidTransition):
            sm.transition(AppPhase.TRANSCRIBING)

    def test_try_transition_success(self):
        sm = StateMachine()
        assert sm.try_transition(AppPhase.RECORDING) is True
        assert sm.phase == AppPhase.RECORDING

    def test_try_transition_failure(self):
        sm = StateMachine()
        assert sm.try_transition(AppPhase.PASTING) is False
        assert sm.phase == AppPhase.IDLE

    def test_reset_from_any_state(self):
        """reset() always goes to IDLE regardless of current phase."""
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        sm.transition(AppPhase.TRANSCRIBING)
        sm.reset()
        assert sm.phase == AppPhase.IDLE

    def test_reset_from_idle_no_observer_call(self):
        """reset() from IDLE doesn't notify observers."""
        sm = StateMachine()
        changes = []
        sm.on_change(lambda old, new: changes.append((old, new)))
        sm.reset()
        assert changes == []

    def test_reset_from_error(self):
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        sm.transition(AppPhase.ERROR)
        sm.reset()
        assert sm.phase == AppPhase.IDLE

    def test_observer_called_on_transition(self):
        sm = StateMachine()
        changes = []
        sm.on_change(lambda old, new: changes.append((old, new)))
        sm.transition(AppPhase.RECORDING)
        assert changes == [(AppPhase.IDLE, AppPhase.RECORDING)]

    def test_observer_called_on_reset(self):
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        changes = []
        sm.on_change(lambda old, new: changes.append((old, new)))
        sm.reset()
        assert changes == [(AppPhase.RECORDING, AppPhase.IDLE)]

    def test_observer_exception_does_not_break_state(self):
        """Observer error doesn't prevent state change."""
        sm = StateMachine()

        def bad_observer(old, new):
            raise RuntimeError("observer crash")

        sm.on_change(bad_observer)
        sm.transition(AppPhase.RECORDING)  # Should not raise
        assert sm.phase == AppPhase.RECORDING

    def test_multiple_observers(self):
        sm = StateMachine()
        results = []
        sm.on_change(lambda old, new: results.append("A"))
        sm.on_change(lambda old, new: results.append("B"))
        sm.transition(AppPhase.RECORDING)
        assert results == ["A", "B"]

    # --- Compat properties ---

    def test_recording_property_getter(self):
        sm = StateMachine()
        assert sm.recording is False
        sm.transition(AppPhase.RECORDING)
        assert sm.recording is True
        sm.transition(AppPhase.PROCESSING)
        assert sm.recording is False

    def test_transcribing_property_getter(self):
        sm = StateMachine()
        assert sm.transcribing is False
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        sm.transition(AppPhase.TRANSCRIBING)
        assert sm.transcribing is True

    def test_recording_setter_true(self):
        sm = StateMachine()
        sm.recording = True
        assert sm.phase == AppPhase.RECORDING

    def test_recording_setter_false(self):
        """Setting recording=False from RECORDING transitions to PROCESSING."""
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.recording = False
        assert sm.phase == AppPhase.PROCESSING

    def test_transcribing_setter_false(self):
        """Setting transcribing=False from TRANSCRIBING transitions to IDLE."""
        sm = StateMachine()
        sm.transition(AppPhase.RECORDING)
        sm.transition(AppPhase.PROCESSING)
        sm.transition(AppPhase.TRANSCRIBING)
        sm.transcribing = False
        assert sm.phase == AppPhase.IDLE

    # --- Extra state dict compat ---

    def test_dict_access(self):
        sm = StateMachine()
        sm["key"] = "value"
        assert sm["key"] == "value"

    def test_dict_get_default(self):
        sm = StateMachine()
        assert sm.get("missing", "default") == "default"

    def test_dict_get_none(self):
        sm = StateMachine()
        assert sm["nonexistent"] is None

    # --- Thread safety ---

    def test_concurrent_transitions(self):
        """Concurrent transitions don't corrupt state."""
        sm = StateMachine()
        errors = []

        def cycle():
            for _ in range(50):
                try:
                    sm.try_transition(AppPhase.RECORDING)
                    sm.try_transition(AppPhase.PROCESSING)
                    sm.try_transition(AppPhase.TRANSCRIBING)
                    sm.try_transition(AppPhase.IDLE)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=cycle) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # State should be valid (some transitions fail due to races, that's fine)
        assert sm.phase in list(AppPhase)
        assert errors == []
