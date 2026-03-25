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
FPS = 20
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
        self._scale = float(cfg.get("recording_indicator_scale", 1.0))
        self._opacity = cfg.get("recording_indicator_opacity", 0.85)
        self._custom_x = cfg.get("recording_indicator_x")
        self._custom_y = cfg.get("recording_indicator_y")

        # Clamp scale to valid range
        self._scale = max(0.1, min(2.0, self._scale))

        # Compute actual pixel dimensions
        self._width = max(16, int(BASE_WIDTH * self._scale))
        self._height = max(4, int(BASE_HEIGHT * self._scale))

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
        """Draw soundwave bars + elapsed time label."""
        r, g, b, _ = COLOR_RECORDING
        t = self._tick_count / FPS  # Time in seconds
        level = self._audio_level

        # Layout: [animation area ~55%] [label area ~45%]
        anim_w = w * 0.50
        label_x = anim_w + w * 0.02

        # Draw soundwave bars in the left portion
        num_bars = 8
        usable_w = anim_w * 0.80
        bar_width = usable_w / (num_bars * 1.8)
        gap = bar_width * 0.8
        total_bar_w = num_bars * bar_width + (num_bars - 1) * gap
        start_x = (anim_w - total_bar_w) / 2
        max_h = h * 0.72
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

        # Draw text label: "Recording  0:05"
        elapsed = self._get_elapsed_str()
        self._draw_text(cr, "Recording", label_x, h / 2, alpha,
                        color=COLOR_TEXT, bold=True)

        # Timer in dimmer color, right-aligned
        timer_font_size = self._height * 0.34
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(timer_font_size)
        timer_extents = cr.text_extents(elapsed)
        timer_x = w - timer_extents.width - w * 0.04
        self._draw_text(cr, elapsed, timer_x, h / 2, alpha,
                        color=COLOR_TEXT_DIM, font_size=timer_font_size)

    def _draw_processing(self, cr, w, h, alpha) -> None:
        """Draw pulsing dots + 'Processing...' label."""
        r, g, b, _ = COLOR_PROCESSING
        t = self._tick_count / FPS

        # Layout: [dots ~35%] [label ~65%]
        anim_w = w * 0.30
        label_x = anim_w + w * 0.03

        num_dots = 4
        dot_r = min(anim_w, h) * 0.08
        gap = dot_r * 3.0
        total_w = (num_dots - 1) * gap
        start_x = (anim_w - total_w) / 2
        cy = h / 2

        for i in range(num_dots):
            phase = i * 0.5
            scale = 0.6 + 0.4 * math.sin(t * 2.5 + phase)
            x = start_x + i * gap
            cr.arc(x, cy, dot_r * scale, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, alpha * scale)
            cr.fill()

        # Animated dots in label text
        dot_count = int(t * 2) % 4
        label = "Processing" + "." * dot_count
        self._draw_text(cr, label, label_x, h / 2, alpha, color=COLOR_TEXT)

    def _draw_transcribing(self, cr, w, h, alpha) -> None:
        """Draw bouncing dots + 'Transcribing...' label."""
        r, g, b, _ = COLOR_TRANSCRIBING
        t = self._tick_count / FPS

        # Layout: [dots ~25%] [label ~75%]
        anim_w = w * 0.22
        label_x = anim_w + w * 0.03

        num_dots = 3
        dot_r = min(anim_w, h) * 0.10
        gap = dot_r * 3.5
        total_w = (num_dots - 1) * gap
        start_x = (anim_w - total_w) / 2
        cy = h / 2

        for i in range(num_dots):
            phase = i * 0.4
            bounce = abs(math.sin(t * 3 + phase)) * min(anim_w, h) * 0.15
            x = start_x + i * gap
            y = cy - bounce
            cr.arc(x, y, dot_r, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, alpha * 0.9)
            cr.fill()

        # Animated dots in label text
        dot_count = int(t * 2) % 4
        label = "Transcribing" + "." * dot_count
        self._draw_text(cr, label, label_x, h / 2, alpha, color=COLOR_TEXT)

    def _draw_pasting(self, cr, w, h, alpha) -> None:
        """Draw clipboard icon + 'Pasting...' label."""
        r, g, b, _ = COLOR_PASTING
        t = self._tick_count / FPS
        cy = h / 2

        # Draw a small clipboard icon
        icon_size = h * 0.45
        icon_x = w * 0.08
        icon_y = cy - icon_size / 2

        # Clipboard body
        cr.set_line_width(icon_size * 0.12)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        # Rectangle body
        bx = icon_x
        by = icon_y + icon_size * 0.15
        bw = icon_size * 0.7
        bh = icon_size * 0.85
        br = icon_size * 0.1
        self._draw_rounded_rect(cr, bx, by, bw, bh, br)
        cr.stroke()

        # Clip at top
        clip_w = icon_size * 0.35
        clip_x = bx + (bw - clip_w) / 2
        clip_y = icon_y
        cr.rectangle(clip_x, clip_y, clip_w, icon_size * 0.2)
        cr.fill()

        # Lines on clipboard (text representation)
        line_y1 = by + bh * 0.35
        line_y2 = by + bh * 0.55
        cr.set_line_width(icon_size * 0.08)
        cr.move_to(bx + bw * 0.2, line_y1)
        cr.line_to(bx + bw * 0.8, line_y1)
        cr.stroke()
        cr.move_to(bx + bw * 0.2, line_y2)
        cr.line_to(bx + bw * 0.6, line_y2)
        cr.stroke()

        # Label
        label_x = icon_x + icon_size * 0.9
        dot_count = int(t * 3) % 4
        label = "Pasting" + "." * dot_count
        self._draw_text(cr, label, label_x, h / 2, alpha, color=COLOR_TEXT)

    def _draw_complete(self, cr, w, h, alpha) -> None:
        """Draw checkmark + 'Done!' label with optional info."""
        r, g, b, _ = COLOR_COMPLETE
        cy = h / 2

        # Draw checkmark on the left
        check_x = w * 0.08
        size = h * 0.25

        cr.set_line_width(size * 0.28)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        cr.move_to(check_x, cy)
        cr.line_to(check_x + size * 0.4, cy + size * 0.4)
        cr.line_to(check_x + size * 1.1, cy - size * 0.35)
        cr.stroke()

        # Label: "Done!"
        label_x = check_x + size * 1.5
        self._draw_text(cr, "Done!", label_x, h / 2, alpha,
                        color=COLOR_COMPLETE, bold=True)

        # Info text (e.g. word count) in dimmer color
        if self._info_text:
            # Position info text after "Done!" label
            cr.select_font_face("Sans", 0, 1)
            cr.set_font_size(self._height * 0.38)
            done_extents = cr.text_extents("Done! ")
            info_x = label_x + done_extents.width + w * 0.01
            self._draw_text(cr, self._info_text, info_x, h / 2, alpha * 0.8,
                            color=COLOR_TEXT_DIM, font_size=self._height * 0.32)

    def _draw_error(self, cr, w, h, alpha) -> None:
        """Draw X mark + error label."""
        r, g, b, _ = COLOR_ERROR
        cy = h / 2

        # Draw X on the left
        x_center = w * 0.08 + h * 0.15
        size = h * 0.18

        cr.set_line_width(size * 0.28)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgba(r, g, b, alpha)

        cr.move_to(x_center - size, cy - size)
        cr.line_to(x_center + size, cy + size)
        cr.stroke()

        cr.move_to(x_center + size, cy - size)
        cr.line_to(x_center - size, cy + size)
        cr.stroke()

        # Label
        label_x = x_center + size * 2
        label = self._info_text if self._info_text else "Error"
        self._draw_text(cr, label, label_x, h / 2, alpha,
                        color=COLOR_ERROR, bold=True)

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
