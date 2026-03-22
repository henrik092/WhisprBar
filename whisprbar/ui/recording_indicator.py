"""Animated recording indicator for WhisprBar.

Displays a wide, frameless, transparent popup bar with animated
visual feedback during recording and transcription:
- RECORDING: Soundwave bars that react to audio level
- PROCESSING: Pulsing dots
- TRANSCRIBING: Bouncing dots (typing animation)
- COMPLETE: Brief green checkmark, then fade out
- ERROR: Brief red X, then fade out

Technical: GTK3 DrawingArea + Cairo for custom rendering,
driven by GLib.timeout_add() at ~20fps.
"""

import math
import sys
import threading
import time
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
PHASE_COMPLETE = "complete"
PHASE_ERROR = "error"

# Base dimensions at 100% scale — wide bar (8:1 ratio)
BASE_WIDTH = 240
BASE_HEIGHT = 30

# Colors (RGBA)
COLOR_RECORDING = (0.91, 0.30, 0.24, 1.0)      # Red/orange
COLOR_RECORDING_BG = (0.15, 0.15, 0.18, 0.85)   # Dark background
COLOR_PROCESSING = (0.20, 0.60, 0.86, 1.0)       # Blue
COLOR_TRANSCRIBING = (0.20, 0.60, 0.86, 1.0)     # Blue
COLOR_COMPLETE = (0.18, 0.80, 0.44, 1.0)         # Green
COLOR_ERROR = (0.91, 0.30, 0.24, 1.0)            # Red

# Animation timing
FPS = 20
FRAME_MS = 1000 // FPS
COMPLETE_DISPLAY_MS = 1500
FADE_DURATION_MS = 400

# Position constants
POSITION_TOP_CENTER = "top-center"
POSITION_TOP_LEFT = "top-left"
POSITION_TOP_RIGHT = "top-right"
POSITION_BOTTOM_CENTER = "bottom-center"
POSITION_BOTTOM_LEFT = "bottom-left"
POSITION_BOTTOM_RIGHT = "bottom-right"
POSITION_DRAGGABLE = "draggable"


class RecordingIndicator:
    """Animated recording indicator window.

    Usage:
        indicator = RecordingIndicator(config_dict)
        indicator.show(phase="recording")
        indicator.set_audio_level(0.7)  # 0.0 - 1.0
        indicator.show(phase="processing")
        indicator.show(phase="complete")  # Auto-hides after delay
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

        # Dragging state
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Config
        cfg = cfg or {}
        self._enabled = cfg.get("recording_indicator_enabled", True)
        self._position = cfg.get("recording_indicator_position", POSITION_TOP_CENTER)
        self._scale = float(cfg.get("recording_indicator_scale", 1.0))
        self._opacity = cfg.get("recording_indicator_opacity", 0.85)
        self._custom_x = cfg.get("recording_indicator_x")
        self._custom_y = cfg.get("recording_indicator_y")

        # Clamp scale to valid range
        self._scale = max(0.1, min(2.0, self._scale))

        # Compute actual pixel dimensions
        self._width = max(16, int(BASE_WIDTH * self._scale))
        self._height = max(4, int(BASE_HEIGHT * self._scale))

    def show(self, phase: str = PHASE_RECORDING) -> None:
        """Show or update the indicator."""
        if not self._enabled or not GTK_AVAILABLE:
            return
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

            # Auto-hide for complete/error phases
            if phase in (PHASE_COMPLETE, PHASE_ERROR):
                self._hide_timer_id = GLib.timeout_add(
                    COMPLETE_DISPLAY_MS, self._start_fade_out
                )

        return False  # Don't repeat GLib.idle_add

    def _hide_on_main_thread(self) -> bool:
        """Must be called from GTK main thread."""
        with self._lock:
            self._phase = PHASE_HIDDEN
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

    def _draw_recording(self, cr, w, h, alpha) -> None:
        """Draw soundwave bars that react to audio level."""
        r, g, b, _ = COLOR_RECORDING
        t = self._tick_count / FPS  # Time in seconds
        level = self._audio_level

        num_bars = 12
        usable_w = w * 0.85
        bar_width = usable_w / (num_bars * 1.8)
        gap = bar_width * 0.8
        total_w = num_bars * bar_width + (num_bars - 1) * gap
        start_x = (w - total_w) / 2
        max_h = h * 0.75
        min_h = h * 0.1

        for i in range(num_bars):
            phase = i * 0.7
            wave = math.sin(t * 3.5 + phase) * 0.5 + 0.5
            bar_h = min_h + (max_h - min_h) * (0.3 + 0.7 * level) * wave

            x = start_x + i * (bar_width + gap)
            y = (h - bar_h) / 2

            cap_r = bar_width / 2
            self._draw_rounded_rect(cr, x, y, bar_width, bar_h, cap_r)
            cr.set_source_rgba(r, g, b, alpha * (0.5 + 0.5 * wave))
            cr.fill()

    def _draw_processing(self, cr, w, h, alpha) -> None:
        """Draw softly pulsing dots."""
        r, g, b, _ = COLOR_PROCESSING
        t = self._tick_count / FPS
        num_dots = 5
        dot_r = min(w, h) * 0.06
        gap = dot_r * 3.5
        total_w = (num_dots - 1) * gap
        start_x = (w - total_w) / 2
        cy = h / 2

        for i in range(num_dots):
            phase = i * 0.5
            scale = 0.6 + 0.4 * math.sin(t * 2.5 + phase)
            x = start_x + i * gap
            cr.arc(x, cy, dot_r * scale, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, alpha * scale)
            cr.fill()

    def _draw_transcribing(self, cr, w, h, alpha) -> None:
        """Draw running dot indicator (typing animation)."""
        r, g, b, _ = COLOR_TRANSCRIBING
        t = self._tick_count / FPS
        num_dots = 3
        dot_r = min(w, h) * 0.07
        gap = dot_r * 4
        total_w = (num_dots - 1) * gap
        start_x = (w - total_w) / 2
        cy = h / 2

        for i in range(num_dots):
            phase = i * 0.4
            bounce = abs(math.sin(t * 3 + phase)) * min(w, h) * 0.12
            x = start_x + i * gap
            y = cy - bounce
            cr.arc(x, y, dot_r, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, alpha * 0.9)
            cr.fill()

    def _draw_complete(self, cr, w, h, alpha) -> None:
        """Draw checkmark."""
        r, g, b, _ = COLOR_COMPLETE
        cx, cy = w / 2, h / 2
        size = min(w, h) * 0.25

        cr.set_line_width(size * 0.25)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        cr.move_to(cx - size * 0.5, cy)
        cr.line_to(cx - size * 0.1, cy + size * 0.4)
        cr.line_to(cx + size * 0.6, cy - size * 0.35)
        cr.stroke()

    def _draw_error(self, cr, w, h, alpha) -> None:
        """Draw X mark."""
        r, g, b, _ = COLOR_ERROR
        cx, cy = w / 2, h / 2
        size = min(w, h) * 0.2

        cr.set_line_width(size * 0.25)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        cr.move_to(cx - size, cy - size)
        cr.line_to(cx + size, cy + size)
        cr.stroke()

        cr.move_to(cx + size, cy - size)
        cr.line_to(cx - size, cy + size)
        cr.stroke()

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


def show_recording_indicator(phase: str = PHASE_RECORDING, cfg: Optional[dict] = None) -> None:
    """Show the recording indicator with the given phase."""
    indicator = get_recording_indicator(cfg)
    indicator.show(phase)


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
