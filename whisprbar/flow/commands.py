"""Voice command detection for Flow Mode."""

import re
from dataclasses import dataclass
from typing import Optional

from whisprbar.flow.models import CommandDetection, PastePolicy


@dataclass(frozen=True)
class CommandSpec:
    command_id: str
    phrase: str
    rewrite_mode: Optional[str] = None
    paste_policy: Optional[PastePolicy] = None


COMMAND_SPECS = (
    CommandSpec("professional", "mach das professioneller", "professional"),
    CommandSpec("shorter", "mach das kürzer", "shorter"),
    CommandSpec("longer", "mach das länger", "longer"),
    CommandSpec("longer", "mach das ausführlicher", "longer"),
    CommandSpec("list", "formatiere das als liste", "list"),
    CommandSpec("list", "als liste", "list"),
    CommandSpec("list", "als leiste", "list"),
    CommandSpec("translate_english", "übersetze das ins englische", "translate_english"),
    CommandSpec("clipboard_only", "nur in die zwischenablage", paste_policy=PastePolicy(clipboard_only=True)),
    CommandSpec("press_enter", "drücke enter", paste_policy=PastePolicy(press_enter_after_paste=True)),
    CommandSpec("new_line", "neue zeile", paste_policy=PastePolicy(add_newline=True)),
    CommandSpec("professional", "make this more professional", "professional"),
    CommandSpec("shorter", "make this shorter", "shorter"),
    CommandSpec("longer", "make this longer", "longer"),
    CommandSpec("longer", "make this more detailed", "longer"),
    CommandSpec("list", "format this as a list", "list"),
    CommandSpec("translate_english", "translate this to english", "translate_english"),
    CommandSpec("clipboard_only", "clipboard only", paste_policy=PastePolicy(clipboard_only=True)),
    CommandSpec("press_enter", "press enter", paste_policy=PastePolicy(press_enter_after_paste=True)),
    CommandSpec("new_line", "new line", paste_policy=PastePolicy(add_newline=True)),
)


def _normalize(text: str) -> str:
    normalized = text.strip().casefold()
    normalized = re.sub(r"[\s,.;:!?]+$", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _strip_suffix(text: str, phrase: str) -> Optional[str]:
    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)
    if normalized_text == normalized_phrase:
        return ""
    suffix = " " + normalized_phrase
    if normalized_text.endswith(suffix):
        cleaned = re.sub(
            rf"[\s,.;:!?]*{re.escape(phrase)}[\s,.;:!?]*$",
            "",
            text,
            flags=re.IGNORECASE,
        )
        return cleaned.rstrip(" ,.;:!?").strip()
    return None


def detect_command(text: str, language: str, enabled: bool = True) -> CommandDetection:
    """Detect supported spoken commands at the end of a dictation."""
    if not enabled:
        return CommandDetection(text=text)

    ordered_specs = sorted(COMMAND_SPECS, key=lambda spec: len(spec.phrase), reverse=True)
    for spec in ordered_specs:
        cleaned_text = _strip_suffix(text, spec.phrase)
        if cleaned_text is not None:
            return CommandDetection(
                text=cleaned_text,
                command_id=spec.command_id,
                rewrite_mode=spec.rewrite_mode,
                paste_policy=spec.paste_policy,
            )

    return CommandDetection(text=text)
