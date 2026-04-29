"""Data models for WhisprBar Flow Mode."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class AppContext:
    """Active application context used for profile resolution."""

    session_type: str
    app_class: str = ""
    app_name: str = ""
    window_title: str = ""


@dataclass(frozen=True)
class FlowProfile:
    """Resolved Flow profile for an application category."""

    profile_id: str
    label: str
    style: str = "plain"
    rewrite_mode: str = "none"
    paste_sequence: Optional[str] = None
    add_space: Optional[bool] = None
    add_newline: Optional[bool] = None


@dataclass(frozen=True)
class PastePolicy:
    """Per-output paste behavior override."""

    sequence: Optional[str] = None
    add_space: Optional[bool] = None
    add_newline: Optional[bool] = None
    clipboard_only: bool = False
    press_enter_after_paste: bool = False


@dataclass(frozen=True)
class FlowInput:
    """Raw transcript and context entering the Flow pipeline."""

    text: str
    language: str
    context: AppContext


@dataclass(frozen=True)
class FlowOutput:
    """Final Flow pipeline result and audit metadata."""

    raw_text: str
    final_text: str
    profile_id: str
    rewrite_status: str = "not_requested"
    command: Optional[str] = None
    dictionary_hits: Tuple[str, ...] = ()
    snippet_hits: Tuple[str, ...] = ()
    paste_policy: Optional[PastePolicy] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DictionaryEntry:
    """Spoken phrase to written replacement."""

    spoken: str
    written: str


@dataclass(frozen=True)
class Snippet:
    """Spoken trigger to text expansion."""

    trigger: str
    text: str


@dataclass(frozen=True)
class CommandDetection:
    """Detected command and its effect on text processing."""

    text: str
    command_id: Optional[str] = None
    rewrite_mode: Optional[str] = None
    paste_policy: Optional[PastePolicy] = None

