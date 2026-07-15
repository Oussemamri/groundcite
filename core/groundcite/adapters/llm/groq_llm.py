"""Groq factory for ``OpenAICompatibleLLM`` (spec §11 default; AD-1).

Groq is OpenAI-compatible, so the same adapter serves it — this module only
binds Groq's base URL, the configured ``GROQ_API_KEY``, and ``GROQ_MODEL``.
"""

from __future__ import annotations

from groundcite.adapters.llm.openai_compatible import OpenAICompatibleLLM, make_groq_llm

__all__ = ["OpenAICompatibleLLM", "make_groq_llm"]
