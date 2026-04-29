"""Local Flow Mode history statistics."""

from typing import Any, Dict, List, Sequence


def compute_dictation_stats(entries: Sequence[dict]) -> Dict[str, Any]:
    """Compute local dictation statistics from history entries."""
    session_count = len(entries)
    word_count = 0
    duration_seconds = 0.0
    for entry in entries:
        try:
            word_count += int(entry.get("word_count") or len(str(entry.get("text", "")).split()))
        except (TypeError, ValueError):
            word_count += len(str(entry.get("text", "")).split())
        try:
            duration_seconds += float(entry.get("duration_seconds") or 0.0)
        except (TypeError, ValueError):
            pass

    words_per_minute = 0.0
    if duration_seconds > 0:
        words_per_minute = round(word_count / (duration_seconds / 60.0), 1)

    return {
        "session_count": session_count,
        "word_count": word_count,
        "duration_seconds": round(duration_seconds, 3),
        "words_per_minute": words_per_minute,
    }


def recent_activity(entries: Sequence[dict], limit: int = 20) -> List[dict]:
    """Return the most recent local history entries."""
    if limit <= 0:
        return []
    return list(entries[-limit:])
