"""Tests for local Flow scratchpad storage."""

import pytest

from whisprbar.ui.scratchpad import create_note, list_notes, update_note


@pytest.mark.unit
def test_create_note_writes_note(tmp_path):
    path = tmp_path / "notes.jsonl"

    note = create_note("Draft text", path=path)

    assert note["text"] == "Draft text"
    assert len(list_notes(path=path)) == 1


@pytest.mark.unit
def test_update_note_replaces_existing_note(tmp_path):
    path = tmp_path / "notes.jsonl"
    note = create_note("Draft", path=path)

    updated = update_note(note["id"], "Final", path=path)

    assert updated["text"] == "Final"
    assert list_notes(path=path)[0]["text"] == "Final"


@pytest.mark.unit
def test_list_notes_skips_invalid_jsonl(tmp_path):
    path = tmp_path / "notes.jsonl"
    path.write_text('{"id": "1", "text": "Valid"}\nnot json\n', encoding="utf-8")

    assert list_notes(path=path) == [{"id": "1", "text": "Valid"}]


@pytest.mark.unit
def test_never_store_requires_explicit_storage(tmp_path):
    path = tmp_path / "notes.jsonl"

    note = create_note("Private", path=path, storage_enabled=False)

    assert note["text"] == "Private"
    assert not path.exists()
