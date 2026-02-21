"""Unit tests for whisprbar.hotkeys module."""

import pytest

from whisprbar import hotkeys

pytestmark = pytest.mark.skipif(
    not hotkeys.PYNPUT_AVAILABLE,
    reason="pynput backend unavailable in this environment",
)

@pytest.mark.unit
def test_normalize_key_token_fkeys():
    """Test normalization of F-key tokens."""
    assert hotkeys.normalize_key_token("f9") == "F9"
    assert hotkeys.normalize_key_token("F9") == "F9"
    assert hotkeys.normalize_key_token("f1") == "F1"
    assert hotkeys.normalize_key_token("F24") == "F24"


@pytest.mark.unit
def test_normalize_key_token_letters():
    """Test normalization of letter keys."""
    assert hotkeys.normalize_key_token("a") == "A"
    assert hotkeys.normalize_key_token("A") == "A"
    assert hotkeys.normalize_key_token("z") == "Z"


@pytest.mark.unit
def test_normalize_key_token_special_aliases():
    """Test normalization of special key aliases."""
    assert hotkeys.normalize_key_token("right_ctrl") == "CTRL_R"
    assert hotkeys.normalize_key_token("left_ctrl") == "CTRL_L"


@pytest.mark.unit
def test_normalize_key_token_invalid():
    """Test normalization of invalid tokens."""
    assert hotkeys.normalize_key_token("") is None
    assert hotkeys.normalize_key_token(None) is None
    assert hotkeys.normalize_key_token("  ") is None
    assert hotkeys.normalize_key_token("invalid") is None


@pytest.mark.unit
def test_parse_hotkey_simple_fkey():
    """Test parsing simple F-key hotkey."""
    modifiers, key = hotkeys.parse_hotkey("F9")
    assert modifiers == frozenset()
    assert key == "F9"


@pytest.mark.unit
def test_parse_hotkey_special_key():
    """Test parsing hotkey with special key token."""
    modifiers, key = hotkeys.parse_hotkey("CTRL_R")
    assert modifiers == frozenset()
    assert key == "CTRL_R"


@pytest.mark.unit
def test_parse_hotkey_with_single_modifier():
    """Test parsing hotkey with single modifier."""
    modifiers, key = hotkeys.parse_hotkey("Ctrl+F9")
    assert "CTRL" in modifiers
    assert key == "F9"

    modifiers, key = hotkeys.parse_hotkey("Alt+A")
    assert "ALT" in modifiers
    assert key == "A"


@pytest.mark.unit
def test_parse_hotkey_with_multiple_modifiers():
    """Test parsing hotkey with multiple modifiers."""
    modifiers, key = hotkeys.parse_hotkey("Ctrl+Shift+F9")
    assert "CTRL" in modifiers
    assert "SHIFT" in modifiers
    assert key == "F9"

    modifiers, key = hotkeys.parse_hotkey("Ctrl+Alt+Shift+A")
    assert "CTRL" in modifiers
    assert "ALT" in modifiers
    assert "SHIFT" in modifiers
    assert key == "A"


@pytest.mark.unit
def test_parse_hotkey_case_insensitive():
    """Test that parse_hotkey is case-insensitive."""
    m1, k1 = hotkeys.parse_hotkey("ctrl+f9")
    m2, k2 = hotkeys.parse_hotkey("CTRL+F9")
    m3, k3 = hotkeys.parse_hotkey("Ctrl+F9")

    assert m1 == m2 == m3
    assert k1 == k2 == k3


@pytest.mark.unit
def test_parse_hotkey_invalid_defaults_to_f9():
    """Test that invalid hotkeys default to F9."""
    modifiers, key = hotkeys.parse_hotkey("")
    assert modifiers == frozenset()
    assert key == "F9"

    modifiers, key = hotkeys.parse_hotkey(None)
    assert modifiers == frozenset()
    assert key == "F9"

    modifiers, key = hotkeys.parse_hotkey("InvalidKey")
    assert modifiers == frozenset()
    assert key == "F9"


@pytest.mark.unit
def test_key_to_label_simple():
    """Test key_to_label with simple keys."""
    binding = (frozenset(), "F9")
    assert hotkeys.key_to_label(binding) == "F9"

    binding = (frozenset(), "A")
    assert hotkeys.key_to_label(binding) == "A"


@pytest.mark.unit
def test_key_to_label_special_key():
    """Test key_to_label with side-specific modifier token as key."""
    binding = (frozenset(), "CTRL_R")
    assert hotkeys.key_to_label(binding) == "Right Ctrl"


@pytest.mark.unit
def test_key_to_label_with_modifiers():
    """Test key_to_label with modifiers."""
    binding = (frozenset(["CTRL"]), "F9")
    assert hotkeys.key_to_label(binding) == "Ctrl+F9"

    binding = (frozenset(["CTRL", "SHIFT"]), "A")
    label = hotkeys.key_to_label(binding)
    assert "Ctrl" in label
    assert "Shift" in label
    assert label.endswith("+A")


@pytest.mark.unit
def test_key_to_label_modifier_order():
    """Test that modifiers are sorted correctly in labels."""
    # Modifiers should appear in order: Ctrl, Shift, Alt, Super
    binding = (frozenset(["ALT", "CTRL", "SHIFT"]), "F9")
    label = hotkeys.key_to_label(binding)

    # Find positions of each modifier
    ctrl_pos = label.index("Ctrl")
    shift_pos = label.index("Shift")
    alt_pos = label.index("Alt")

    # Ctrl should come before Shift, Shift before Alt
    assert ctrl_pos < shift_pos < alt_pos


@pytest.mark.unit
def test_key_to_config_string():
    """Test key_to_config_string conversion."""
    binding = (frozenset(["CTRL"]), "F9")
    assert hotkeys.key_to_config_string(binding) == "CTRL+F9"

    binding = (frozenset(["CTRL", "SHIFT"]), "A")
    config_str = hotkeys.key_to_config_string(binding)
    assert "CTRL" in config_str
    assert "SHIFT" in config_str
    assert config_str.endswith("+A")


@pytest.mark.unit
def test_hotkey_to_label():
    """Test hotkey_to_label wrapper function."""
    binding = (frozenset(["CTRL"]), "F9")
    assert hotkeys.hotkey_to_label(binding) == "Ctrl+F9"


@pytest.mark.unit
def test_hotkey_to_config():
    """Test hotkey_to_config wrapper function."""
    binding = (frozenset(["CTRL"]), "F9")
    assert hotkeys.hotkey_to_config(binding) == "CTRL+F9"


@pytest.mark.unit
def test_find_hotkey_conflicts_detects_duplicates():
    """Test duplicate binding detection across hotkey actions."""
    conflicts = hotkeys.find_hotkey_conflicts(
        {
            "toggle_recording": "ctrl+f9",
            "start_recording": "CTRL+F9",
            "stop_recording": "F10",
            "open_settings": None,
        }
    )

    assert "CTRL+F9" in conflicts
    assert set(conflicts["CTRL+F9"]) == {"toggle_recording", "start_recording"}


@pytest.mark.unit
def test_event_to_token_fkeys():
    """Test converting keyboard events to tokens for F-keys."""
    # Test each F-key mapping
    for name, key_obj in hotkeys.FKEYS.items():
        token = hotkeys.event_to_token(key_obj)
        assert token == name


@pytest.mark.unit
def test_event_to_token_special_key():
    """Test converting special key events to tokens."""
    token = "CTRL_R" if hotkeys.SPECIAL_KEY_MAP.get("CTRL_R") else "CTRL"
    key_obj = next(iter(hotkeys.SPECIAL_KEY_MAP[token]))
    assert hotkeys.event_to_token(key_obj) == token


@pytest.mark.unit
def test_modifier_name():
    """Test modifier_name function."""
    # Test that keyboard modifiers are recognized
    # Note: These tests require actual keyboard.Key objects
    ctrl_key = hotkeys.keyboard.Key.ctrl
    result = hotkeys.modifier_name(ctrl_key)
    assert result == "CTRL"


@pytest.mark.unit
def test_get_current_hotkey():
    """Test get_current_hotkey returns the current binding."""
    # Initially should be F9
    binding = hotkeys.get_current_hotkey()
    assert isinstance(binding, tuple)
    assert len(binding) == 2


@pytest.mark.unit
def test_hotkey_manager_register():
    """Test HotkeyManager registration."""
    manager = hotkeys.HotkeyManager()

    called = {"value": False}

    def callback():
        called["value"] = True

    hotkey_binding = (frozenset(["CTRL"]), "F9")
    manager.register("test_action", hotkey_binding, callback)

    # Verify registration
    assert manager.get_hotkey("test_action") == hotkey_binding
    assert "test_action" in manager._callbacks


@pytest.mark.unit
def test_hotkey_manager_unregister():
    """Test HotkeyManager unregistration."""
    manager = hotkeys.HotkeyManager()

    def callback():
        pass

    hotkey_binding = (frozenset(), "F9")
    manager.register("test_action", hotkey_binding, callback)

    # Unregister
    manager.unregister("test_action")

    assert manager.get_hotkey("test_action") is None
    assert "test_action" not in manager._callbacks


@pytest.mark.unit
def test_hotkey_manager_get_all_hotkeys():
    """Test HotkeyManager.get_all_hotkeys()."""
    manager = hotkeys.HotkeyManager()

    def callback1():
        pass

    def callback2():
        pass

    manager.register("action1", (frozenset(), "F9"), callback1)
    manager.register("action2", (frozenset(["CTRL"]), "F10"), callback2)

    all_hotkeys = manager.get_all_hotkeys()

    assert len(all_hotkeys) == 2
    assert "action1" in all_hotkeys
    assert "action2" in all_hotkeys
    assert all_hotkeys["action1"] == (frozenset(), "F9")


@pytest.mark.unit
def test_get_hotkey_manager_singleton():
    """Test that get_hotkey_manager returns singleton instance."""
    manager1 = hotkeys.get_hotkey_manager()
    manager2 = hotkeys.get_hotkey_manager()

    assert manager1 is manager2
