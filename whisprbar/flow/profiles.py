"""Built-in Flow Mode app profiles."""

from dataclasses import replace
from typing import Any, Dict

from whisprbar.flow.models import AppContext, FlowProfile


BUILTIN_PROFILES: Dict[str, FlowProfile] = {
    "terminal": FlowProfile(
        profile_id="terminal",
        label="Terminal",
        style="literal",
        rewrite_mode="none",
        paste_sequence="ctrl_shift_v",
    ),
    "chat": FlowProfile(
        profile_id="chat",
        label="Chat",
        style="casual",
        rewrite_mode="concise",
    ),
    "email": FlowProfile(
        profile_id="email",
        label="Email",
        style="professional",
        rewrite_mode="professional",
    ),
    "notes": FlowProfile(
        profile_id="notes",
        label="Notes",
        style="structured",
        rewrite_mode="structured",
    ),
    "editor": FlowProfile(
        profile_id="editor",
        label="Editor",
        style="literal",
        rewrite_mode="none",
    ),
    "default": FlowProfile(
        profile_id="default",
        label="Default",
        style="clean",
        rewrite_mode="clean",
    ),
}

TERMINAL_KEYWORDS = ("terminal", "konsole", "alacritty", "kitty", "wezterm", "xterm", "bash", "zsh")
CHAT_KEYWORDS = ("slack", "discord", "telegram", "signal", "whatsapp", "element")
EMAIL_KEYWORDS = ("thunderbird", "evolution", "geary", "mail", "inbox", "gmail", "outlook")
NOTES_KEYWORDS = ("obsidian", "notion", "logseq", "joplin", "notes")
EDITOR_KEYWORDS = ("code", "vscode", "jetbrains", "pycharm", "idea", "sublime", "vim", "emacs")


def _context_text(context: AppContext) -> str:
    return " ".join([context.app_class, context.app_name, context.window_title]).lower()


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _profile_id_for_context(context: AppContext, cfg: dict) -> str:
    text = _context_text(context)
    if _matches(text, TERMINAL_KEYWORDS):
        return "terminal"
    if _matches(text, CHAT_KEYWORDS):
        return "chat"
    if _matches(text, EMAIL_KEYWORDS):
        return "email"
    if _matches(text, NOTES_KEYWORDS):
        return "notes"
    if _matches(text, EDITOR_KEYWORDS):
        return "editor"

    default_profile = cfg.get("flow_default_profile", "default")
    if default_profile in BUILTIN_PROFILES:
        return default_profile
    return "default"


def _merge_override(profile: FlowProfile, override: Dict[str, Any]) -> FlowProfile:
    allowed = {
        "label",
        "style",
        "rewrite_mode",
        "paste_sequence",
        "add_space",
        "add_newline",
    }
    values = {key: value for key, value in override.items() if key in allowed}
    return replace(profile, **values)


def resolve_profile(context: AppContext, cfg: dict) -> FlowProfile:
    """Resolve the Flow profile for an app context and config."""
    profile_id = _profile_id_for_context(context, cfg)
    profile = BUILTIN_PROFILES[profile_id]
    overrides = cfg.get("flow_profiles") or {}
    override = overrides.get(profile.profile_id)
    if isinstance(override, dict):
        profile = _merge_override(profile, override)
    return profile
