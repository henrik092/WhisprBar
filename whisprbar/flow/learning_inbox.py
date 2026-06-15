"""Local review-state and candidate mining for Flow learning suggestions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from whisprbar.config import DATA_DIR
from whisprbar.flow.dictionary import DICTIONARY_PATH, load_dictionary, save_dictionary
from whisprbar.flow.models import DictionaryEntry
from whisprbar.transcript_store import DATABASE_PATH
from whisprbar.utils import debug

LEARNING_STATE_VERSION = 1
LEARNING_INBOX_PATH = DATA_DIR / "learning_inbox.json"
VALID_STATUSES = {"approved", "dismissed", "never"}
_TOKEN_PATTERN = re.compile(r"[\w][\w'-]*", re.UNICODE)
_KNOWN_REVIEW_TERMS = {"Codex", "GitHub", "OpenAI", "WhisprBar"}


@dataclass(frozen=True)
class LearningCandidate:
    """A body-free learning suggestion that must be reviewed before use."""

    kind: str
    spoken: str
    written: str
    evidence_count: int
    status: str = "pending"

    @property
    def id(self) -> str:
        payload = f"{self.kind}\0{self.spoken.casefold()}\0{self.written}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_public_dict(self) -> dict[str, object]:
        """Return the Settings/UI-safe form without transcript bodies."""
        return {
            "id": self.id,
            "kind": self.kind,
            "spoken": self.spoken,
            "written": self.written,
            "evidence_count": self.evidence_count,
            "status": self.status,
        }


def load_learning_state(path: Optional[Path] = None) -> dict[str, Any]:
    """Load review decisions for local learning suggestions."""
    state_path = Path(path or LEARNING_INBOX_PATH)
    if not state_path.exists():
        return {"version": LEARNING_STATE_VERSION, "items": {}}

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        debug(f"Failed to load Flow learning inbox state {state_path}: {exc}")
        return {"version": LEARNING_STATE_VERSION, "items": {}}

    if not isinstance(data, dict):
        return {"version": LEARNING_STATE_VERSION, "items": {}}
    raw_items = data.get("items")
    if not isinstance(raw_items, dict):
        raw_items = {}

    items: dict[str, dict[str, str]] = {}
    for candidate_id, item in raw_items.items():
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "").strip()
        if status not in VALID_STATUSES:
            continue
        updated_at = str(item.get("updated_at") or "")
        items[str(candidate_id)] = {"status": status, "updated_at": updated_at}

    return {"version": LEARNING_STATE_VERSION, "items": items}


def save_learning_state(state: Mapping[str, object], path: Optional[Path] = None) -> None:
    """Persist review decisions with private-file permissions."""
    state_path = Path(path or LEARNING_INBOX_PATH)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    items = state.get("items") if isinstance(state.get("items"), Mapping) else {}
    payload = {"version": LEARNING_STATE_VERSION, "items": items}
    temporary_path = state_path.with_name(f".{state_path.name}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.chmod(0o600)
    os.replace(temporary_path, state_path)
    state_path.chmod(0o600)


def set_learning_candidate_status(
    candidate_id: str,
    status: str,
    *,
    state_path: Optional[Path] = None,
) -> None:
    """Record an explicit review decision for a candidate."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid learning candidate status: {status}")
    state = load_learning_state(state_path)
    items = state.setdefault("items", {})
    if not isinstance(items, dict):
        items = {}
        state["items"] = items
    items[str(candidate_id)] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_learning_state(state, state_path)


def apply_learning_candidate_status(
    candidate_id: str,
    status: str,
    *,
    database_path: Path = DATABASE_PATH,
    state_path: Optional[Path] = None,
    dictionary_path: Optional[Path] = None,
    min_evidence: int = 2,
) -> None:
    """Apply a review decision, writing approved dictionary candidates."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid learning candidate status: {status}")

    dictionary_file = Path(dictionary_path or DICTIONARY_PATH)
    entries = load_dictionary(dictionary_file)
    candidates = build_learning_candidates(
        database_path=Path(database_path),
        existing_dictionary=entries,
        min_evidence=min_evidence,
    )
    candidate = next((item for item in candidates if item.id == candidate_id), None)
    if candidate is None:
        raise ValueError(f"unknown learning candidate: {candidate_id}")

    if status == "approved" and candidate.kind == "dictionary":
        existing = _existing_dictionary_keys(entries)
        key = (candidate.spoken.strip().casefold(), candidate.written.strip())
        if key not in existing:
            entries.append(DictionaryEntry(spoken=candidate.spoken, written=candidate.written))
            save_dictionary(entries, dictionary_file)

    set_learning_candidate_status(candidate_id, status, state_path=state_path)


def _tokens(text: str) -> list[str]:
    return [match.group(0) for match in _TOKEN_PATTERN.finditer(text or "")]


def _is_reviewable_written_term(written: str) -> bool:
    if written in _KNOWN_REVIEW_TERMS:
        return True
    return any(character.isupper() for character in written[1:])


def _existing_dictionary_keys(entries: Iterable[DictionaryEntry]) -> set[tuple[str, str]]:
    return {
        (entry.spoken.strip().casefold(), entry.written.strip())
        for entry in entries
        if entry.spoken.strip() and entry.written.strip()
    }


def _dictionary_candidate_counts(
    *,
    database_path: Path,
    existing_dictionary: Iterable[DictionaryEntry],
) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    existing = _existing_dictionary_keys(existing_dictionary)
    if not database_path.exists():
        return counts

    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        for raw_text, final_text in connection.execute(
            "SELECT raw_text, text FROM transcripts WHERE raw_text IS NOT NULL AND raw_text != text"
        ):
            raw_tokens = _tokens(str(raw_text or ""))
            final_tokens = _tokens(str(final_text or ""))
            if len(raw_tokens) != len(final_tokens):
                continue
            for raw_token, final_token in zip(raw_tokens, final_tokens):
                spoken = raw_token.strip()
                written = final_token.strip()
                if not spoken or not written or spoken == written:
                    continue
                if spoken.casefold() != written.casefold():
                    continue
                if not _is_reviewable_written_term(written):
                    continue
                key = (spoken.casefold(), written)
                if key in existing:
                    continue
                counts[key] += 1
    finally:
        connection.close()
    return counts


def build_learning_candidates(
    *,
    database_path: Path = DATABASE_PATH,
    existing_dictionary: Optional[Iterable[DictionaryEntry]] = None,
    min_evidence: int = 2,
) -> list[LearningCandidate]:
    """Build conservative local suggestions without returning transcript bodies."""
    dictionary_entries = (
        list(existing_dictionary)
        if existing_dictionary is not None
        else load_dictionary()
    )
    counts = _dictionary_candidate_counts(
        database_path=Path(database_path),
        existing_dictionary=dictionary_entries,
    )
    candidates = [
        LearningCandidate(
            kind="dictionary",
            spoken=spoken,
            written=written,
            evidence_count=count,
        )
        for (spoken, written), count in counts.items()
        if count >= min_evidence
    ]
    return sorted(candidates, key=lambda item: (-item.evidence_count, item.written, item.spoken))


def get_learning_inbox_summary(
    *,
    database_path: Path = DATABASE_PATH,
    state_path: Optional[Path] = None,
    dictionary_path: Optional[Path] = None,
    min_evidence: int = 2,
    include_reviewed: bool = False,
    enabled: bool = True,
) -> dict[str, object]:
    """Return a body-free Learning Inbox summary for Settings."""
    state_file = Path(state_path or LEARNING_INBOX_PATH)
    summary: dict[str, object] = {
        "state_path": str(state_file),
        "total_candidates": 0,
        "pending_count": 0,
        "approved_count": 0,
        "dismissed_count": 0,
        "never_count": 0,
        "candidates": [],
        "error": None,
    }
    if not enabled:
        return summary
    try:
        state = load_learning_state(state_file)
        review_items = state.get("items") if isinstance(state.get("items"), Mapping) else {}
        candidates = build_learning_candidates(
            database_path=Path(database_path),
            existing_dictionary=load_dictionary(dictionary_path) if dictionary_path else None,
            min_evidence=min_evidence,
        )
    except Exception as exc:
        summary["error"] = str(exc)
        return summary

    public_candidates = []
    for candidate in candidates:
        review_item = review_items.get(candidate.id) if isinstance(review_items, Mapping) else None
        status = "pending"
        if isinstance(review_item, Mapping):
            status = str(review_item.get("status") or "pending")
        if status not in {"pending", *VALID_STATUSES}:
            status = "pending"
        summary["total_candidates"] = int(summary["total_candidates"]) + 1
        count_key = f"{status}_count"
        summary[count_key] = int(summary.get(count_key, 0)) + 1
        if status == "pending" or include_reviewed:
            public_candidates.append(
                LearningCandidate(
                    kind=candidate.kind,
                    spoken=candidate.spoken,
                    written=candidate.written,
                    evidence_count=candidate.evidence_count,
                    status=status,
                ).to_public_dict()
            )

    summary["candidates"] = public_candidates
    return summary
