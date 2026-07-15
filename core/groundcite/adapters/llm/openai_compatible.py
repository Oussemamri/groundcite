"""One OpenAI-compatible LLM adapter served to all three generation providers
(spec §7 step 5, §11; AD-1).

Groq (``https://api.groq.com/openai/v1``), OpenAI (SDK default base URL), and
Ollama (``http://localhost:11434/v1``) all speak the OpenAI Chat Completions
API, so a single client — the ``openai`` SDK — covers all three. One adapter +
three thin factories that bind (base_url, api_key, model) is the §11 "Buy"
decision for generation inference; the §7 pipeline, prompts, gates and JSON
contract remain ours (§11.1).

Copies the guarded-import + pyproject mypy-override pattern from
``bge_reranker.py``: the ``openai`` import is module-level guarded so CI (no
``[llm]`` extra) and the unit suite (FakeLLM) never need it; an actual
``stream`` raises ``RuntimeError`` with the install hint when the extra is
absent.

Token usage (AD-1): with ``stream=True, stream_options={"include_usage": True}``
the provider sends an extra final chunk carrying ``usage``; the adapter collects
it and returns it as the generator's ``StopIteration`` value, so the streaming
token loop and the per-call accounting come from one call (feeds
``pipeline_debug`` + ``cost_usd``). ``temperature=0.0`` for reproducible,
grounded answers (evals need determinism — not a config knob, a fixed choice).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from groundcite.domain.results import TokenUsage

# Declared ``Any`` so the guarded ``None`` assignment type-checks in BOTH install
# states: CI (openai missing → ``ignore_missing_imports`` makes it Any) and the
# local dev install (openai ships real ``py.typed`` stubs, so the import binds a
# real ``type[OpenAI]``). Without this annotation mypy narrows the name from the
# try-branch to ``type[OpenAI]`` and the except's ``None`` then fails. Mirrors
# the bge_reranker lazy-import + per-module mypy-override pattern.
_OpenAI: Any
try:  # pragma: no cover - exercised only when the llm extra is installed
    from openai import OpenAI as _OpenAI
except ImportError:  # pragma: no cover
    _OpenAI = None


class OpenAICompatibleLLM:
    """Implements ``LLMProvider`` around the ``openai`` SDK (AD-1).

    The SDK client opens lazily on first ``stream`` (not in ``__init__``) so
    ``container.build_services`` can construct this adapter without the
    ``[llm]`` extra installed or a reachable provider; only an actual generation
    call needs either.
    """

    def __init__(self, *, api_key: str | None, model: str, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        # None ⇒ the SDK's own default base_url (api.openai.com).
        self._base_url = base_url
        self._client: Any = None  # opened on first stream, cached on the instance

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str | None:
        return self._base_url

    def _open(self) -> Any:
        if self._client is None:
            if _OpenAI is None:  # pragma: no cover - guarded by import
                raise RuntimeError(
                    "The `openai` SDK is not installed. Install the llm extra "
                    "(`uv sync --extra llm`), or set LLM_PROVIDER to a stub."
                )
            self._client = _OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def stream(self, system: str, user: str) -> Generator[str, None, TokenUsage]:
        """Yield streamed token strings and RETURN the per-call ``TokenUsage``.

        Caller captures usage via the generator's ``StopIteration.value`` (see
        the ``LLMProvider`` protocol docstring).
        """
        client = self._open()
        stream = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
            stream_options={"include_usage": True},
            temperature=0.0,
        )
        prompt_tokens = 0
        completion_tokens = 0
        for chunk in stream:  # type: ignore[union-attr]
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            if content:
                yield content
        return TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


# --- factories: one per provider, binding (base_url, api_key, model) ---

_DEFAULT_OLLAMA_KEY = "ollama"  # Ollama /v1 ignores the key, but the SDK needs a non-empty str


def make_groq_llm(*, api_key: str | None, model: str, base_url: str) -> OpenAICompatibleLLM:
    """Groq factory (AD-1); base_url is ``https://api.groq.com/openai/v1``."""
    return OpenAICompatibleLLM(api_key=api_key, model=model, base_url=base_url)


def make_openai_llm(*, api_key: str | None, model: str) -> OpenAICompatibleLLM:
    """OpenAI factory (AD-1); base_url None ⇒ the SDK's api.openai.com default."""
    return OpenAICompatibleLLM(api_key=api_key, model=model, base_url=None)


def make_ollama_llm(*, base_url: str, model: str) -> OpenAICompatibleLLM:
    """Ollama factory (AD-1); appends ``/v1`` to the Ollama base URL."""
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return OpenAICompatibleLLM(api_key=_DEFAULT_OLLAMA_KEY, model=model, base_url=url)
