"""Tests for Flow Mode profile resolution."""

import pytest

from whisprbar.flow.models import AppContext
from whisprbar.flow.profiles import resolve_profile


@pytest.mark.unit
@pytest.mark.parametrize(
    ("context", "expected_id", "expected_rewrite", "expected_paste"),
    [
        (AppContext("x11", app_class="gnome-terminal", window_title="bash"), "terminal", "none", "ctrl_shift_v"),
        (AppContext("x11", app_class="Slack", window_title="Team chat"), "chat", "concise", None),
        (AppContext("x11", app_class="thunderbird", window_title="Inbox"), "email", "professional", None),
        (AppContext("x11", app_class="obsidian", window_title="Daily Notes"), "notes", "structured", None),
        (AppContext("x11", app_class="code", window_title="main.py"), "editor", "none", None),
        (AppContext("x11", app_class="firefox", window_title="Unknown page"), "default", "clean", None),
    ],
)
def test_resolve_profile_matches_builtin_categories(context, expected_id, expected_rewrite, expected_paste):
    profile = resolve_profile(context, {"flow_default_profile": "default"})

    assert profile.profile_id == expected_id
    assert profile.rewrite_mode == expected_rewrite
    assert profile.paste_sequence == expected_paste


@pytest.mark.unit
def test_resolve_profile_merges_user_overrides():
    context = AppContext("x11", app_class="thunderbird", window_title="Inbox")
    cfg = {
        "flow_profiles": {
            "email": {
                "label": "Mail custom",
                "style": "brief",
                "rewrite_mode": "shorter",
                "add_space": False,
                "unknown": "ignored",
            }
        }
    }

    profile = resolve_profile(context, cfg)

    assert profile.profile_id == "email"
    assert profile.label == "Mail custom"
    assert profile.style == "brief"
    assert profile.rewrite_mode == "shorter"
    assert profile.add_space is False


@pytest.mark.unit
def test_resolve_profile_uses_default_profile_when_context_unknown():
    context = AppContext("wayland")
    cfg = {"flow_default_profile": "notes"}

    profile = resolve_profile(context, cfg)

    assert profile.profile_id == "notes"
    assert profile.rewrite_mode == "structured"
