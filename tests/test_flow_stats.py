"""Tests for Flow Mode history stats."""

import pytest

from whisprbar.flow.stats import compute_dictation_stats, recent_activity


@pytest.mark.unit
def test_compute_dictation_stats_from_history_entries():
    stats = compute_dictation_stats([
        {"text": "hello world", "word_count": 2, "duration_seconds": 1.0},
        {"text": "another test", "word_count": 2, "duration_seconds": 3.0},
    ])

    assert stats["session_count"] == 2
    assert stats["word_count"] == 4
    assert stats["duration_seconds"] == 4.0
    assert stats["words_per_minute"] == 60.0


@pytest.mark.unit
def test_compute_dictation_stats_uses_text_when_word_count_missing():
    stats = compute_dictation_stats([{"text": "hello world again", "duration_seconds": 6.0}])

    assert stats["word_count"] == 3
    assert stats["words_per_minute"] == 30.0


@pytest.mark.unit
def test_recent_activity_limits_entries():
    entries = [{"text": str(i)} for i in range(5)]

    assert recent_activity(entries, limit=2) == [{"text": "3"}, {"text": "4"}]
