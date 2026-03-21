"""Typed configuration dataclasses for WhisprBar.

Provides frozen (immutable) dataclasses that replace the untyped Dict[str, Any]
configuration. Includes from_dict()/to_dict() for JSON serialization and
backwards compatibility with the existing cfg dict.
"""

from dataclasses import dataclass, field, asdict, fields
from typing import Any, Dict, Optional


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp a numeric value to [lo, hi]."""
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class AudioConfig:
    """Audio recording and processing settings."""

    device_name: Optional[str] = None
    use_vad: bool = True
    vad_energy_ratio: float = 0.05
    vad_bridge_ms: int = 300
    vad_min_energy_frames: int = 2
    vad_auto_stop_enabled: bool = False
    vad_auto_stop_silence_seconds: float = 2.0
    vad_calibration_enabled: bool = False
    vad_energy_floor: float = 0.0005
    vad_padding_ms: int = 200
    vad_min_output_ratio: float = 0.4
    vad_mode: int = 1
    noise_reduction_enabled: bool = True
    noise_reduction_strength: float = 0.7
    min_audio_energy: float = 0.0008
    audio_feedback_enabled: bool = True
    audio_feedback_volume: float = 0.3
    stop_tail_grace_ms: int = 500
    min_drain_timeout_ms: int = 100

    def validated(self) -> "AudioConfig":
        """Return a new AudioConfig with values clamped to safe ranges."""
        return AudioConfig(
            device_name=self.device_name,
            use_vad=self.use_vad,
            vad_energy_ratio=_clamp(self.vad_energy_ratio, 0.002, 0.3),
            vad_bridge_ms=int(_clamp(self.vad_bridge_ms, 0, 1000)),
            vad_min_energy_frames=int(_clamp(self.vad_min_energy_frames, 1, 10)),
            vad_auto_stop_enabled=self.vad_auto_stop_enabled,
            vad_auto_stop_silence_seconds=_clamp(self.vad_auto_stop_silence_seconds, 0.5, 30.0),
            vad_calibration_enabled=self.vad_calibration_enabled,
            vad_energy_floor=self.vad_energy_floor,
            vad_padding_ms=self.vad_padding_ms,
            vad_min_output_ratio=self.vad_min_output_ratio,
            vad_mode=int(_clamp(self.vad_mode, 0, 3)),
            noise_reduction_enabled=self.noise_reduction_enabled,
            noise_reduction_strength=_clamp(self.noise_reduction_strength, 0.0, 1.0),
            min_audio_energy=self.min_audio_energy,
            audio_feedback_enabled=self.audio_feedback_enabled,
            audio_feedback_volume=_clamp(self.audio_feedback_volume, 0.0, 1.0),
            stop_tail_grace_ms=int(_clamp(self.stop_tail_grace_ms, 0, 2000)),
            min_drain_timeout_ms=int(_clamp(self.min_drain_timeout_ms, 100, 500)),
        )


@dataclass(frozen=True)
class TranscriptionConfig:
    """Transcription backend settings."""

    language: str = "de"
    transcription_backend: str = "openai"
    faster_whisper_model: str = "medium"
    faster_whisper_device: str = "cpu"
    faster_whisper_compute_type: str = "int8"
    streaming_model: str = "tiny"


@dataclass(frozen=True)
class ChunkingConfig:
    """Audio chunking settings for long recordings."""

    chunking_enabled: bool = True
    chunk_duration_seconds: float = 30.0
    chunk_overlap_seconds: float = 2.0
    chunking_threshold_seconds: float = 60.0


@dataclass(frozen=True)
class PostprocessConfig:
    """Text postprocessing settings."""

    postprocess_enabled: bool = True
    postprocess_fix_spacing: bool = True
    postprocess_fix_capitalization: bool = True
    postprocess_fix_punctuation: bool = False


@dataclass(frozen=True)
class PasteConfig:
    """Auto-paste settings."""

    auto_paste_enabled: bool = True
    auto_paste_add_newline: bool = True
    auto_paste_add_space: bool = True
    paste_sequence: str = "auto"
    paste_delay_ms: int = 250

    def validated(self) -> "PasteConfig":
        """Return a new PasteConfig with values clamped to safe ranges."""
        return PasteConfig(
            auto_paste_enabled=self.auto_paste_enabled,
            auto_paste_add_newline=self.auto_paste_add_newline,
            auto_paste_add_space=self.auto_paste_add_space,
            paste_sequence=self.paste_sequence,
            paste_delay_ms=int(_clamp(self.paste_delay_ms, 0, 5000)),
        )


@dataclass(frozen=True)
class HotkeyConfig:
    """Hotkey settings."""

    hotkeys: Dict[str, Optional[str]] = field(default_factory=lambda: {
        "toggle_recording": "F9",
        "start_recording": None,
        "stop_recording": None,
        "open_settings": "F10",
        "show_history": None,
        "cancel_recording": None,
    })
    hotkey: str = "F9"  # Legacy compat


@dataclass(frozen=True)
class OverlayConfig:
    """Live overlay settings."""

    live_overlay_enabled: bool = False
    live_overlay_font_size: int = 14
    live_overlay_opacity: float = 0.9
    live_overlay_width: int = 400
    live_overlay_height: int = 150
    live_overlay_display_duration: float = 2.0
    live_overlay_x: Optional[int] = None
    live_overlay_y: Optional[int] = None


@dataclass(frozen=True)
class IndicatorConfig:
    """Recording indicator (animated popup) settings."""

    recording_indicator_enabled: bool = True
    recording_indicator_style: str = "soundwave"  # "soundwave", "pulse", "minimal"
    recording_indicator_position: str = "bottom-center"  # "bottom-center", "top-right", etc.
    recording_indicator_size: str = "normal"  # "small", "normal", "large"
    recording_indicator_opacity: float = 0.85


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration, composed of sub-configs."""

    audio: AudioConfig = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    postprocess: PostprocessConfig = field(default_factory=PostprocessConfig)
    paste: PasteConfig = field(default_factory=PasteConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    indicator: IndicatorConfig = field(default_factory=IndicatorConfig)

    # Top-level settings (not grouped)
    notifications_enabled: bool = False
    first_run_complete: bool = False
    check_updates: bool = True
    theme_mode: str = "auto"
    theme_preference: str = "auto"

    def validated(self) -> "AppConfig":
        """Return a new AppConfig with all sub-configs validated."""
        return AppConfig(
            audio=self.audio.validated(),
            transcription=self.transcription,
            chunking=self.chunking,
            postprocess=self.postprocess,
            paste=self.paste.validated(),
            hotkey=self.hotkey,
            overlay=self.overlay,
            indicator=self.indicator,
            notifications_enabled=self.notifications_enabled,
            first_run_complete=self.first_run_complete,
            check_updates=self.check_updates,
            theme_mode=self.theme_mode,
            theme_preference=self.theme_preference,
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AppConfig":
        """Create AppConfig from a flat config dictionary (like cfg).

        Maps flat keys to the correct sub-config dataclasses.
        Unknown keys are silently ignored for forward compatibility.
        """
        def _get(key: str, default: Any = None) -> Any:
            return d.get(key, default)

        audio = AudioConfig(
            device_name=_get("device_name"),
            use_vad=_get("use_vad", True),
            vad_energy_ratio=_get("vad_energy_ratio", 0.05),
            vad_bridge_ms=_get("vad_bridge_ms", 300),
            vad_min_energy_frames=_get("vad_min_energy_frames", 2),
            vad_auto_stop_enabled=_get("vad_auto_stop_enabled", False),
            vad_auto_stop_silence_seconds=_get("vad_auto_stop_silence_seconds", 2.0),
            vad_calibration_enabled=_get("vad_calibration_enabled", False),
            vad_energy_floor=_get("vad_energy_floor", 0.0005),
            vad_padding_ms=_get("vad_padding_ms", 200),
            vad_min_output_ratio=_get("vad_min_output_ratio", 0.4),
            vad_mode=_get("vad_mode", 1),
            noise_reduction_enabled=_get("noise_reduction_enabled", True),
            noise_reduction_strength=_get("noise_reduction_strength", 0.7),
            min_audio_energy=_get("min_audio_energy", 0.0008),
            audio_feedback_enabled=_get("audio_feedback_enabled", True),
            audio_feedback_volume=_get("audio_feedback_volume", 0.3),
            stop_tail_grace_ms=_get("stop_tail_grace_ms", 500),
            min_drain_timeout_ms=_get("min_drain_timeout_ms", 100),
        )

        transcription = TranscriptionConfig(
            language=_get("language", "de"),
            transcription_backend=_get("transcription_backend", "openai"),
            faster_whisper_model=_get("faster_whisper_model", "medium"),
            faster_whisper_device=_get("faster_whisper_device", "cpu"),
            faster_whisper_compute_type=_get("faster_whisper_compute_type", "int8"),
            streaming_model=_get("streaming_model", "tiny"),
        )

        chunking = ChunkingConfig(
            chunking_enabled=_get("chunking_enabled", True),
            chunk_duration_seconds=_get("chunk_duration_seconds", 30.0),
            chunk_overlap_seconds=_get("chunk_overlap_seconds", 2.0),
            chunking_threshold_seconds=_get("chunking_threshold_seconds", 60.0),
        )

        postprocess = PostprocessConfig(
            postprocess_enabled=_get("postprocess_enabled", True),
            postprocess_fix_spacing=_get("postprocess_fix_spacing", True),
            postprocess_fix_capitalization=_get("postprocess_fix_capitalization", True),
            postprocess_fix_punctuation=_get("postprocess_fix_punctuation", False),
        )

        paste = PasteConfig(
            auto_paste_enabled=_get("auto_paste_enabled", True),
            auto_paste_add_newline=_get("auto_paste_add_newline", True),
            auto_paste_add_space=_get("auto_paste_add_space", True),
            paste_sequence=_get("paste_sequence", "auto"),
            paste_delay_ms=_get("paste_delay_ms", 250),
        )

        hotkeys_dict = _get("hotkeys", {
            "toggle_recording": "F9",
            "start_recording": None,
            "stop_recording": None,
            "open_settings": "F10",
            "show_history": None,
            "cancel_recording": None,
        })
        hotkey_cfg = HotkeyConfig(
            hotkeys=hotkeys_dict,
            hotkey=_get("hotkey", "F9"),
        )

        overlay = OverlayConfig(
            live_overlay_enabled=_get("live_overlay_enabled", False),
            live_overlay_font_size=_get("live_overlay_font_size", 14),
            live_overlay_opacity=_get("live_overlay_opacity", 0.9),
            live_overlay_width=_get("live_overlay_width", 400),
            live_overlay_height=_get("live_overlay_height", 150),
            live_overlay_display_duration=_get("live_overlay_display_duration", 2.0),
            live_overlay_x=_get("live_overlay_x"),
            live_overlay_y=_get("live_overlay_y"),
        )

        indicator = IndicatorConfig(
            recording_indicator_enabled=_get("recording_indicator_enabled", True),
            recording_indicator_style=_get("recording_indicator_style", "soundwave"),
            recording_indicator_position=_get("recording_indicator_position", "bottom-center"),
            recording_indicator_size=_get("recording_indicator_size", "normal"),
            recording_indicator_opacity=_get("recording_indicator_opacity", 0.85),
        )

        return cls(
            audio=audio,
            transcription=transcription,
            chunking=chunking,
            postprocess=postprocess,
            paste=paste,
            hotkey=hotkey_cfg,
            overlay=overlay,
            indicator=indicator,
            notifications_enabled=_get("notifications_enabled", False),
            first_run_complete=_get("first_run_complete", False),
            check_updates=_get("check_updates", True),
            theme_mode=_get("theme_mode", "auto"),
            theme_preference=_get("theme_preference", "auto"),
        ).validated()

    def to_dict(self) -> Dict[str, Any]:
        """Convert back to a flat dictionary (compatible with cfg/JSON save).

        This is the inverse of from_dict() – produces the same flat key structure
        that the existing config system expects.
        """
        d: Dict[str, Any] = {}

        # Audio config
        for f in fields(self.audio):
            d[f.name] = getattr(self.audio, f.name)

        # Transcription config
        for f in fields(self.transcription):
            d[f.name] = getattr(self.transcription, f.name)

        # Chunking config
        for f in fields(self.chunking):
            d[f.name] = getattr(self.chunking, f.name)

        # Postprocess config
        for f in fields(self.postprocess):
            d[f.name] = getattr(self.postprocess, f.name)

        # Paste config
        for f in fields(self.paste):
            d[f.name] = getattr(self.paste, f.name)

        # Hotkey config
        d["hotkeys"] = dict(self.hotkey.hotkeys)
        d["hotkey"] = self.hotkey.hotkey

        # Overlay config
        for f in fields(self.overlay):
            d[f.name] = getattr(self.overlay, f.name)

        # Indicator config
        for f in fields(self.indicator):
            d[f.name] = getattr(self.indicator, f.name)

        # Top-level settings
        d["notifications_enabled"] = self.notifications_enabled
        d["first_run_complete"] = self.first_run_complete
        d["check_updates"] = self.check_updates
        d["theme_mode"] = self.theme_mode
        d["theme_preference"] = self.theme_preference

        return d


def typed_config(cfg_dict: Dict[str, Any]) -> AppConfig:
    """Convenience function: create a validated AppConfig from a cfg dict.

    Usage:
        from whisprbar.config import cfg
        from whisprbar.config_types import typed_config
        tc = typed_config(cfg)
        print(tc.audio.use_vad)  # True
    """
    return AppConfig.from_dict(cfg_dict)
