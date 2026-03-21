"""Unit tests for whisprbar.config_types module."""

import pytest

from whisprbar.config_types import (
    AppConfig,
    AudioConfig,
    ChunkingConfig,
    HotkeyConfig,
    IndicatorConfig,
    OverlayConfig,
    PasteConfig,
    PostprocessConfig,
    TranscriptionConfig,
    typed_config,
)


@pytest.mark.unit
class TestAudioConfig:
    """Tests for AudioConfig dataclass."""

    def test_defaults(self):
        cfg = AudioConfig()
        assert cfg.use_vad is True
        assert cfg.device_name is None
        assert cfg.vad_energy_ratio == 0.05
        assert cfg.noise_reduction_enabled is True
        assert cfg.min_audio_energy == 0.0008
        assert cfg.stop_tail_grace_ms == 500

    def test_frozen(self):
        cfg = AudioConfig()
        with pytest.raises(AttributeError):
            cfg.use_vad = False

    def test_validated_clamps_vad_energy_ratio(self):
        cfg = AudioConfig(vad_energy_ratio=999.0)
        validated = cfg.validated()
        assert validated.vad_energy_ratio == 0.3

    def test_validated_clamps_low_values(self):
        cfg = AudioConfig(vad_energy_ratio=0.0, vad_bridge_ms=-100)
        validated = cfg.validated()
        assert validated.vad_energy_ratio == 0.002
        assert validated.vad_bridge_ms == 0

    def test_validated_clamps_vad_mode(self):
        cfg = AudioConfig(vad_mode=5)
        assert cfg.validated().vad_mode == 3

    def test_validated_clamps_stop_tail_grace(self):
        cfg = AudioConfig(stop_tail_grace_ms=5000)
        assert cfg.validated().stop_tail_grace_ms == 2000

    def test_validated_clamps_noise_reduction_strength(self):
        cfg = AudioConfig(noise_reduction_strength=2.0)
        assert cfg.validated().noise_reduction_strength == 1.0

    def test_validated_clamps_audio_feedback_volume(self):
        cfg = AudioConfig(audio_feedback_volume=-1.0)
        assert cfg.validated().audio_feedback_volume == 0.0

    def test_validated_clamps_min_drain_timeout(self):
        cfg = AudioConfig(min_drain_timeout_ms=50)
        assert cfg.validated().min_drain_timeout_ms == 100


@pytest.mark.unit
class TestPasteConfig:
    """Tests for PasteConfig dataclass."""

    def test_defaults(self):
        cfg = PasteConfig()
        assert cfg.auto_paste_enabled is True
        assert cfg.paste_sequence == "auto"
        assert cfg.paste_delay_ms == 250

    def test_frozen(self):
        cfg = PasteConfig()
        with pytest.raises(AttributeError):
            cfg.paste_delay_ms = 500

    def test_validated_clamps_delay(self):
        cfg = PasteConfig(paste_delay_ms=99999)
        assert cfg.validated().paste_delay_ms == 5000

    def test_validated_clamps_negative_delay(self):
        cfg = PasteConfig(paste_delay_ms=-100)
        assert cfg.validated().paste_delay_ms == 0


@pytest.mark.unit
class TestHotkeyConfig:
    """Tests for HotkeyConfig dataclass."""

    def test_defaults(self):
        cfg = HotkeyConfig()
        assert cfg.hotkey == "F9"
        assert "toggle_recording" in cfg.hotkeys
        assert cfg.hotkeys["toggle_recording"] == "F9"

    def test_hotkeys_dict_has_expected_keys(self):
        cfg = HotkeyConfig()
        expected_keys = {"toggle_recording", "start_recording", "stop_recording",
                         "open_settings", "show_history", "cancel_recording"}
        assert set(cfg.hotkeys.keys()) == expected_keys


@pytest.mark.unit
class TestOverlayConfig:
    """Tests for OverlayConfig dataclass."""

    def test_defaults(self):
        cfg = OverlayConfig()
        assert cfg.live_overlay_enabled is False
        assert cfg.live_overlay_font_size == 14
        assert cfg.live_overlay_x is None
        assert cfg.live_overlay_y is None


@pytest.mark.unit
class TestIndicatorConfig:
    """Tests for IndicatorConfig dataclass."""

    def test_defaults(self):
        cfg = IndicatorConfig()
        assert cfg.recording_indicator_enabled is True
        assert cfg.recording_indicator_style == "soundwave"
        assert cfg.recording_indicator_position == "bottom-center"
        assert cfg.recording_indicator_opacity == 0.85


@pytest.mark.unit
class TestAppConfig:
    """Tests for AppConfig dataclass."""

    def test_defaults(self):
        cfg = AppConfig()
        assert isinstance(cfg.audio, AudioConfig)
        assert isinstance(cfg.transcription, TranscriptionConfig)
        assert isinstance(cfg.paste, PasteConfig)
        assert cfg.notifications_enabled is False
        assert cfg.first_run_complete is False

    def test_frozen(self):
        cfg = AppConfig()
        with pytest.raises(AttributeError):
            cfg.notifications_enabled = True

    def test_validated_propagates(self):
        """validated() validates all sub-configs."""
        cfg = AppConfig(
            audio=AudioConfig(vad_energy_ratio=999.0),
            paste=PasteConfig(paste_delay_ms=99999),
        )
        validated = cfg.validated()
        assert validated.audio.vad_energy_ratio == 0.3
        assert validated.paste.paste_delay_ms == 5000

    def test_from_dict_empty(self):
        """from_dict with empty dict returns defaults."""
        cfg = AppConfig.from_dict({})
        assert cfg.audio.use_vad is True
        assert cfg.transcription.language == "de"
        assert cfg.paste.auto_paste_enabled is True

    def test_from_dict_with_values(self):
        """from_dict maps flat keys to sub-configs."""
        d = {
            "language": "en",
            "use_vad": False,
            "paste_delay_ms": 500,
            "notifications_enabled": True,
            "transcription_backend": "deepgram",
        }
        cfg = AppConfig.from_dict(d)
        assert cfg.transcription.language == "en"
        assert cfg.audio.use_vad is False
        assert cfg.paste.paste_delay_ms == 500
        assert cfg.notifications_enabled is True
        assert cfg.transcription.transcription_backend == "deepgram"

    def test_from_dict_ignores_unknown_keys(self):
        """from_dict silently ignores unknown keys."""
        d = {"unknown_future_key": "value", "another_one": 42}
        cfg = AppConfig.from_dict(d)  # Should not raise
        assert cfg.audio.use_vad is True  # Default still works

    def test_from_dict_validates(self):
        """from_dict auto-validates (clamps values)."""
        d = {"vad_energy_ratio": 999.0}
        cfg = AppConfig.from_dict(d)
        assert cfg.audio.vad_energy_ratio == 0.3

    def test_to_dict_produces_flat_dict(self):
        """to_dict creates flat dict with all keys."""
        cfg = AppConfig()
        d = cfg.to_dict()
        assert isinstance(d, dict)
        # Check some expected keys
        assert "use_vad" in d
        assert "language" in d
        assert "paste_delay_ms" in d
        assert "notifications_enabled" in d
        assert "hotkeys" in d
        assert "hotkey" in d

    def test_roundtrip(self):
        """from_dict(to_dict()) preserves values."""
        original = AppConfig(
            audio=AudioConfig(use_vad=False, device_name="test-mic"),
            transcription=TranscriptionConfig(language="en", transcription_backend="deepgram"),
            paste=PasteConfig(paste_delay_ms=100),
            notifications_enabled=True,
        )
        d = original.to_dict()
        restored = AppConfig.from_dict(d)
        assert restored.audio.use_vad == original.audio.use_vad
        assert restored.audio.device_name == original.audio.device_name
        assert restored.transcription.language == original.transcription.language
        assert restored.transcription.transcription_backend == original.transcription.transcription_backend
        assert restored.paste.paste_delay_ms == original.paste.paste_delay_ms
        assert restored.notifications_enabled == original.notifications_enabled

    def test_roundtrip_all_defaults(self):
        """Roundtrip with all defaults preserves everything."""
        original = AppConfig()
        d = original.to_dict()
        restored = AppConfig.from_dict(d)
        # Compare all flat dicts
        assert original.to_dict() == restored.to_dict()

    def test_to_dict_hotkeys_is_dict(self):
        """Hotkeys in to_dict is a plain dict (not frozen)."""
        cfg = AppConfig()
        d = cfg.to_dict()
        assert isinstance(d["hotkeys"], dict)
        # Should be modifiable (not frozen)
        d["hotkeys"]["new_action"] = "F12"


@pytest.mark.unit
class TestTypedConfigFunction:
    """Tests for the typed_config convenience function."""

    def test_returns_app_config(self):
        result = typed_config({})
        assert isinstance(result, AppConfig)

    def test_passes_values_through(self):
        result = typed_config({"language": "fr"})
        assert result.transcription.language == "fr"
