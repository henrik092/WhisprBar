"""Animated recording indicator for WhisprBar.

Displays a wide, frameless, transparent popup bar with animated
visual feedback during recording and transcription:
- RECORDING: Soundwave bars + elapsed timer (e.g. "Recording  0:05")
- PROCESSING: Pulsing dots + "Processing..." label
- TRANSCRIBING: Bouncing dots + "Transcribing..." label
- PASTING: Brief clipboard icon + "Pasting..." label
- COMPLETE: Green checkmark + "Done! (15 words)" label, then fade out
- ERROR: Red X + error message label, then fade out

Technical: GTK3 DrawingArea + Cairo for custom rendering,
driven by GLib.timeout_add() at ~20fps.
"""

import math
import random
import sys
import threading
import time
from collections import deque
from typing import Optional

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib
    GTK_AVAILABLE = True
except Exception:
    GTK_AVAILABLE = False


# Animation phases (mirrors state.AppPhase but UI-specific)
PHASE_HIDDEN = "hidden"
PHASE_RECORDING = "recording"
PHASE_PROCESSING = "processing"
PHASE_TRANSCRIBING = "transcribing"
PHASE_REWRITING = "rewriting"
PHASE_PASTING = "pasting"
PHASE_COMPLETE = "complete"
PHASE_ERROR = "error"

# Base dimensions at 100% scale — wider bar to accommodate text labels
BASE_WIDTH = 320
BASE_HEIGHT = 32

# Colors (RGBA)
COLOR_RECORDING = (0.91, 0.30, 0.24, 1.0)      # Red/orange
COLOR_RECORDING_BG = (0.15, 0.15, 0.18, 0.85)   # Dark background
COLOR_PROCESSING = (0.20, 0.60, 0.86, 1.0)       # Blue
COLOR_TRANSCRIBING = (0.20, 0.60, 0.86, 1.0)     # Blue
COLOR_PASTING = (0.60, 0.40, 0.90, 1.0)          # Purple
COLOR_COMPLETE = (0.18, 0.80, 0.44, 1.0)         # Green
COLOR_ERROR = (0.91, 0.30, 0.24, 1.0)            # Red
COLOR_TEXT = (0.92, 0.92, 0.95, 1.0)             # Light text
COLOR_TEXT_DIM = (0.65, 0.65, 0.70, 1.0)         # Dimmer text for secondary info

# Animation timing
FPS = 30
FRAME_MS = 1000 // FPS
COMPLETE_DISPLAY_MS = 1500
PASTING_DISPLAY_MS = 800
FADE_DURATION_MS = 400

# Position constants
POSITION_TOP_CENTER = "top-center"
POSITION_TOP_LEFT = "top-left"
POSITION_TOP_RIGHT = "top-right"
POSITION_BOTTOM_CENTER = "bottom-center"
POSITION_BOTTOM_LEFT = "bottom-left"
POSITION_BOTTOM_RIGHT = "bottom-right"
POSITION_DRAGGABLE = "draggable"


def _is_flow_indicator_enabled(cfg: Optional[dict]) -> bool:
    """Return whether Flow Mode should use the Flow-Bar renderer."""
    return bool((cfg or {}).get("flow_mode_enabled", False))


def _flow_phase_label(phase: str) -> str:
    """Map internal indicator phases to compact Flow-Bar labels."""
    return {
        PHASE_RECORDING: "Listening",
        PHASE_PROCESSING: "Processing",
        PHASE_TRANSCRIBING: "Transcribing",
        PHASE_REWRITING: "Rewriting",
        PHASE_PASTING: "Pasting",
        PHASE_COMPLETE: "Done",
        PHASE_ERROR: "Error",
    }.get(phase, "Working")


def _flow_hotkey_label(cfg: Optional[dict]) -> str:
    """Resolve the active recording hotkey label for the Flow-Bar hint."""
    try:
        from whisprbar.hotkeys import hotkey_to_label
        config = cfg or {}
        hotkeys = config.get("hotkeys") or {}
        binding = hotkeys.get("toggle_recording") or config.get("hotkey")
        return hotkey_to_label(binding) if binding else ""
    except Exception:
        return ""


class RecordingIndicator:
    """Animated recording indicator window with text labels.

    Usage:
        indicator = RecordingIndicator(config_dict)
        indicator.show(phase="recording")
        indicator.set_audio_level(0.7)  # 0.0 - 1.0
        indicator.show(phase="processing")
        indicator.show(phase="complete", info="15 words")
        indicator.hide()
    """

    def __init__(self, cfg: Optional[dict] = None) -> None:
        self._window: Optional[Gtk.Window] = None
        self._drawing_area: Optional[Gtk.DrawingArea] = None
        self._phase = PHASE_HIDDEN
        self._audio_level = 0.0
        self._tick_count = 0
        self._fade_alpha = 1.0
        self._timer_id: Optional[int] = None
        self._hide_timer_id: Optional[int] = None
        self._lock = threading.Lock()

        # Recording timer
        self._recording_start_time: Optional[float] = None

        # Info text for complete/error phases (e.g. word count or error message)
        self._info_text = ""

        # Dragging state
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Config
        cfg = cfg or {}
        self._enabled = cfg.get("recording_indicator_enabled", True)
        self._position = cfg.get("recording_indicator_position", POSITION_TOP_CENTER)
        self._opacity = cfg.get("recording_indicator_opacity", 0.85)
        self._custom_x = cfg.get("recording_indicator_x")
        self._custom_y = cfg.get("recording_indicator_y")

        # Read width/height directly from config (with clamping)
        self._width = max(60, min(600, int(cfg.get("recording_indicator_width", BASE_WIDTH))))
        self._height = max(10, min(100, int(cfg.get("recording_indicator_height", BASE_HEIGHT))))

        # Smooth audio level (lerp toward target each frame)
        self._smooth_level = 0.0

        # Per-bar state for gradient bars (smooth interpolation)
        self._num_bars = 24
        self._bar_heights = [0.0] * self._num_bars
        # Randomized per-bar phase offsets for organic feel
        self._bar_phases = [random.uniform(0, 2 * math.pi) for _ in range(self._num_bars)]

        # Siri wave parameters (5 overlapping curves)
        self._wave_curves = [
            {"amp_mult": 1.0, "freq": 1.5, "phase_speed": 2.2, "opacity": 0.6},
            {"amp_mult": 0.7, "freq": 2.2, "phase_speed": 1.8, "opacity": 0.35},
            {"amp_mult": 0.5, "freq": 3.0, "phase_speed": 2.8, "opacity": 0.2},
            {"amp_mult": 0.85, "freq": 1.8, "phase_speed": -1.5, "opacity": 0.25},
            {"amp_mult": 0.3, "freq": 3.5, "phase_speed": 3.2, "opacity": 0.12},
        ]

    def show(self, phase: str = PHASE_RECORDING, info: str = "") -> None:
        """Show or update the indicator.

        Args:
            phase: Animation phase to display.
            info: Optional info text (e.g. word count for complete, error msg for error).
        """
        if not self._enabled or not GTK_AVAILABLE:
            return
        self._info_text = info
        if phase == PHASE_RECORDING:
            self._recording_start_time = time.monotonic()
        elif phase != PHASE_RECORDING and self._phase != phase:
            # Keep start time if still recording, clear otherwise
            if self._phase != PHASE_RECORDING:
                self._recording_start_time = None
        GLib.idle_add(self._show_on_main_thread, phase)

    def hide(self) -> None:
        """Hide the indicator."""
        if not GTK_AVAILABLE:
            return
        GLib.idle_add(self._hide_on_main_thread)

    def set_audio_level(self, level: float) -> None:
        """Set current audio level for soundwave animation."""
        self._audio_level = max(0.0, min(1.0, level))

    def _show_on_main_thread(self, phase: str) -> bool:
        """Must be called from GTK main thread."""
        with self._lock:
            old_phase = self._phase
            self._phase = phase
            self._fade_alpha = 1.0

            # Cancel pending hide timer
            if self._hide_timer_id is not None:
                GLib.source_remove(self._hide_timer_id)
                self._hide_timer_id = None

            # Create window if needed
            if self._window is None:
                self._create_window()

            self._window.show_all()

            # Start animation timer if not running
            if self._timer_id is None:
                self._timer_id = GLib.timeout_add(FRAME_MS, self._tick)

            # Auto-hide for complete/error/pasting phases
            if phase in (PHASE_COMPLETE, PHASE_ERROR):
                self._hide_timer_id = GLib.timeout_add(
                    COMPLETE_DISPLAY_MS, self._start_fade_out
                )
            elif phase == PHASE_PASTING:
                self._hide_timer_id = GLib.timeout_add(
                    PASTING_DISPLAY_MS, self._start_fade_out
                )

        return False  # Don't repeat GLib.idle_add

    def _hide_on_main_thread(self) -> bool:
        """Must be called from GTK main thread."""
        with self._lock:
            self._phase = PHASE_HIDDEN
            self._recording_start_time = None
            if self._timer_id is not None:
                GLib.source_remove(self._timer_id)
                self._timer_id = None
            if self._hide_timer_id is not None:
                GLib.source_remove(self._hide_timer_id)
                self._hide_timer_id = None
            if self._window is not None:
                self._window.hide()
        return False

    def _create_window(self) -> None:
        """Create the transparent overlay window."""
        window = Gtk.Window(type=Gtk.WindowType.POPUP)
        window.set_decorated(False)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.set_keep_above(True)
        window.set_accept_focus(False)
        window.set_default_size(self._width, self._height)
        window.resize(self._width, self._height)
        window.set_resizable(False)

        # Enable transparency
        screen = window.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            window.set_visual(visual)
        window.set_app_paintable(True)

        # Drawing area
        drawing_area = Gtk.DrawingArea()
        drawing_area.set_size_request(self._width, self._height)
        drawing_area.connect("draw", self._on_draw)
        window.add(drawing_area)

        # Enable dragging for "draggable" position mode
        if self._position == POSITION_DRAGGABLE:
            window.set_accept_focus(True)
            window.add_events(
                Gdk.EventMask.BUTTON_PRESS_MASK
                | Gdk.EventMask.BUTTON_RELEASE_MASK
                | Gdk.EventMask.POINTER_MOTION_MASK
            )
            window.connect("button-press-event", self._on_button_press)
            window.connect("button-release-event", self._on_button_release)
            window.connect("motion-notify-event", self._on_motion_notify)

        # Position
        self._position_window(window, screen)

        self._window = window
        self._drawing_area = drawing_area

    def _position_window(self, window, screen) -> None:
        """Position the window based on config."""
        # If draggable and custom position saved, use that
        if self._position == POSITION_DRAGGABLE and self._custom_x is not None and self._custom_y is not None:
            window.move(int(self._custom_x), int(self._custom_y))
            return

        display = screen.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            return
        geom = monitor.get_geometry()
        margin = 20

        pos = self._position
        if pos == POSITION_TOP_CENTER:
            x = geom.x + (geom.width - self._width) // 2
            y = geom.y + margin
        elif pos == POSITION_TOP_LEFT:
            x = geom.x + margin
            y = geom.y + margin
        elif pos == POSITION_TOP_RIGHT:
            x = geom.x + geom.width - self._width - margin
            y = geom.y + margin
        elif pos == POSITION_BOTTOM_LEFT:
            x = geom.x + margin
            y = geom.y + geom.height - self._height - margin - 60
        elif pos == POSITION_BOTTOM_RIGHT:
            x = geom.x + geom.width - self._width - margin
            y = geom.y + geom.height - self._height - margin - 60
        elif pos == POSITION_DRAGGABLE:
            # Default to center of screen
            x = geom.x + (geom.width - self._width) // 2
            y = geom.y + (geom.height - self._height) // 2
        else:
            # default: bottom-center
            x = geom.x + (geom.width - self._width) // 2
            y = geom.y + geom.height - self._height - margin - 60

        window.move(x, y)

    def _on_button_press(self, widget, event) -> bool:
        if event.button == 1:
            self._dragging = True
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
        return False

    def _on_button_release(self, widget, event) -> bool:
        if event.button == 1 and self._dragging:
            self._dragging = False
            # Save position to config
            if self._window:
                x, y = self._window.get_position()
                self._custom_x = x
                self._custom_y = y
                try:
                    from whisprbar.config import cfg as app_cfg, save_config
                    app_cfg["recording_indicator_x"] = x
                    app_cfg["recording_indicator_y"] = y
                    save_config()
                except Exception:
                    pass
        return False

    def _on_motion_notify(self, widget, event) -> bool:
        if self._dragging and self._window:
            dx = event.x_root - self._drag_start_x
            dy = event.y_root - self._drag_start_y
            x, y = self._window.get_position()
            self._window.move(int(x + dx), int(y + dy))
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
        return False

    def _tick(self) -> bool:
        """Animation tick (~20fps). Returns True to keep timer alive."""
        self._tick_count += 1
        # Smooth audio level interpolation (fast attack, slower release)
        target = self._audio_level
        if target > self._smooth_level:
            self._smooth_level += (target - self._smooth_level) * 0.35  # fast attack
        else:
            self._smooth_level += (target - self._smooth_level) * 0.10  # slow release
        if self._drawing_area is not None:
            self._drawing_area.queue_draw()
        return self._phase != PHASE_HIDDEN

    def _start_fade_out(self) -> bool:
        """Begin fade-out animation."""
        self._hide_timer_id = GLib.timeout_add(FRAME_MS, self._fade_tick)
        return False  # Don't repeat

    def _fade_tick(self) -> bool:
        """Fade-out animation tick."""
        self._fade_alpha -= FRAME_MS / FADE_DURATION_MS
        if self._fade_alpha <= 0:
            self._fade_alpha = 0
            self._hide_on_main_thread()
            return False
        if self._drawing_area is not None:
            self._drawing_area.queue_draw()
        return True

    # =========================================================================
    # Drawing
    # =========================================================================

    def _on_draw(self, widget, cr) -> bool:
        """Cairo draw callback - renders the current animation frame."""
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        alpha = self._fade_alpha * self._opacity

        # Background with rounded corners (proportional to height)
        radius = min(h // 2, 12)
        self._draw_rounded_rect(cr, 0, 0, w, h, radius)
        r, g, b, _ = COLOR_RECORDING_BG
        cr.set_source_rgba(r, g, b, alpha)
        cr.fill()

        # Draw phase-specific animation
        if self._phase == PHASE_RECORDING:
            self._draw_recording(cr, w, h, alpha)
        elif self._phase == PHASE_PROCESSING:
            self._draw_processing(cr, w, h, alpha)
        elif self._phase == PHASE_TRANSCRIBING:
            self._draw_transcribing(cr, w, h, alpha)
        elif self._phase == PHASE_PASTING:
            self._draw_pasting(cr, w, h, alpha)
        elif self._phase == PHASE_COMPLETE:
            self._draw_complete(cr, w, h, alpha)
        elif self._phase == PHASE_ERROR:
            self._draw_error(cr, w, h, alpha)

        return False

    def _draw_rounded_rect(self, cr, x, y, w, h, r) -> None:
        """Draw a rounded rectangle path."""
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _draw_text(self, cr, text: str, x: float, y: float, alpha: float,
                   color: tuple = COLOR_TEXT, font_size: float = 0.0,
                   bold: bool = False) -> None:
        """Draw text at position using Cairo.

        Args:
            cr: Cairo context
            text: Text to draw
            x: X position
            y: Y center position (text is vertically centered)
            alpha: Opacity multiplier
            color: RGBA color tuple
            font_size: Font size in pixels (0 = auto based on bar height)
            bold: Use bold weight
        """
        if not text:
            return
        r, g, b, _ = color
        cr.set_source_rgba(r, g, b, alpha)

        if font_size <= 0:
            font_size = self._height * 0.38

        weight = 1 if bold else 0  # CAIRO_FONT_WEIGHT_BOLD / NORMAL
        cr.select_font_face("Sans", 0, weight)
        cr.set_font_size(font_size)

        # Get text extents for vertical centering
        extents = cr.text_extents(text)
        text_y = y + extents.height / 2

        cr.move_to(x, text_y)
        cr.show_text(text)

    def _get_elapsed_str(self) -> str:
        """Get elapsed recording time as M:SS string."""
        if self._recording_start_time is None:
            return "0:00"
        elapsed = time.monotonic() - self._recording_start_time
        minutes = int(elapsed) // 60
        seconds = int(elapsed) % 60
        return f"{minutes}:{seconds:02d}"

    def _draw_recording(self, cr, w, h, alpha) -> None:
        """Draw premium recording animation: Siri waves + gradient bars + text."""
        t = self._tick_count / FPS  # Time in seconds
        level = self._smooth_level

        # Layout: [animation area ~80%] [timer ~20%]
        anim_w = w * 0.78
        cy = h / 2

        # Save state and clip animation area to pill shape
        cr.save()
        self._draw_rounded_rect(cr, 0, 0, anim_w, h, min(h // 2, 12))
        cr.clip()

        # === Layer 1: Siri-style flowing sine curves (background atmosphere) ===
        self._draw_siri_waves(cr, anim_w, h, t, level, alpha)

        # === Layer 2: Gradient bars with glow (foreground) ===
        self._draw_gradient_bars(cr, anim_w, h, t, level, alpha)

        cr.restore()

        # === Layer 3: Timer only (compact, right-aligned) ===
        elapsed = self._get_elapsed_str()
        timer_font_size = self._height * 0.28
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(timer_font_size)
        timer_extents = cr.text_extents(elapsed)
        timer_x = w - timer_extents.width - w * 0.04
        self._draw_text(cr, elapsed, timer_x, cy, alpha,
                        color=COLOR_TEXT_DIM, font_size=timer_font_size)

    def _draw_siri_waves(self, cr, w, h, t, level, alpha) -> None:
        """Draw overlapping Siri-style sine curves as background atmosphere."""
        cy = h / 2
        max_amp = h * 0.35

        for curve in self._wave_curves:
            amp = max_amp * curve["amp_mult"] * (0.15 + 0.85 * level)
            freq = curve["freq"]
            phase = t * curve["phase_speed"]
            curve_alpha = alpha * curve["opacity"]

            if curve_alpha < 0.01:
                continue

            # Draw filled sine curve (mirrored around center)
            cr.new_path()
            cr.move_to(0, cy)

            steps = int(w)
            for i in range(steps + 1):
                x = i
                # Normalized position (0 to 1)
                nx = x / w
                # Attenuation: fade to zero at edges (smooth pill containment)
                # Using a smooth bell curve: sin^2 creates natural fade
                edge_fade = math.sin(nx * math.pi) ** 2
                y_offset = amp * math.sin(freq * nx * 2 * math.pi - phase) * edge_fade
                cr.line_to(x, cy - y_offset)

            # Mirror back along bottom
            for i in range(steps, -1, -1):
                x = i
                nx = x / w
                edge_fade = math.sin(nx * math.pi) ** 2
                y_offset = amp * math.sin(freq * nx * 2 * math.pi - phase) * edge_fade
                cr.line_to(x, cy + y_offset * 0.6)  # Slightly asymmetric for organic feel

            cr.close_path()

            # Gradient fill: warm coral left → hot red center → cool magenta right
            try:
                import cairo as _cairo
                pat = _cairo.LinearGradient(0, 0, w, 0)
                pat.add_color_stop_rgba(0.0, 1.0, 0.45, 0.35, curve_alpha)
                pat.add_color_stop_rgba(0.5, 0.91, 0.30, 0.24, curve_alpha)
                pat.add_color_stop_rgba(1.0, 0.75, 0.25, 0.55, curve_alpha)
                cr.set_source(pat)
            except Exception:
                cr.set_source_rgba(0.91, 0.30, 0.24, curve_alpha)
            cr.fill()

    def _draw_gradient_bars(self, cr, w, h, t, level, alpha) -> None:
        """Draw center-aligned gradient bars with glow effect."""
        cy = h / 2
        num_bars = self._num_bars
        max_bar_h = h * 0.75
        min_bar_h = h * 0.06

        # Bar geometry
        total_bar_area = w * 0.92
        bar_spacing = total_bar_area / num_bars
        bar_width = bar_spacing * 0.55
        start_x = (w - total_bar_area) / 2 + bar_spacing * 0.25

        # Update bar heights with smooth interpolation
        for i in range(num_bars):
            # Multiple sine waves for organic movement per bar
            phase = self._bar_phases[i]
            wave1 = math.sin(t * 3.0 + phase) * 0.5 + 0.5
            wave2 = math.sin(t * 1.7 + phase * 1.5) * 0.3 + 0.5
            wave3 = math.sin(t * 5.2 + phase * 0.7) * 0.2 + 0.5
            combined = (wave1 * 0.5 + wave2 * 0.3 + wave3 * 0.2)

            target_h = min_bar_h + (max_bar_h - min_bar_h) * (0.08 + 0.92 * level) * combined
            # Smooth lerp toward target
            self._bar_heights[i] += (target_h - self._bar_heights[i]) * 0.18

        # Draw glow layer first (larger, more transparent)
        for i in range(num_bars):
            bar_h = self._bar_heights[i]
            x = start_x + i * bar_spacing
            glow_extra = bar_width * 0.5
            glow_h = bar_h + glow_extra
            glow_x = x - glow_extra / 2
            glow_w = bar_width + glow_extra
            glow_y = cy - glow_h / 2

            # Gradient position (0-1 across all bars)
            frac = i / max(1, num_bars - 1)
            r, g, b = self._gradient_color(frac)

            cap_r = glow_w / 2
            self._draw_rounded_rect(cr, glow_x, glow_y, glow_w, glow_h, cap_r)
            cr.set_source_rgba(r, g, b, alpha * 0.12)
            cr.fill()

        # Draw crisp bars on top
        for i in range(num_bars):
            bar_h = self._bar_heights[i]
            x = start_x + i * bar_spacing
            y = cy - bar_h / 2

            frac = i / max(1, num_bars - 1)
            r, g, b = self._gradient_color(frac)

            cap_r = bar_width / 2
            self._draw_rounded_rect(cr, x, y, bar_width, bar_h, cap_r)
            # Brightness varies slightly with height for depth
            brightness = 0.7 + 0.3 * (bar_h / max_bar_h)
            cr.set_source_rgba(r, g, b, alpha * brightness)
            cr.fill()

    @staticmethod
    def _gradient_color(frac: float) -> tuple:
        """Get gradient color for position 0.0-1.0 across the bar.

        Warm coral → hot red → cool magenta/purple
        """
        if frac < 0.5:
            t = frac * 2.0  # 0 to 1 in first half
            r = 1.0 - t * 0.15
            g = 0.45 - t * 0.18
            b = 0.35 + t * 0.05
        else:
            t = (frac - 0.5) * 2.0  # 0 to 1 in second half
            r = 0.85 - t * 0.15
            g = 0.27 - t * 0.05
            b = 0.40 + t * 0.20
        return (r, g, b)

    # =========================================================================
    # Unified layout constants for all non-recording phases
    # Icon on the left, label centered, consistent sizing
    # =========================================================================

    def _phase_layout(self, w, h):
        """Return consistent layout metrics for icon+label phases."""
        cy = h / 2
        icon_x = w * 0.06              # Icon left edge
        icon_size = h * 0.32           # Icon fits within bar height
        label_font = self._height * 0.30  # Consistent font size
        label_x = w * 0.18             # Label starts after icon area
        return cy, icon_x, icon_size, label_font, label_x

    def _draw_processing(self, cr, w, h, alpha) -> None:
        """Draw pulsing dots + 'Processing...' label."""
        r, g, b, _ = COLOR_PROCESSING
        t = self._tick_count / FPS
        cy, icon_x, icon_size, label_font, label_x = self._phase_layout(w, h)

        # 3 pulsing dots as icon
        num_dots = 3
        dot_r = icon_size * 0.28
        gap = dot_r * 2.5
        total_w = (num_dots - 1) * gap
        sx = icon_x + (icon_size - total_w) / 2

        for i in range(num_dots):
            phase = i * 0.6
            scale = 0.6 + 0.4 * math.sin(t * 2.5 + phase)
            cr.arc(sx + i * gap, cy, dot_r * scale, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, alpha * (0.5 + 0.5 * scale))
            cr.fill()

        # Label with animated dots
        dot_count = int(t * 2) % 4
        label = "Processing" + "." * dot_count
        self._draw_text(cr, label, label_x, cy, alpha,
                        color=COLOR_TEXT, font_size=label_font)

    def _draw_transcribing(self, cr, w, h, alpha) -> None:
        """Draw bouncing dots + 'Transcribing...' label."""
        r, g, b, _ = COLOR_TRANSCRIBING
        t = self._tick_count / FPS
        cy, icon_x, icon_size, label_font, label_x = self._phase_layout(w, h)

        # 3 bouncing dots as icon
        num_dots = 3
        dot_r = icon_size * 0.28
        gap = dot_r * 2.5
        total_w = (num_dots - 1) * gap
        sx = icon_x + (icon_size - total_w) / 2

        for i in range(num_dots):
            phase = i * 0.5
            bounce = abs(math.sin(t * 3 + phase)) * icon_size * 0.4
            cr.arc(sx + i * gap, cy - bounce, dot_r, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, alpha * 0.9)
            cr.fill()

        # Label with animated dots
        dot_count = int(t * 2) % 4
        label = "Transcribing" + "." * dot_count
        self._draw_text(cr, label, label_x, cy, alpha,
                        color=COLOR_TEXT, font_size=label_font)

    def _draw_pasting(self, cr, w, h, alpha) -> None:
        """Draw clipboard icon + 'Pasting...' label."""
        r, g, b, _ = COLOR_PASTING
        t = self._tick_count / FPS
        cy, icon_x, icon_size, label_font, label_x = self._phase_layout(w, h)

        # Simple clipboard icon scaled to icon_size
        cr.set_line_width(icon_size * 0.10)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        # Clipboard body
        bx = icon_x
        by = cy - icon_size * 0.4
        bw = icon_size * 0.75
        bh = icon_size * 0.85
        br = icon_size * 0.1
        self._draw_rounded_rect(cr, bx, by + icon_size * 0.12, bw, bh, br)
        cr.stroke()

        # Clip at top
        clip_w = icon_size * 0.35
        clip_x = bx + (bw - clip_w) / 2
        cr.rectangle(clip_x, by, clip_w, icon_size * 0.18)
        cr.fill()

        # Lines on clipboard
        cr.set_line_width(icon_size * 0.06)
        line_y1 = by + bh * 0.45
        line_y2 = by + bh * 0.62
        cr.move_to(bx + bw * 0.22, line_y1)
        cr.line_to(bx + bw * 0.78, line_y1)
        cr.stroke()
        cr.move_to(bx + bw * 0.22, line_y2)
        cr.line_to(bx + bw * 0.58, line_y2)
        cr.stroke()

        # Label with animated dots
        dot_count = int(t * 3) % 4
        label = "Pasting" + "." * dot_count
        self._draw_text(cr, label, label_x, cy, alpha,
                        color=COLOR_TEXT, font_size=label_font)

    def _draw_complete(self, cr, w, h, alpha) -> None:
        """Draw checkmark + 'Done!' label with optional word count."""
        r, g, b, _ = COLOR_COMPLETE
        cy, icon_x, icon_size, label_font, label_x = self._phase_layout(w, h)

        # Checkmark icon
        cr.set_line_width(icon_size * 0.22)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        cx = icon_x + icon_size * 0.35
        cr.move_to(cx - icon_size * 0.25, cy)
        cr.line_to(cx, cy + icon_size * 0.25)
        cr.line_to(cx + icon_size * 0.35, cy - icon_size * 0.25)
        cr.stroke()

        # "Done!" label
        self._draw_text(cr, "Done!", label_x, cy, alpha,
                        color=COLOR_COMPLETE, bold=True, font_size=label_font)

        # Info text (word count) after label
        if self._info_text:
            cr.select_font_face("Sans", 0, 1)
            cr.set_font_size(label_font)
            done_ext = cr.text_extents("Done! ")
            info_x = label_x + done_ext.width + w * 0.01
            info_font = label_font * 0.88
            self._draw_text(cr, self._info_text, info_x, cy, alpha * 0.7,
                            color=COLOR_TEXT_DIM, font_size=info_font)

    def _draw_error(self, cr, w, h, alpha) -> None:
        """Draw X mark + error label."""
        r, g, b, _ = COLOR_ERROR
        cy, icon_x, icon_size, label_font, label_x = self._phase_layout(w, h)

        # X icon
        cr.set_line_width(icon_size * 0.22)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        cx = icon_x + icon_size * 0.35
        s = icon_size * 0.25
        cr.move_to(cx - s, cy - s)
        cr.line_to(cx + s, cy + s)
        cr.stroke()
        cr.move_to(cx + s, cy - s)
        cr.line_to(cx - s, cy + s)
        cr.stroke()

        # Error label
        label = self._info_text if self._info_text else "Error"
        self._draw_text(cr, label, label_x, cy, alpha,
                        color=COLOR_ERROR, bold=True, font_size=label_font)

    def destroy(self) -> None:
        """Clean up the window."""
        if GTK_AVAILABLE:
            GLib.idle_add(self._destroy_on_main_thread)

    def _destroy_on_main_thread(self) -> bool:
        self._hide_on_main_thread()
        if self._window is not None:
            self._window.destroy()
            self._window = None
            self._drawing_area = None
        return False


# Module-level singleton for easy access
_indicator: Optional[RecordingIndicator] = None
_indicator_lock = threading.Lock()


def get_recording_indicator(cfg: Optional[dict] = None) -> RecordingIndicator:
    """Get or create the recording indicator singleton."""
    global _indicator
    with _indicator_lock:
        if _indicator is None:
            _indicator = RecordingIndicator(cfg)
        return _indicator


def show_recording_indicator(phase: str = PHASE_RECORDING, cfg: Optional[dict] = None,
                             info: str = "") -> None:
    """Show the recording indicator with the given phase.

    Args:
        phase: Animation phase to display.
        cfg: Configuration dict (used on first call to create the indicator).
        info: Optional info text (e.g. "15 words" for complete, error msg for error).
    """
    indicator = get_recording_indicator(cfg)
    indicator.show(phase, info=info)


def hide_recording_indicator() -> None:
    """Hide the recording indicator."""
    global _indicator
    with _indicator_lock:
        if _indicator is not None:
            _indicator.hide()


def reset_recording_indicator() -> None:
    """Destroy the current indicator so a new one is created with fresh config."""
    global _indicator
    with _indicator_lock:
        if _indicator is not None:
            _indicator.destroy()
            _indicator = None


def update_audio_level(level: float) -> None:
    """Update the audio level for the soundwave animation."""
    global _indicator
    with _indicator_lock:
        if _indicator is not None:
            _indicator.set_audio_level(level)
