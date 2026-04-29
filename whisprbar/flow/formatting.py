"""Deterministic smart formatting helpers for Flow Mode."""

import re
from typing import Dict, Tuple

from whisprbar.flow.models import FlowProfile

BACKTRACK_PHRASES = {
    "en": ("scratch that", "actually"),
    "de": ("streich das", "nein eigentlich"),
}

PUNCTUATION_WORDS = {
    "en": {
        "comma": ",",
        "period": ".",
        "question mark": "?",
        "exclamation mark": "!",
    },
    "de": {
        "komma": ",",
        "punkt": ".",
        "fragezeichen": "?",
        "ausrufezeichen": "!",
    },
}

LINE_BREAK_WORDS = {
    "en": ("new line",),
    "de": ("neue zeile",),
}

LIST_MARKERS = {
    "en": ("one", "two", "three", "four", "five"),
    "de": ("eins", "zwei", "drei", "vier", "fünf"),
}


def apply_backtrack(text: str, language: str, enabled: bool) -> Tuple[str, Tuple[str, ...]]:
    """Remove earlier fragment when a correction phrase is spoken."""
    if not enabled:
        return text, ()

    phrases = BACKTRACK_PHRASES.get(language, BACKTRACK_PHRASES["en"])
    lowered = text.casefold()
    for phrase in phrases:
        marker = f" {phrase} "
        index = lowered.rfind(marker)
        if index >= 0:
            corrected = text[index + len(marker):].strip()
            return corrected, (phrase,)
    return text, ()


def _replace_punctuation_words(text: str, language: str) -> Tuple[str, bool]:
    replacements = PUNCTUATION_WORDS.get(language, PUNCTUATION_WORDS["en"])
    result = text
    changed = False
    for phrase, punctuation in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(
            rf"(?:\s*[,.;:!?])?\s+\b{re.escape(phrase)}\b[\s,.;:!?]*",
            re.IGNORECASE,
        )

        def replacement(match: re.Match[str]) -> str:
            return punctuation + (" " if match.end() < len(result) else "")

        result, count = pattern.subn(replacement, result)
        changed = changed or bool(count)
    result = re.sub(r"([,?!.])(?=\S)", r"\1 ", result)
    return result.strip(), changed


def _replace_line_break_words(text: str, language: str) -> Tuple[str, bool]:
    phrases = LINE_BREAK_WORDS.get(language, LINE_BREAK_WORDS["en"])
    result = text
    changed = False
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = re.compile(rf"\s*\b{re.escape(phrase)}\b[\s,.;:!?]*", re.IGNORECASE)
        result, count = pattern.subn("\n", result)
        changed = changed or bool(count)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r" *\n *", "\n", result)
    return result.strip(), changed


def _clean_list_item(item: str, language: str) -> str:
    punctuation_words = "|".join(
        re.escape(word)
        for word in PUNCTUATION_WORDS.get(language, PUNCTUATION_WORDS["en"]).keys()
    )
    item = item.strip(" ,.;:!?")
    item = re.sub(rf"^(?:{punctuation_words})\b[\s,.;:!?]*", "", item, flags=re.IGNORECASE)
    item = re.sub(rf"[\s,.;:!?]*(?:{punctuation_words})\b$", "", item, flags=re.IGNORECASE)
    return item.strip(" ,.;:!?")


def _format_numbered_list(text: str, language: str) -> Tuple[str, bool]:
    markers = LIST_MARKERS.get(language, LIST_MARKERS["en"])
    marker_pattern = "|".join(re.escape(marker) for marker in markers)
    pattern = re.compile(rf"\b({marker_pattern})\b\s+", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if len(matches) < 2 or matches[0].start() != 0:
        return text, False

    lines = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        item = _clean_list_item(text[start:end], language)
        if item:
            lines.append(f"{index + 1}. {item}")
    if len(lines) < 2:
        return text, False
    return "\n".join(lines), True


def apply_smart_formatting(
    text: str, language: str, profile: FlowProfile, cfg: dict
) -> Tuple[str, Dict[str, object]]:
    """Apply deterministic smart formatting without AI."""
    if not cfg.get("flow_smart_formatting_enabled", True):
        return text, {}

    metadata: Dict[str, object] = {}
    result, list_changed = _format_numbered_list(text, language)
    if list_changed:
        metadata["list_format"] = "numbered"

    result, punctuation_changed = _replace_punctuation_words(result, language)
    if punctuation_changed:
        metadata["punctuation_words"] = True

    result, line_breaks_changed = _replace_line_break_words(result, language)
    if line_breaks_changed:
        metadata["line_breaks"] = True

    if profile.style == "casual" and result.endswith("."):
        result = result[:-1]
        metadata["chat_period_trimmed"] = True

    return result, metadata
