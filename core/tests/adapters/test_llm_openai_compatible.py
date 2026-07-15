"""Unit tests for the OpenAI-compatible LLM adapter + factories (AD-1).

Fake ports only — no network, no model. The adapter is exercised with a scripted
fake OpenAI client (monkeypatched in place of the guarded ``_OpenAI`` import
sentinel) so stream order, usage capture, and the install-missing RuntimeError
are pinned without touching a real provider. A live Groq smoke is run separately
by the owner and pasted in the commit message (AD-1/Phase 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from groundcite.adapters.llm import openai_compatible as oc
from groundcite.adapters.llm.groq_llm import make_groq_llm
from groundcite.adapters.llm.ollama_llm import make_ollama_llm
from groundcite.adapters.llm.openai_llm import make_openai_llm
from groundcite.config import Settings

# --- scripted fake OpenAI SDK -------------------------------------------------


@dataclass
class _Delta:
    content: str | None = None


@dataclass
class _Choice:
    delta: _Delta | None = None


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class _Chunk:
    choices: list[_Choice] | None = None
    usage: _Usage | None = None


class _FakeCreate:
    """Returns a scripted list of chunks; the final chunk carries ``usage``."""

    def __init__(self, chunks: list[_Chunk]) -> None:
        self._chunks = chunks

    def create(self, **_kwargs: Any) -> list[_Chunk]:
        return list(self._chunks)


class _FakeOpenAI:
    def __init__(self, chunks: list[_Chunk]) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCreate(chunks)})()


def _chunks_with_tokens(tokens: list[str], usage: _Usage) -> list[_Chunk]:
    out = [_Chunk(choices=[_Choice(delta=_Delta(content=t))]) for t in tokens]
    out.append(_Chunk(choices=None, usage=usage))  # usage-only final chunk
    return out


def _consume(gen: Any) -> tuple[str, Any]:
    text = ""
    usage = None
    while True:
        try:
            text += next(gen)
        except StopIteration as stop:
            usage = stop.value
            break
    return text, usage


# --- factory binding (provider selection by config) --------------------------


def test_groq_factory_binds_groq_base_url_and_model() -> None:
    llm = make_groq_llm(
        api_key="k",
        model="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
    )
    assert llm.model_name == "llama-3.3-70b-versatile"
    assert llm.base_url == "https://api.groq.com/openai/v1"


def test_openai_factory_leaves_sdk_default_base_url() -> None:
    llm = make_openai_llm(api_key="k", model="gpt-4o-mini")
    assert llm.model_name == "gpt-4o-mini"
    assert llm.base_url is None, "None ⇒ the SDK's api.openai.com default"


def test_ollama_factory_appends_v1_and_placeholder_key() -> None:
    llm = make_ollama_llm(base_url="http://localhost:11434", model="llama3.1")
    assert llm.model_name == "llama3.1"
    assert llm.base_url == "http://localhost:11434/v1"


def test_container_builds_groq_adapter_by_default() -> None:
    """Provider selection by config: LLM_PROVIDER=groq wires the groq factory."""
    from groundcite.container import _build_llm

    s = Settings(groq_api_key="k", groq_model="llama-3.3-70b-versatile")
    llm = _build_llm(s)
    assert isinstance(llm, oc.OpenAICompatibleLLM)
    assert llm.model_name == "llama-3.3-70b-versatile"
    assert llm.base_url == "https://api.groq.com/openai/v1"


def test_container_builds_ollama_adapter_when_configured() -> None:
    from groundcite.container import _build_llm

    s = Settings(
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.1",
    )
    llm = _build_llm(s)
    assert isinstance(llm, oc.OpenAICompatibleLLM)
    assert llm.base_url == "http://localhost:11434/v1"


# --- stream order + usage capture (scripted fake client) ---------------------


def test_stream_yields_tokens_in_order_and_returns_usage(monkeypatch) -> None:
    chunks = _chunks_with_tokens(
        ["Hel", "lo", " world"], _Usage(prompt_tokens=42, completion_tokens=3)
    )
    llm = oc.OpenAICompatibleLLM(api_key="k", model="m", base_url="https://x/v1")
    monkeypatch.setattr(oc, "_OpenAI", lambda **kw: _FakeOpenAI(chunks))

    gen = llm.stream("sys", "What does §25.1309(b) require?")
    text, usage = _consume(gen)

    assert text == "Hello world", "tokens yielded in order, concatenated"
    assert usage.prompt_tokens == 42
    assert usage.completion_tokens == 3


def test_stream_captures_usage_from_a_maximal_final_chunk(monkeypatch) -> None:
    # empty content + usage-only final chunk should still yield no tokens but return usage
    chunks = [_Chunk(choices=None, usage=_Usage(prompt_tokens=7, completion_tokens=9))]
    llm = oc.OpenAICompatibleLLM(api_key="k", model="m", base_url="https://x/v1")
    monkeypatch.setattr(oc, "_OpenAI", lambda **kw: _FakeOpenAI(chunks))

    gen = llm.stream("sys", "u")
    text, usage = _consume(gen)

    assert text == ""
    assert usage.prompt_tokens == 7
    assert usage.completion_tokens == 9


def test_stream_passes_model_messages_stream_options_and_temperature(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _RecordingCreate:
        def create(self, **kwargs: Any) -> list[_Chunk]:
            captured.update(kwargs)
            return [_Chunk(choices=None, usage=_Usage())]

    class _RecordingChat:
        def __init__(self) -> None:
            self.completions = _RecordingCreate()

    class _RecordingOpenAI:
        def __init__(self, **_kw: Any) -> None:
            self.chat = _RecordingChat()

    monkeypatch.setattr(oc, "_OpenAI", _RecordingOpenAI)
    llm = oc.OpenAICompatibleLLM(api_key="k", model="groq-xyz", base_url="https://x/v1")
    _consume(llm.stream("SYS", "USR"))

    assert captured["model"] == "groq-xyz"
    assert captured["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]
    assert captured["stream"] is True
    assert captured["stream_options"] == {"include_usage": True}
    assert captured["temperature"] == 0.0


# --- install-missing path ----------------------------------------------------


def test_stream_raises_runtime_error_with_install_hint_when_extra_missing(monkeypatch) -> None:
    monkeypatch.setattr(oc, "_OpenAI", None)
    llm = oc.OpenAICompatibleLLM(api_key="k", model="m", base_url="https://x/v1")
    with pytest.raises(RuntimeError, match="llm extra"):
        gen = llm.stream("sys", "u")
        next(gen)  # first access opens the client and raises


def test_client_is_lazy_no_sdk_call_in_constructor(monkeypatch) -> None:
    """Construction must not touch the SDK (CI builds services with no extra)."""
    called: list[Any] = []

    def _boom(**_kw: Any) -> Any:
        called.append(1)
        raise AssertionError("SDK client opened at construction time")

    monkeypatch.setattr(oc, "_OpenAI", _boom)
    oc.OpenAICompatibleLLM(api_key="k", model="m", base_url="https://x/v1")
    assert called == []
