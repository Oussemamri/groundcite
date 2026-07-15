"""Ollama factory for ``OpenAICompatibleLLM`` (spec §11 alternate; AD-1).

Ollama speaks the OpenAI Chat Completions API at ``<base_url>/v1`` and ignores
the API key, so the factory passes a placeholder key and appends ``/v1``. Written
per AD-1 to keep the LLM port swappable; UNEXERCISED this week (only Groq is
configured).
"""

from __future__ import annotations

from groundcite.adapters.llm.openai_compatible import OpenAICompatibleLLM, make_ollama_llm

__all__ = ["OpenAICompatibleLLM", "make_ollama_llm"]
