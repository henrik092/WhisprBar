"""Local dictionary corrections for Flow Mode."""

import json
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from whisprbar.flow.models import DictionaryEntry
from whisprbar.utils import debug

DICTIONARY_PATH = Path.home() / ".config" / "whisprbar" / "dictionary.json"


def load_dictionary(path: Optional[Path] = None) -> List[DictionaryEntry]:
    """Load dictionary entries from JSON."""
    dictionary_path = path or DICTIONARY_PATH
    if not dictionary_path.exists():
        return []

    try:
        data = json.loads(dictionary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        debug(f"Failed to load Flow dictionary {dictionary_path}: {exc}")
        return []

    entries: List[DictionaryEntry] = []
    if not isinstance(data, list):
        return entries

    for item in data:
        if not isinstance(item, dict):
            continue
        spoken = str(item.get("spoken", "")).strip()
        written = str(item.get("written", "")).strip()
        if spoken and written:
            entries.append(DictionaryEntry(spoken=spoken, written=written))
    return entries


def apply_dictionary(
    text: str, entries: Sequence[DictionaryEntry]
) -> Tuple[str, Tuple[str, ...]]:
    """Apply case-insensitive phrase replacements and return hit labels."""
    result = text
    hits = []
    replacements = []
    ordered_entries = sorted(entries, key=lambda entry: len(entry.spoken), reverse=True)

    for entry in ordered_entries:
        pattern = re.compile(rf"(?<!\w){re.escape(entry.spoken)}(?!\w)", re.IGNORECASE)
        token = f"__WHISPRBAR_DICT_{len(replacements)}__"
        result, count = pattern.subn(token, result)
        if count:
            hits.append(entry.spoken)
            replacements.append((token, entry.written))

    for token, written in replacements:
        result = result.replace(token, written)

    return result, tuple(hits)
