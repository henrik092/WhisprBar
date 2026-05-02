"""Flow Mode text pipeline orchestration."""

from dataclasses import asdict, replace
from typing import Dict

from whisprbar.flow.commands import detect_command
from whisprbar.flow.context import detect_app_context
from whisprbar.flow.dictionary import apply_dictionary, load_dictionary
from whisprbar.flow.formatting import apply_backtrack, apply_smart_formatting
from whisprbar.flow.models import FlowOutput
from whisprbar.flow.profiles import resolve_profile
from whisprbar.flow.rewrite import rewrite_text
from whisprbar.flow.snippets import apply_snippets, load_snippets
from whisprbar.transcription.postprocess import (
    postprocess_fix_capitalization,
    postprocess_fix_spacing,
)


def _basic_postprocess(text: str, language: str, cfg: dict) -> str:
    if not cfg.get("postprocess_enabled", True):
        return text
    result = text
    if cfg.get("postprocess_fix_spacing", True):
        result = postprocess_fix_spacing(result)
    if cfg.get("postprocess_fix_capitalization", True):
        result = postprocess_fix_capitalization(result, language)
    return result


def _metadata(context, profile, extra: Dict[str, object]) -> Dict[str, object]:
    data: Dict[str, object] = {
        "profile_id": profile.profile_id,
        "profile_style": profile.style,
        "context": asdict(context),
    }
    data.update(extra)
    return data


def process_flow_text(raw_text: str, language: str, cfg: dict) -> FlowOutput:
    """Process raw transcript text through the Flow pipeline."""
    context = detect_app_context() if cfg.get("flow_context_awareness_enabled", True) else detect_app_context("unknown")
    profile = resolve_profile(context, cfg)
    local_text = _basic_postprocess(raw_text, language, cfg)

    metadata_extra: Dict[str, object] = {}
    dictionary_hits = ()
    snippet_hits = ()
    command_id = None
    command_rewrite_mode = None
    paste_policy = None

    if cfg.get("flow_mode_enabled", False):
        local_text, backtrack_hits = apply_backtrack(
            local_text,
            language,
            cfg.get("flow_backtrack_enabled", True),
        )
        if backtrack_hits:
            metadata_extra["backtrack_hits"] = backtrack_hits

        local_text, formatting_metadata = apply_smart_formatting(local_text, language, profile, cfg)
        metadata_extra.update(formatting_metadata)

        if cfg.get("flow_dictionary_enabled", True):
            local_text, dictionary_hits = apply_dictionary(local_text, load_dictionary())

        if cfg.get("flow_snippets_enabled", True):
            local_text, snippet_hits = apply_snippets(local_text, load_snippets())

        command = detect_command(
            local_text,
            language,
            enabled=cfg.get("flow_command_mode_enabled", True),
        )
        local_text = command.text
        command_id = command.command_id
        command_rewrite_mode = command.rewrite_mode
        paste_policy = command.paste_policy
        if command_id:
            metadata_extra["command"] = command_id

    rewrite_status = "not_requested"
    final_text = local_text
    rewrite_profile = (
        replace(profile, rewrite_mode=command_rewrite_mode)
        if command_rewrite_mode
        else profile
    )
    should_rewrite = (
        cfg.get("flow_mode_enabled", False)
        and cfg.get("flow_rewrite_enabled", False)
        and rewrite_profile.rewrite_mode != "none"
    )
    if should_rewrite:
        rewrite_result = rewrite_text(
            text=local_text,
            language=language,
            context=context,
            profile=rewrite_profile,
            command=command_id,
            dictionary_terms=dictionary_hits,
            cfg=cfg,
        )
        final_text = rewrite_result.text
        rewrite_status = rewrite_result.status

    metadata_extra["rewrite_status"] = rewrite_status
    metadata_extra["dictionary_hits"] = dictionary_hits
    metadata_extra["snippet_hits"] = snippet_hits

    return FlowOutput(
        raw_text=raw_text,
        final_text=final_text,
        profile_id=profile.profile_id,
        rewrite_status=rewrite_status,
        command=command_id,
        dictionary_hits=dictionary_hits,
        snippet_hits=snippet_hits,
        paste_policy=paste_policy,
        metadata=_metadata(context, profile, metadata_extra),
    )
