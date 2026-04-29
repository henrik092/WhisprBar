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
def test_openai_provider_without_key_or_model_is_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WHISPRBAR_FLOW_REWRITE_API_KEY", raising=False)

    provider = OpenAICompatibleRewriteProvider()

    with pytest.raises(ValueError, match="not configured"):
        provider.rewrite("hello", "prompt", {"flow_rewrite_model": ""})
