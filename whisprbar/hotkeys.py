"""Hotkey handling for WhisprBar.

Provides global hotkey detection using pynput, key parsing, and
hotkey configuration management.
"""

import contextlib
import threading
from typing import Callable, Dict, Optional, Set, Tuple

from pynput import keyboard

# Type alias for hotkey binding
# (frozenset of modifiers like {"CTRL", "ALT"}, key token like "F9")
HotkeyBinding = Tuple[frozenset[str], str]

# Build F-key mapping (F1-F24)
FKEYS: Dict[str, keyboard.Key] = {}
for idx in range(1, 25):
    attr = f"f{idx}"
    key_obj = getattr(keyboard.Key, attr, None)
    if key_obj is not None:
        FKEYS[f"F{idx}"] = key_obj


def _collect_keys(*names: str) -> Set[keyboard.Key]:
    """Collect keyboard.Key objects by name.

    Args:
        names: Attribute names from keyboard.Key

    Returns:
        Set of keyboard.Key objects
    """
    keys: Set[keyboard.Key] = set()
    for name in names:
        key_obj = getattr(keyboard.Key, name, None)
        if key_obj is not None:
            keys.add(key_obj)
    return keys


# Modifier key mappings
MODIFIER_MAP: Dict[str, Set[keyboard.Key]] = {
    "CTRL": _collect_keys("ctrl", "ctrl_l", "ctrl_r"),
    "ALT": _collect_keys("alt", "alt_l", "alt_r"),
    "SHIFT": _collect_keys("shift", "shift_l", "shift_r"),
    "SUPER": _collect_keys("cmd", "cmd_l", "cmd_r", "super", "super_l", "super_r"),
}

# Reverse lookup: keyboard.Key -> modifier name
MODIFIER_LOOKUP: Dict[keyboard.Key, str] = {
    key: name for name, keys in MODIFIER_MAP.items() for key in keys
}

# Human-readable labels for modifiers
MODIFIER_LABELS: Dict[str, str] = {
    "CTRL": "Ctrl",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "SUPER": "Super",
}

# Sort order for modifiers in display strings
MODIFIER_ORDER: Dict[str, int] = {
    "CTRL": 0,
    "SHIFT": 1,
    "ALT": 2,
    "SUPER": 3,
}


def normalize_key_token(token: str) -> Optional[str]:
    """Normalize a key token string.

    Args:
        token: Key token (e.g., "f9", "a", "enter")

    Returns:
        Normalized token (e.g., "F9", "A") or None if invalid
    """
    token = (token or "").strip().upper()
    if not token:
        return None
    if token in FKEYS:
        return token
    if len(token) == 1:
        return token
    return None


def parse_hotkey(binding: str) -> HotkeyBinding:
    """Parse hotkey binding string into structured format.

    Examples:
        "F9" -> (frozenset(), "F9")
        "Ctrl+F9" -> (frozenset({"CTRL"}), "F9")
        "Ctrl+Shift+A" -> (frozenset({"CTRL", "SHIFT"}), "A")

    Args:
        binding: Hotkey string (e.g., "Ctrl+F9", "Alt+Shift+A")

    Returns:
        Tuple of (modifiers, key_token). Defaults to F9 if parsing fails.
    """
    binding = (binding or "").strip()
    if not binding:
        return (frozenset(), "F9")

    parts = [part.strip() for part in binding.split("+") if part.strip()]
    if not parts:
        return (frozenset(), "F9")

    # Last part is the key, everything else is modifiers
    key_token = normalize_key_token(parts[-1])
    if not key_token:
        return (frozenset(), "F9")

    modifiers = {
        part.upper() for part in parts[:-1] if part.upper() in MODIFIER_MAP
    }

    return (frozenset(modifiers), key_token)


def key_to_label(key_obj) -> str:
    """Convert key object to human-readable label.

    Args:
        key_obj: keyboard.Key, keyboard.KeyCode, or HotkeyBinding tuple

    Returns:
        Human-readable label (e.g., "Ctrl+F9", "Alt+Shift+A")
    """
    if isinstance(key_obj, tuple) and len(key_obj) == 2:
        modifiers, token = key_obj
        parts = [
            MODIFIER_LABELS[m]
            for m in sorted(modifiers, key=lambda x: MODIFIER_ORDER.get(x, 99))
        ]
        if token in FKEYS:
            parts.append(token)
        else:
            parts.append(token.upper())
        return "+".join(parts) if parts else token.upper()

    # Check if it's an F-key
    for name, key in FKEYS.items():
        if key_obj == key:
            return name

    # Check if it's a character key
    if isinstance(key_obj, keyboard.KeyCode):
        if key_obj.char:
            return key_obj.char.upper()

    # Check if it's a special key
    if isinstance(key_obj, keyboard.Key):
        return str(key_obj).split(".")[-1].upper()

    return "F9"


def key_to_config_string(key_obj) -> str:
    """Convert key object to config string format.

    Args:
        key_obj: keyboard.Key, keyboard.KeyCode, or HotkeyBinding tuple

    Returns:
        Config string (e.g., "CTRL+F9", "ALT+SHIFT+A")
    """
    if isinstance(key_obj, tuple) and len(key_obj) == 2:
        modifiers, token = key_obj
        parts = [
            mod for mod in sorted(modifiers, key=lambda x: MODIFIER_ORDER.get(x, 99))
        ]
        parts.append(token.upper())
        return "+".join(parts)

    # Check if it's an F-key
    for name, key in FKEYS.items():
        if key_obj == key:
            return name

    # Check if it's a character key
    if isinstance(key_obj, keyboard.KeyCode) and key_obj.char:
        return key_obj.char.upper()

    return "F9"


def hotkey_to_label(binding: HotkeyBinding) -> str:
    """Convert hotkey binding to human-readable label.

    Args:
        binding: HotkeyBinding tuple

    Returns:
        Human-readable label
    """
    return key_to_label(binding)


def hotkey_to_config(binding: HotkeyBinding) -> str:
    """Convert hotkey binding to config string.

    Args:
        binding: HotkeyBinding tuple

    Returns:
        Config string
    """
    return key_to_config_string(binding)


def event_to_token(key) -> Optional[str]:
    """Convert keyboard event key to normalized token.

    Args:
        key: keyboard.Key or keyboard.KeyCode from pynput event

    Returns:
        Normalized token (e.g., "F9", "A") or None if not recognized
    """
    # Check F-keys first
    for name, key_obj in FKEYS.items():
        if key == key_obj:
            return name

    # Check character keys
    if isinstance(key, keyboard.KeyCode) and key.char:
        char = key.char.strip()
        if len(char) == 1:
            return char.upper()

    return None


def modifier_name(key) -> Optional[str]:
    """Get modifier name from key object.

    Args:
        key: keyboard.Key from pynput event

    Returns:
        Modifier name (e.g., "CTRL", "ALT") or None if not a modifier
    """
    return MODIFIER_LOOKUP.get(key)


# Current hotkey binding (used by capture_hotkey and update_hotkey_binding)
_current_hotkey: HotkeyBinding = (frozenset(), "F9")

# =============================================================================
# Multiple Hotkey Manager
# =============================================================================
#
# Thread Safety Design:
# ---------------------
# The HotkeyManager coordinates between two threads:
#   1. Main thread: Registers/unregisters hotkeys, configures handlers
#   2. Listener thread: Detects keypresses and triggers callbacks (pynput daemon thread)
#
# Thread Safety Strategy:
#   - All shared state is protected by a reentrant lock (threading.RLock)
#   - RLock allows the same thread to acquire the lock multiple times (needed for stop())
#   - Callbacks are called OUTSIDE the lock to prevent deadlock
#   - Handler functions are copied under lock, then called outside lock
#   - Lock is held for minimal time to reduce contention
#
# Potential Deadlock Prevention:
#   - Never call user callbacks while holding the lock
#   - Never call handler functions while holding the lock
#   - If callbacks need to call back into HotkeyManager, RLock allows re-entry
#
# Performance Considerations:
#   - Lock acquisition overhead is minimal (<1μs on modern CPUs)
#   - Lock is released quickly after state access
#   - No measurable impact on hotkey detection latency
# =============================================================================

class HotkeyManager:
    """Manages multiple global hotkey bindings for different actions.

    This class allows registering multiple hotkeys that trigger different callbacks.
    It maintains a single keyboard listener that monitors all registered hotkeys.

    Thread Safety:
        All public methods are thread-safe and can be called from any thread.
        The keyboard listener runs in a separate daemon thread (managed by pynput).
        Internal state is protected by a reentrant lock to prevent race conditions
        between the main thread (registration/configuration) and the listener thread
        (key event handling).
    """

    def __init__(self):
        """Initialize the hotkey manager with thread-safe state."""
        # Thread synchronization - use RLock to allow nested locking in same thread
        self._lock = threading.RLock()

        # Listener state
        self._listener: Optional[keyboard.Listener] = None

        # Hotkey registration (accessed from main thread and listener thread)
        self._hotkeys: Dict[str, HotkeyBinding] = {}
        self._callbacks: Dict[str, Callable[[], None]] = {}

        # Active key state (accessed from listener thread only, but cleared from main thread)
        self._active_modifiers: Set[str] = set()
        self._active_tokens: Set[str] = set()

        # Special event handlers (set from main thread, called from listener thread)
        self._is_recording_fn: Optional[Callable[[], bool]] = None
        self._on_esc_fn: Optional[Callable[[], None]] = None
        self._is_capture_active_fn: Optional[Callable[[], bool]] = None

    def register(self, action: str, hotkey: HotkeyBinding, callback: Callable[[], None]) -> None:
        """Register a hotkey for an action.

        Thread-safe: Can be called from any thread.

        Args:
            action: Action identifier (e.g., "toggle_recording", "open_settings")
            hotkey: Hotkey binding tuple (modifiers, key)
            callback: Function to call when hotkey is pressed
        """
        with self._lock:
            self._hotkeys[action] = hotkey
            self._callbacks[action] = callback

    def unregister(self, action: str) -> None:
        """Unregister a hotkey action.

        Thread-safe: Can be called from any thread.

        Args:
            action: Action identifier to remove
        """
        with self._lock:
            self._hotkeys.pop(action, None)
            self._callbacks.pop(action, None)

    def set_special_handlers(
        self,
        is_recording: Optional[Callable[[], bool]] = None,
        on_esc: Optional[Callable[[], None]] = None,
        is_capture_active: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Set special event handlers.

        Thread-safe: Can be called from any thread.

        Args:
            is_recording: Function that returns True if currently recording
            on_esc: Callback when ESC is pressed during recording
            is_capture_active: Function that returns True if capturing new hotkey
        """
        with self._lock:
            self._is_recording_fn = is_recording
            self._on_esc_fn = on_esc
            self._is_capture_active_fn = is_capture_active

    def start(self) -> None:
        """Start listening for all registered hotkeys.

        Thread-safe: Can be called from any thread.
        """
        with self._lock:
            if self._listener is not None:
                self.stop()

        def on_press(key):
            """Handle key press events. Runs in pynput's listener thread.

            Thread Safety Strategy:
            1. Read handler functions under lock, then call outside lock
            2. Protect state modifications (_active_modifiers, _active_tokens) with lock
            3. Perform hotkey matching under lock, then call callback outside lock
            4. Minimize time spent holding the lock to reduce contention
            """
            # CRITICAL: Read handler functions with lock, then call outside lock.
            # This prevents deadlock if handlers try to acquire the same lock.
            with self._lock:
                is_recording_fn = self._is_recording_fn
                on_esc_fn = self._on_esc_fn
                is_capture_active_fn = self._is_capture_active_fn

            # Handle ESC during recording (call handlers outside lock to prevent deadlock)
            if is_recording_fn and is_recording_fn():
                if key == keyboard.Key.esc and on_esc_fn:
                    on_esc_fn()
                    return

            # Ignore keys during hotkey capture
            if is_capture_active_fn and is_capture_active_fn():
                return

            # Check if it's a modifier
            mod = modifier_name(key)
            if mod:
                with self._lock:
                    self._active_modifiers.add(mod)
                return

            # Check if it's a recognized key token
            token = event_to_token(key)
            if not token:
                return

            # Thread-safe hotkey matching and callback execution
            # Strategy: Acquire lock, match hotkey, store callback reference, release lock,
            # then call callback. This prevents deadlock if callback calls back into manager.
            callback_to_call = None
            with self._lock:
                # Prevent key repeat
                if token in self._active_tokens:
                    return

                self._active_tokens.add(token)

                # Check all registered hotkeys
                for action, (required_mods, required_token) in self._hotkeys.items():
                    if token == required_token and required_mods.issubset(self._active_modifiers):
                        callback_to_call = self._callbacks.get(action)
                        break

            # CRITICAL: Call callback outside lock to prevent deadlock
            if callback_to_call:
                callback_to_call()

        def on_release(key):
            """Handle key release events. Runs in pynput's listener thread.

            Thread Safety Strategy:
            1. Read handler function under lock, then call outside lock
            2. Protect state modifications with lock
            """
            # Read handler function with lock protection
            with self._lock:
                is_capture_active_fn = self._is_capture_active_fn

            # Ignore keys during hotkey capture
            if is_capture_active_fn and is_capture_active_fn():
                return

            # Release modifier - protect state modification
            mod = modifier_name(key)
            if mod:
                with self._lock:
                    self._active_modifiers.discard(mod)

            # Release token - protect state modification
            token = event_to_token(key)
            if token:
                with self._lock:
                    self._active_tokens.discard(token)

        with self._lock:
            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._listener.daemon = True
            self._listener.start()

    def stop(self) -> None:
        """Stop the hotkey listener.

        Thread-safe: Can be called from any thread.

        Note: This method releases the lock BEFORE calling listener.stop()
        to prevent cross-thread deadlock. The RLock allows same-thread
        reentry, but doesn't prevent deadlock between different threads
        (main thread holding lock while waiting for listener thread,
        which might need the lock in its callbacks).
        """
        # Get listener reference and clear state while holding lock
        with self._lock:
            listener_to_stop = self._listener
            self._listener = None
            self._active_modifiers.clear()
            self._active_tokens.clear()

        # Stop listener OUTSIDE lock to prevent cross-thread deadlock
        # This allows listener thread to complete pending callbacks
        if listener_to_stop:
            listener_to_stop.stop()

    def get_hotkey(self, action: str) -> Optional[HotkeyBinding]:
        """Get the hotkey binding for an action.

        Thread-safe: Can be called from any thread.

        Args:
            action: Action identifier

        Returns:
            Hotkey binding or None if not registered
        """
        with self._lock:
            return self._hotkeys.get(action)

    def get_all_hotkeys(self) -> Dict[str, HotkeyBinding]:
        """Get all registered hotkey bindings.

        Thread-safe: Can be called from any thread.

        Returns:
            Dictionary mapping actions to hotkey bindings
        """
        with self._lock:
            return self._hotkeys.copy()


# Global hotkey manager instance
_hotkey_manager: Optional[HotkeyManager] = None


def get_hotkey_manager() -> HotkeyManager:
    """Get or create the global hotkey manager instance.

    Returns:
        Global HotkeyManager instance
    """
    global _hotkey_manager
    if _hotkey_manager is None:
        _hotkey_manager = HotkeyManager()
    return _hotkey_manager



def get_current_hotkey() -> HotkeyBinding:
    """Get the currently configured hotkey.

    Returns:
        Current hotkey binding
    """
    return _current_hotkey


# Global capture listener instance
_capture_listener: Optional[keyboard.Listener] = None


def capture_hotkey(
    on_complete: Optional[Callable[[str, str], None]] = None,
    notify_user: bool = True,
    timeout_seconds: float = 30.0,
) -> None:
    """Capture the next keypress globally and store it as hotkey.

    Opens a temporary keyboard listener to capture a new hotkey combination.
    When a key is pressed (with optional modifiers), it updates the hotkey
    configuration and restarts the main hotkey listener.

    Args:
        on_complete: Callback function called with (config_value, label) when done
        notify_user: If True, show notification when starting capture
        timeout_seconds: Timeout after which capture is cancelled (default: 30s)
    """
    global _capture_listener
    from .config import cfg, save_config
    from .utils import notify
    import threading
    import time

    # Stop existing capture listener
    if _capture_listener:
        with contextlib.suppress(Exception):
            _capture_listener.stop()
        _capture_listener = None

    if notify_user:
        notify("Press a key for the new hotkey...")

    capture_modifiers: Set[str] = set()
    capture_done = {"value": False}
    timeout_timer = {"timer": None}

    def finalize_hotkey(token: Optional[str]) -> None:
        if capture_done["value"]:
            return
        capture_done["value"] = True

        # Cancel timeout timer
        if timeout_timer["timer"]:
            timeout_timer["timer"].cancel()
            timeout_timer["timer"] = None

        # Stop capture listener first
        global _capture_listener
        with contextlib.suppress(Exception):
            if _capture_listener:
                _capture_listener.stop()
        _capture_listener = None

        # If no token, capture was cancelled/timed out
        if not token:
            if notify_user:
                notify("Hotkey capture cancelled.")
            return

        # Update hotkey binding
        update_hotkey_binding(set(capture_modifiers), token, notify_change=notify_user)

        # Call completion callback if provided
        if on_complete:
            config_value = cfg.get("hotkey", "")
            global _current_hotkey
            label = hotkey_to_label(_current_hotkey)

            # Try to use GLib.idle_add if available (for GTK thread safety)
            try:
                from gi.repository import GLib

                def _fire_callback() -> bool:
                    on_complete(config_value, label)
                    return False

                GLib.idle_add(_fire_callback)
            except ImportError:
                # No GLib available, call directly
                on_complete(config_value, label)

    def _on_press(key):
        mod = modifier_name(key)
        if mod:
            capture_modifiers.add(mod)
            return
        token = event_to_token(key)
        if token:
            finalize_hotkey(token)

    def _on_release(key):
        mod = modifier_name(key)
        if mod:
            capture_modifiers.discard(mod)

    _capture_listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    _capture_listener.daemon = True
    _capture_listener.start()

    # Start timeout timer
    def on_timeout():
        finalize_hotkey(None)  # Cancel capture

    timeout_timer["timer"] = threading.Timer(timeout_seconds, on_timeout)
    timeout_timer["timer"].daemon = True
    timeout_timer["timer"].start()


def update_hotkey_binding(
    modifiers: Set[str],
    token: str,
    notify_change: bool = True,
    restart_listener: bool = True,
) -> None:
    """Update the hotkey binding and save to configuration.

    Args:
        modifiers: Set of modifier names (e.g., {"CTRL", "SHIFT"})
        token: Key token (e.g., "F9", "A")
        notify_change: If True, show notification about the change
        restart_listener: If True, restart the hotkey listener (default: True)
    """
    global _current_hotkey
    from .config import cfg, save_config
    from .utils import notify

    # Normalize and validate
    normalized_token = normalize_key_token(token) or "F9"
    valid_mods = {mod for mod in modifiers if mod in MODIFIER_MAP}

    # Update current hotkey
    _current_hotkey = (frozenset(valid_mods), normalized_token)

    # Save to config
    cfg["hotkey"] = hotkey_to_config(_current_hotkey)
    # Also update the hotkeys dict for the new multi-hotkey format
    if "hotkeys" not in cfg:
        cfg["hotkeys"] = {}
    cfg["hotkeys"]["toggle_recording"] = hotkey_to_config(_current_hotkey)
    save_config()

    # Notify user
    if notify_change:
        notify(f"Hotkey set to {hotkey_to_label(_current_hotkey)}.")

    # Restart listener if requested
    # Note: In V6, the listener is managed by main.py, so we can't directly restart it here
    # The caller should restart the listener manually if needed
