"""Safe local dictionary learning from completed Flow transcripts.

The learning path is intentionally offline and review-first: it analyzes raw vs.
final transcript pairs, writes candidates for review, and only merges very safe
short technical/proper-name replacements when explicitly requested.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, DefaultDict, Iterable, Mapping, Sequence

from whisprbar.config import DATA_DIR
from whisprbar.flow.dictionary import DICTIONARY_PATH, load_dictionary, save_dictionary
from whisprbar.flow.models import DictionaryEntry
from whisprbar.transcript_store import DATABASE_PATH

CANDIDATES_PATH = Path.home() / ".config" / "whisprbar" / "dictionary_candidates.json"
LEARNING_REPORT_PATH = DATA_DIR / "dictionary_learning_report.md"
WORD_RE = re.compile(
    r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:[+#/.-][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*",
    re.UNICODE,
)
MAX_PHRASE_TOKENS = 5
MAX_EXAMPLE_CHARS = 160


@dataclass(frozen=True)
class TranscriptSample:
    """Raw/final text pair used for dictionary learning."""

    text: str
    raw_text: str = ""
    created_at: str = ""
    language: str = ""
    backend: str = ""
    profile_id: str = ""
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DictionaryCandidate:
    """Reviewable spoken-to-written dictionary candidate."""

    spoken: str
    written: str
    count: int
    confidence: float
    reason: str
    examples: tuple[str, ...] = ()
    auto_apply_eligible: bool = False


def _words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def _norm_phrase(text: str) -> str:
    return " ".join(_words(text.lower()))


def _phrase_from_tokens(tokens: Sequence[str]) -> str:
    return " ".join(token.strip() for token in tokens if token.strip()).strip()


def _truncate(text: str, limit: int = MAX_EXAMPLE_CHARS) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _is_valid_replacement_phrase(spoken: str, written: str) -> bool:
    spoken_words = _words(spoken)
    written_words = _words(written)
    if not spoken_words or not written_words:
        return False
    if len(spoken_words) > MAX_PHRASE_TOKENS or len(written_words) > MAX_PHRASE_TOKENS:
        return False
    if _norm_phrase(spoken) == _norm_phrase(written):
        # Capitalization-only changes are formatting, not dictionary learning.
        return False
    if len(spoken) > 80 or len(written) > 80:
        return False
    return True


def _is_safe_written_term(written: str) -> bool:
    """Return True for short technical/proper terms safe enough to auto-merge."""
    term = written.strip()
    if not term or len(term) > 60 or len(_words(term)) > 4:
        return False
    if any(ch.isdigit() for ch in term):
        return True
    if any(ch in term for ch in "+#./-"):
        return True
    if len(term) >= 2 and term.upper() == term and any(ch.isalpha() for ch in term):
        return True
    # CamelCase / mixed-case product names: WhisprBar, ChatGPT, OpenRouter.
    return any(ch.isupper() for ch in term[1:])


def _candidate_confidence(count: int, written: str) -> float:
    if _is_safe_written_term(written):
        return min(0.99, 0.84 + min(count, 4) * 0.04)
    return min(0.85, 0.60 + min(count, 5) * 0.04)


def _existing_pairs(entries: Iterable[DictionaryEntry]) -> set[tuple[str, str]]:
    return {(_norm_phrase(entry.spoken), _norm_phrase(entry.written)) for entry in entries}


def _raw_final_replacements(sample: TranscriptSample) -> list[tuple[str, str]]:
    raw_tokens = _words(sample.raw_text)
    final_tokens = _words(sample.text)
    if not raw_tokens or not final_tokens:
        return []

    replacements: list[tuple[str, str]] = []
    matcher = difflib.SequenceMatcher(a=raw_tokens, b=final_tokens, autojunk=False)
    for tag, raw_start, raw_end, final_start, final_end in matcher.get_opcodes():
        if tag != "replace":
            continue
        spoken = _phrase_from_tokens(raw_tokens[raw_start:raw_end])
        written = _phrase_from_tokens(final_tokens[final_start:final_end])
        if _is_valid_replacement_phrase(spoken, written):
            replacements.append((spoken, written))
    return replacements


def suggest_dictionary_candidates(
    samples: Sequence[TranscriptSample],
    existing_entries: Sequence[DictionaryEntry] = (),
    min_count: int = 2,
    max_examples: int = 3,
) -> list[DictionaryCandidate]:
    """Suggest reviewable dictionary entries from repeated raw→final replacements."""
    min_count = max(1, int(min_count))
    known_pairs = _existing_pairs(existing_entries)
    counts: Counter[tuple[str, str]] = Counter()
    spoken_variants: DefaultDict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    written_variants: DefaultDict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    examples: DefaultDict[tuple[str, str], list[str]] = defaultdict(list)

    for sample in samples:
        seen_in_sample: set[tuple[str, str]] = set()
        for spoken, written in _raw_final_replacements(sample):
            key = (_norm_phrase(spoken), _norm_phrase(written))
            if key in known_pairs or key in seen_in_sample:
                continue
            seen_in_sample.add(key)
            counts[key] += 1
            spoken_variants[key][spoken] += 1
            written_variants[key][written] += 1
            if len(examples[key]) < max_examples:
                examples[key].append(
                    f"{spoken} → {written}: {_truncate(sample.raw_text or sample.text)}"
                )

    candidates: list[DictionaryCandidate] = []
    for key, count in counts.items():
        if count < min_count:
            continue
        spoken = spoken_variants[key].most_common(1)[0][0]
        written = written_variants[key].most_common(1)[0][0]
        confidence = _candidate_confidence(count, written)
        auto_apply_eligible = _is_safe_written_term(written) and confidence >= 0.90
        candidates.append(
            DictionaryCandidate(
                spoken=spoken,
                written=written,
                count=count,
                confidence=round(confidence, 3),
                reason="raw_final_replacement",
                examples=tuple(examples[key]),
                auto_apply_eligible=auto_apply_eligible,
            )
        )

    return sorted(candidates, key=lambda item: (-item.count, -item.confidence, item.written.lower()))


def load_transcript_samples(
    database_path: Path = DATABASE_PATH,
    limit: int = 1000,
) -> list[TranscriptSample]:
    """Load recent transcript samples read-only from the SQLite transcript store."""
    database_path = Path(database_path)
    if not database_path.exists():
        return []

    limit = max(1, int(limit))
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT created_at, language, text, raw_text, backend, profile_id, metadata_json
            FROM transcripts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()

    samples: list[TranscriptSample] = []
    for created_at, language, text, raw_text, backend, profile_id, metadata_json in rows:
        try:
            metadata = json.loads(metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        samples.append(
            TranscriptSample(
                text=str(text or ""),
                raw_text=str(raw_text or ""),
                created_at=str(created_at or ""),
                language=str(language or ""),
                backend=str(backend or ""),
                profile_id=str(profile_id or ""),
                metadata=metadata,
            )
        )
    return samples


def save_dictionary_candidates(
    candidates: Sequence[DictionaryCandidate],
    path: Path = CANDIDATES_PATH,
) -> None:
    """Persist candidates as reviewable JSON without touching the live dictionary."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(candidate) for candidate in candidates]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_safe_dictionary_candidates(
    candidates: Sequence[DictionaryCandidate],
    dictionary_path: Path = DICTIONARY_PATH,
    min_confidence: float = 0.90,
    min_count: int = 3,
) -> list[DictionaryEntry]:
    """Merge only conservative short technical-term candidates into the dictionary."""
    entries = load_dictionary(dictionary_path)
    known_pairs = _existing_pairs(entries)
    applied: list[DictionaryEntry] = []

    for candidate in candidates:
        key = (_norm_phrase(candidate.spoken), _norm_phrase(candidate.written))
        if key in known_pairs:
            continue
        if not candidate.auto_apply_eligible:
            continue
        if candidate.count < min_count or candidate.confidence < min_confidence:
            continue
        if not _is_safe_written_term(candidate.written):
            continue
        entry = DictionaryEntry(spoken=candidate.spoken, written=candidate.written)
        entries.append(entry)
        applied.append(entry)
        known_pairs.add(key)

    if applied:
        save_dictionary(entries, dictionary_path)
    return applied


def write_learning_report(
    summary: Mapping[str, Any],
    candidates: Sequence[DictionaryCandidate],
    applied: Sequence[DictionaryEntry],
    path: Path = LEARNING_REPORT_PATH,
) -> None:
    """Write a compact Markdown report for manual review."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# WhisprBar Dictionary Learning Report",
        "",
        f"- Samples analyzed: {summary.get('sample_count', 0)}",
        f"- Candidates found: {summary.get('candidate_count', 0)}",
        f"- Safe entries applied: {summary.get('applied_count', 0)}",
        f"- Candidates file: `{summary.get('candidates_path', '')}`",
        f"- Dictionary file: `{summary.get('dictionary_path', '')}`",
        "",
        "## Candidates",
        "",
    ]
    if not candidates:
        lines.append("No repeated raw→final replacements found.")
    else:
        lines.extend([
            "| spoken | written | count | confidence | auto |",
            "|---|---|---:|---:|---|",
        ])
        for candidate in candidates[:50]:
            spoken = candidate.spoken.replace("|", "\\|")
            written = candidate.written.replace("|", "\\|")
            auto = "yes" if candidate.auto_apply_eligible else "review"
            lines.append(
                f"| {spoken} | {written} | {candidate.count} | "
                f"{candidate.confidence:.2f} | {auto} |"
            )
    if applied:
        lines.extend(["", "## Applied safely", ""])
        for entry in applied:
            lines.append(f"- `{entry.spoken}` → `{entry.written}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_dictionary_learning(
    database_path: Path = DATABASE_PATH,
    dictionary_path: Path = DICTIONARY_PATH,
    candidates_path: Path = CANDIDATES_PATH,
    report_path: Path = LEARNING_REPORT_PATH,
    limit: int = 1000,
    min_count: int = 2,
    apply_safe: bool = False,
) -> dict[str, Any]:
    """Analyze transcript history and write reviewable dictionary candidates."""
    samples = load_transcript_samples(database_path=database_path, limit=limit)
    existing_entries = load_dictionary(dictionary_path)
    candidates = suggest_dictionary_candidates(
        samples,
        existing_entries=existing_entries,
        min_count=min_count,
    )
    save_dictionary_candidates(candidates, candidates_path)
    applied = (
        apply_safe_dictionary_candidates(candidates, dictionary_path=dictionary_path)
        if apply_safe
        else []
    )
    summary: dict[str, Any] = {
        "sample_count": len(samples),
        "candidate_count": len(candidates),
        "applied_count": len(applied),
        "database_path": str(database_path),
        "dictionary_path": str(dictionary_path),
        "candidates_path": str(candidates_path),
        "report_path": str(report_path),
    }
    write_learning_report(summary, candidates, applied, report_path)
    return summary


__all__ = [
    "CANDIDATES_PATH",
    "LEARNING_REPORT_PATH",
    "DictionaryCandidate",
    "TranscriptSample",
    "apply_safe_dictionary_candidates",
    "load_transcript_samples",
    "run_dictionary_learning",
    "save_dictionary_candidates",
    "suggest_dictionary_candidates",
    "write_learning_report",
]
