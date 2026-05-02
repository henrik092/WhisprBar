"""Tests for Flow Mode optional rewrite provider."""

import time

import pytest

from whisprbar.flow.models import AppContext, FlowProfile
from whisprbar.flow.rewrite import (
    OpenAICompatibleRewriteProvider,
    RewriteResult,
    build_rewrite_prompt,
    rewrite_text,
)


class EchoProvider:
    def rewrite(self, text, prompt, cfg):
        return f"rewritten: {text}"


class FailingProvider:
    def rewrite(self, text, prompt, cfg):
        raise RuntimeError("provider failed")


class SlowProvider:
    def rewrite(self, text, prompt, cfg):
        time.sleep(0.2)
        return "late"


class FakeURLResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"Corrected text."}}]}'


@pytest.mark.unit
def test_rewrite_provider_none_returns_original_text():
    result = rewrite_text(
        "hello",
        language="en",
        context=AppContext("x11"),
        profile=FlowProfile("default", "Default"),
        command=None,
        dictionary_terms=(),
        cfg={"flow_rewrite_provider": "none"},
    )

    assert result == RewriteResult(text="hello", status="not_requested")


@pytest.mark.unit
def test_empty_text_never_calls_provider():
    result = rewrite_text(
        "",
        language="en",
        context=AppContext("x11"),
        profile=FlowProfile("default", "Default"),
        command="professional",
        dictionary_terms=(),
        cfg={"flow_rewrite_provider": "openai_compatible"},
        provider=FailingProvider(),
    )

    assert result == RewriteResult(text="", status="not_requested")


@pytest.mark.unit
def test_provider_exception_returns_original_text():
    result = rewrite_text(
        "hello",
        language="en",
        context=AppContext("x11"),
        profile=FlowProfile("default", "Default"),
        command="professional",
        dictionary_terms=(),
        cfg={"flow_rewrite_provider": "openai_compatible", "flow_rewrite_timeout_seconds": 1},
        provider=FailingProvider(),
    )

    assert result == RewriteResult(text="hello", status="failed")


@pytest.mark.unit
def test_provider_timeout_returns_original_text():
    result = rewrite_text(
        "hello",
        language="en",
        context=AppContext("x11"),
        profile=FlowProfile("default", "Default"),
        command="professional",
        dictionary_terms=(),
        cfg={"flow_rewrite_provider": "openai_compatible", "flow_rewrite_timeout_seconds": 0.01},
        provider=SlowProvider(),
    )

    assert result == RewriteResult(text="hello", status="timeout")


@pytest.mark.unit
def test_provider_success_returns_rewritten_text():
    result = rewrite_text(
        "hello",
        language="en",
        context=AppContext("x11", app_class="thunderbird", window_title="Inbox"),
        profile=FlowProfile("email", "Email", style="professional", rewrite_mode="professional"),
        command="professional",
        dictionary_terms=("WhisprBar",),
        cfg={"flow_rewrite_provider": "openai_compatible", "flow_rewrite_timeout_seconds": 1},
        provider=EchoProvider(),
    )

    assert result == RewriteResult(text="rewritten: hello", status="applied")


@pytest.mark.unit
def test_prompt_contains_context_profile_command_and_terms():
    prompt = build_rewrite_prompt(
        language="de",
        context=AppContext("x11", app_class="thunderbird", window_title="Inbox"),
        profile=FlowProfile("email", "Email", style="professional", rewrite_mode="professional"),
        command="professional",
        dictionary_terms=("WhisprBar",),
    )

    assert "Language: de" in prompt
    assert "Profile: email" in prompt
    assert "Style: professional" in prompt
    assert "Command: professional" in prompt
    assert "thunderbird" in prompt
    assert "WhisprBar" in prompt


@pytest.mark.unit
def test_prompt_contains_specific_instruction_for_correcting_english():
    prompt = build_rewrite_prompt(
        language="en",
        context=AppContext("x11", app_class="codex", window_title="Codex"),
        profile=FlowProfile("editor", "Editor", style="literal", rewrite_mode="correct_english"),
        command="correct_english",
        dictionary_terms=(),
    )

    assert "Correct English spelling, grammar, punctuation, and wording" in prompt
    assert "Preserve the original meaning" in prompt


@pytest.mark.unit
def test_prompt_contains_humanizer_instruction_without_full_skill_dump():
    prompt = build_rewrite_prompt(
        language="de",
        context=AppContext("x11", app_class="telegramdesktop", window_title="Chat"),
        profile=FlowProfile("chat", "Chat", style="casual", rewrite_mode="humanize"),
        command="humanize",
        dictionary_terms=("WhisprBar",),
    )

    assert "Remove AI-sounding patterns" in prompt
    assert "Preserve the language, meaning, facts, names, and technical terms" in prompt
    assert "Do not start with Here is, Here's, Of course, or Certainly" in prompt
    assert "Use straight quotes and apostrophes" in prompt
    assert "Forbidden output words and phrases" in prompt
    assert "highlight, highlights, underscore, underscores, crucial, pivotal, important, key, comprehensive overview" in prompt
    assert "Do not include a draft, audit, bullets, or explanation" in prompt
    assert "29 patterns listed below" not in prompt


@pytest.mark.unit
def test_openai_provider_without_key_or_model_is_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WHISPRBAR_FLOW_REWRITE_API_KEY", raising=False)

    provider = OpenAICompatibleRewriteProvider()

    with pytest.raises(ValueError, match="not configured"):
        provider.rewrite("hello", "prompt", {"flow_rewrite_model": ""})


@pytest.mark.unit
def test_openai_provider_reads_key_from_whisprbar_env_file(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WHISPRBAR_FLOW_REWRITE_API_KEY", raising=False)
    monkeypatch.setattr(
        "whisprbar.flow.rewrite.load_env_file_values",
        lambda: {"OPENAI_API_KEY": "env-file-key"},
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeURLResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleRewriteProvider()
    result = provider.rewrite(
        "bad english",
        "prompt",
        {"flow_rewrite_model": "gpt-test", "flow_rewrite_timeout_seconds": 3},
    )

    assert result == "Corrected text."
    assert captured["authorization"] == "Bearer env-file-key"
    assert captured["timeout"] == 3
