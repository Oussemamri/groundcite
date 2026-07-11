"""Configuration — the single source of environment (spec §11, §17 rule 9).

All settings (including secrets and model choices) come from ``.env`` via
pydantic-settings. Only ``container`` / ``cli`` / ``apps`` read this; the pure
layers (domain, ports, services, adapters) receive values by injection, never by
importing config. Every variable here mirrors ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

EmbeddingProviderName = Literal["bge_m3", "openai"]
LLMProviderName = Literal["groq", "openai", "ollama"]


class Settings(BaseSettings):
    """Environment-backed configuration (spec §11)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- storage ---
    database_url: str = "postgresql+psycopg://groundcite:groundcite@localhost:5433/groundcite"

    # --- providers (swappable via ports, spec §11) ---
    embedding_provider: EmbeddingProviderName = "bge_m3"
    llm_provider: LLMProviderName = "groq"
    reranker_enabled: bool = True
    # Local bge-m3 model name (spec §11 default; spec §17 rule 9: never hardcode
    # model names outside config defaults). Used by the bge_m3_embed and
    # bge_m3_tokencount adapters, wired in container.py.
    embedding_model: str = "BAAI/bge-m3"
    # Skip real embeddings for dry runs (spec task 2e). When true the container
    # wires a zero-vector FakeEmbedder so chunks.embedding (NOT NULL) still has a
    # 1024-d vector; retrieval is meaningless but the ingest path is exercised.
    skip_embeddings: bool = False

    # --- provider credentials / endpoints ---
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- retrieval tunables (defaults from spec §7; tune with evals) ---
    tau_retrieval: float = 0.35
    rrf_k: int = 60
    candidates_dense: int = 30
    candidates_lexical: int = 30
    fused_k: int = 20
    context_k: int = 6

    # --- ingestion tunables (spec §6 step 3) ---
    # A leaf clause with no children and token_count < MIN_LEAF_TOKENS merges up
    # into its parent's chunk (spec §6.1 #5). Configurable — standards vary.
    min_leaf_tokens: int = 64


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings (spec §11). Cached; call once per process."""
    return Settings()
