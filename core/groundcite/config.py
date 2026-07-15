"""Configuration — the single source of environment (spec §11, §17 rule 9).

All settings (including secrets and model choices) come from ``.env`` via
pydantic-settings. Only ``container`` / ``cli`` / ``apps`` read this; the pure
layers (domain, ports, services, adapters) receive values by injection, never by
importing config. Every variable here mirrors ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

EmbeddingProviderName = Literal["bge_m3", "openai"]
LLMProviderName = Literal["groq", "openai", "ollama"]

# A model's per-million-token price in USD (spec §12 cost, AD-6). One entry per
# model name → {"prompt": USD/M input, "completion": USD/M output}. Used by the
# container to compute ``asks.cost_usd`` ONLY when the active model has an entry
# here; otherwise cost stays NULL — a number is never faked (AD-6).
ModelPrice = dict[str, float]

# config.py -> groundcite/ -> core/ -> repo root. Derived (not a cwd-relative
# path) so `groundcite eval run` finds the committed suites from any directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


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
    # Cross-encoder reranker model (spec §11 default). Used by the bge_reranker
    # adapter; scores are normalized so they feed TAU_RETRIEVAL directly (§11).
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # Skip real embeddings for dry runs (spec task 2e). When true the container
    # wires a zero-vector FakeEmbedder so chunks.embedding (NOT NULL) still has a
    # 1024-d vector; retrieval is meaningless but the ingest path is exercised.
    skip_embeddings: bool = False

    # --- provider credentials / endpoints ---
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- LLM generation models (AD-1; spec §17 rule 9: model names live ONLY in
    # these config defaults, never in code). One OpenAI-compatible client serves
    # all three providers. The Groq default is the spec §11 guess, still present
    # in the live catalog on 2026-07-15 (17 models); Phase 6 re-evaluates the
    # candidate set (llama-3.3-70b-versatile / openai/gpt-oss-120b /
    # meta-llama/llama-4-scout-17b-16e-instruct) with real citation numbers and
    # may change this default in a measured commit. The openai/ollama factories
    # are written per AD-1 but UNEXERCISED this week — their names are not
    # verified against a live provider now (spec §11 last row).
    groq_model: str = "llama-3.3-70b-versatile"
    openai_model: str = "gpt-4o-mini"
    ollama_model: str = "llama3.1"
    # Groq's OpenAI-compatible base URL (AD-1). OpenAI LLC base URL is the SDK
    # default; Ollama's is ``ollama_base_url`` above + ``/v1``.
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # --- judge (evals only, AD-7) ---
    # Judge metrics are SKIPPED this week (Phase 0 step 2b: only Groq is
    # configured, spec §11 requires judge ≠ answerer). Left None so the eval
    # runner's --judge path is a no-op (judge columns NULL) rather than a
    # broken cross-provider call. Pinned when a second provider arrives.
    judge_provider: LLMProviderName | None = None
    judge_model: str | None = None

    # --- per-call cost (spec §12, AD-6) ---
    # Optional price map; empty → cost_usd is NULL (never faked). Parsed from a
    # JSON env var MODEL_PRICES, e.g.
    # {"llama-3.3-70b-versatile":{"prompt":0.59,"completion":0.79}}
    model_prices: dict[str, ModelPrice] = Field(default_factory=dict)

    # --- retrieval tunables (defaults from spec §7; tune with evals) ---
    # 0.70, not the spec's original 0.35 (AD-3 / Week 3 Phase 6, real baseline
    # on the full 60-case golden set, tau_sweep against every case's recorded
    # top_score): tau=0.35 leaks 3/12 (25%) must-abstain cases through Gate A
    # on raw score alone — spec §1's "wrong citation is worse than no answer"
    # contract cannot depend on the LLM's own insufficient-flag as the only
    # backstop. 0.70 is the first candidate with zero measured leak on that
    # baseline; cost is grounded-wrongly-abstained rising 4.2% -> 10.4%
    # (5/48), a real, stated trade — see docs/WEEK3_RESULTS.md.
    tau_retrieval: float = 0.70
    rrf_k: int = 60
    candidates_dense: int = 30
    candidates_lexical: int = 30
    fused_k: int = 20
    context_k: int = 6

    # --- evals (spec §8) ---
    # The human-owned golden set (prep task P2; CLAUDE.md rule 13 — read, never
    # written by code) and where `eval run` writes its report (spec §8).
    eval_suites_dir: Path = _REPO_ROOT / "evals" / "suites"
    eval_reports_dir: Path = _REPO_ROOT / "evals" / "reports"

    # --- ingestion tunables (spec §6 step 3) ---
    # A leaf clause with no children and token_count < MIN_LEAF_TOKENS merges up
    # into its parent's chunk (spec §6.1 #5). Configurable — standards vary.
    min_leaf_tokens: int = 64


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings (spec §11). Cached; call once per process."""
    return Settings()
