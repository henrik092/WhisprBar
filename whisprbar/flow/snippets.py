"""Local spoken snippet expansion for Flow Mode."""

import json
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from whisprbar.flow.models import Snippet
from whisprbar.utils import debug

SNIPPETS_PATH = Path.home() / ".config" / "whisprbar" / "snippets.json"


def load_snippets(path: Optional[Path] = None) -> List[Snippet]:
    """Load snippets from JSON."""
    snippets_path = path or SNIPPETS_PATH
    if not snippets_path.exists():
        return []

    try:
        data = json.loads(snippets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        debug(f"Failed to load Flow snippets {snippets_path}: {exc}")
        return []

    snippets: List[Snippet] = []
    if not isinstance(data, list):
        return snippets

    for item in data:
        if not isinstance(item, dict):
            continue
        trigger = str(item.get("trigger", "")).strip()
        text = str(item.get("text", "")).strip()
        if trigger and text:
            snippets.append(Snippet(trigger=trigger, text=text))
    return list(validate_snippets(snippets))


def save_snippets(snippets: Sequence[Snippet], path: Optional[Path] = None) -> None:
    """Persist snippets as JSON, skipping incomplete rows."""
    snippets_path = path or SNIPPETS_PATH
    snippets_path.parent.mkdir(parents=True, exist_ok=True)

    data = []
    for snippet in snippets:
        trigger = str(snippet.trigger).strip()
        text = str(snippet.text).strip()
        if trigger and text:
            data.append({"trigger": trigger, "text": text})

    snippets_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_snippets(snippets: Sequence[Snippet]) -> Tuple[Snippet, ...]:
    """Validate snippet triggers and return a normalized tuple."""
    seen = set()
    result = []
    for snippet in snippets:
        key = snippet.trigger.casefold().strip()
        if key in seen:
            raise ValueError(f"duplicate snippet trigger: {snippet.trigger}")
        seen.add(key)
        result.append(snippet)
    return tuple(result)


def apply_snippets(text: str, snippets: Sequence[Snippet]) -> Tuple[str, Tuple[str, ...]]:
    """Apply spoken snippets and return hit labels."""
    result = text
    hits = []
    replacements = []
    ordered_snippets = sorted(snippets, key=lambda snippet: len(snippet.trigger), reverse=True)

    for snippet in ordered_snippets:
        pattern = re.compile(rf"(?<!\w){re.escape(snippet.trigger)}(?!\w)", re.IGNORECASE)
        token = f"__WHISPRBAR_SNIPPET_{len(replacements)}__"
        result, count = pattern.subn(token, result)
        if count:
            hits.append(snippet.trigger)
            replacements.append((token, snippet.text))

    for token, replacement in replacements:
        result = result.replace(token, replacement)

    return result, tuple(hits)
