"""Optional AI rewrite support for Flow Mode."""

import json
import os
import threading
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from whisprbar.config import load_env_file_values
from whisprbar.flow.models import AppContext, FlowProfile
from whisprbar.utils import debug


@dataclass(frozen=True)
class RewriteResult:
    """Result from optional rewrite processing."""

    text: str
    status: str


class RewriteProvider(Protocol):
    """Provider interface for rewrite implementations."""

    def rewrite(self, text: str, prompt: str, cfg: dict) -> str:
        """Return rewritten text."""


class OpenAICompatibleRewriteProvider:
    """Minimal OpenAI-compatible chat completions provider."""

    def rewrite(self, text: str, prompt: str, cfg: dict) -> str:
        env_values = load_env_file_values()
        api_key = (
            os.environ.get("WHISPRBAR_FLOW_REWRITE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or env_values.get("WHISPRBAR_FLOW_REWRITE_API_KEY")
            or env_values.get("OPENAI_API_KEY")
        )
        model = cfg.get("flow_rewrite_model") or ""
        if not api_key or not model:
            raise ValueError("rewrite provider not configured")

        base_url = (
            os.environ.get("WHISPRBAR_FLOW_REWRITE_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        url = f"{base_url}/chat/completions"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout = float(cfg.get("flow_rewrite_timeout_seconds", 12.0))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"].strip()


def _rewrite_instruction(rewrite_mode: str) -> str:
    """Return mode-specific rewrite guidance for the provider prompt."""
    instructions = {
        "correct_english": (
            "Correct English spelling, grammar, punctuation, and wording. "
            "Preserve the original meaning, tone, names, and technical terms. "
            "Do not translate non-English proper nouns or code."
        ),
        "humanize": (
            "Remove AI-sounding patterns while keeping the text useful and natural. "
            "Preserve the language, meaning, facts, names, and technical terms. "
            "Use simple direct wording, varied sentence rhythm, and a real human voice. "
            "Do not start with Here is, Here's, Of course, or Certainly. "
            "Forbidden output words and phrases: highlight, highlights, underscore, underscores, "
            "crucial, pivotal, important, key, comprehensive overview. "
            "If the source uses those words, replace them with specific plain wording or remove the claim. "
            "Avoid promotional language, fake significance, generic conclusions, "
            "overused AI vocabulary, signposting, rule-of-three padding, excessive "
            "hedging, bold labels, emojis, and mechanical list structure. "
            "Use straight quotes and apostrophes. "
            "Do not include a draft, audit, bullets, or explanation."
        ),
        "translate_english": (
            "Translate the text to natural English. Preserve names, numbers, "
            "technical terms, and the intended tone."
        ),
        "professional": "Make the text professional while preserving the original meaning.",
        "shorter": "Make the text shorter without dropping important meaning.",
        "longer": "Make the text more detailed without inventing facts.",
        "list": "Format the text as a clear list.",
        "structured": "Structure the text clearly while preserving the original meaning.",
        "concise": "Make the text concise and conversational.",
        "clean": "Clean up dictated wording while preserving the original meaning.",
    }
    return instructions.get(
        rewrite_mode,
        "Clean up the dictated text while preserving the original meaning.",
    )


def build_rewrite_prompt(
    language: str,
    context: AppContext,
    profile: FlowProfile,
    command: Optional[str],
    dictionary_terms: Sequence[str],
) -> str:
    """Build a deterministic rewrite instruction prompt."""
    terms = ", ".join(dictionary_terms) if dictionary_terms else "None"
    rewrite_mode = profile.rewrite_mode or "clean"
    return "\n".join(
        [
            "Rewrite dictation text for insertion into the active app.",
            f"Language: {language}",
            f"Profile: {profile.profile_id}",
            f"Style: {profile.style}",
            f"Rewrite mode: {rewrite_mode}",
            f"Command: {command or 'none'}",
            f"Instruction: {_rewrite_instruction(rewrite_mode)}",
            f"Active app class: {context.app_class or 'unknown'}",
            f"Active window title: {context.window_title or 'unknown'}",
            f"Must-preserve terms: {terms}",
            "Return only the final text. Do not add explanations.",
        ]
    )


def _configured_provider(cfg: dict) -> Optional[RewriteProvider]:
    provider_name = cfg.get("flow_rewrite_provider", "none")
    if provider_name == "openai_compatible":
        return OpenAICompatibleRewriteProvider()
    return None


def rewrite_text(
    text: str,
    language: str,
    context: AppContext,
    profile: FlowProfile,
    command: Optional[str],
    dictionary_terms: Sequence[str],
    cfg: dict,
    provider: Optional[RewriteProvider] = None,
) -> RewriteResult:
    """Optionally rewrite text, preserving original text on any failure."""
    if not text:
        return RewriteResult(text=text, status="not_requested")

    selected_provider = provider or _configured_provider(cfg)
    if selected_provider is None:
        return RewriteResult(text=text, status="not_requested")

    prompt = build_rewrite_prompt(language, context, profile, command, dictionary_terms)
    timeout = max(0.001, float(cfg.get("flow_rewrite_timeout_seconds", 12.0)))
    result_box = [None]
    exc_box = [None]

    def worker():
        try:
            result_box[0] = selected_provider.rewrite(text, prompt, cfg)
        except Exception as exc:
            exc_box[0] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        debug("Flow rewrite timed out")
        return RewriteResult(text=text, status="timeout")
    if exc_box[0] is not None:
        status = "not_configured" if isinstance(exc_box[0], ValueError) else "failed"
        debug(f"Flow rewrite failed: {exc_box[0]}")
        return RewriteResult(text=text, status=status)
    rewritten = str(result_box[0] or "").strip()
    if not rewritten:
        return RewriteResult(text=text, status="failed")
    return RewriteResult(text=rewritten, status="applied")
