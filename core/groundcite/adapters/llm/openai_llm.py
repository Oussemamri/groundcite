"""OpenAI factory for ``OpenAICompatibleLLM`` (spec §11 alternate; AD-1).

OpenAI is the SDK's own default base URL, so the factory passes ``base_url=None``.
Written per AD-1 to keep the LLM port swappable; UNEXERCISED this week (only
Groq is configured).
"""

from __future__ import annotations

from groundcite.adapters.llm.openai_compatible import OpenAICompatibleLLM, make_openai_llm

__all__ = ["OpenAICompatibleLLM", "make_openai_llm"]
