# GroundCite — rules for AI-assisted development

1. Read GROUNDCITE_PROJECT_SPEC.md before any task. If a request conflicts
   with the spec, say so and stop.
2. Dependency rule is law: domain ← ports ← services / adapters ← apps.
   Core never imports adapters. import-linter enforces; don't fight it.
3. Every service-layer change ships with unit tests using fake ports
   (no network, no DB). Integration tests may use the compose Postgres.
4. Any change to chunking, retrieval, fusion, thresholds, or prompts MUST
   include an eval run: `groundcite eval run --suite core` — paste the
   before/after table in the PR/commit message.
5. mypy --strict on core; no `Any` in ports; pydantic v2 frozen models in domain.
6. TS: strict, no `any`, TanStack Query for all server state, SSE types
   mirror core/services enums exactly.
7. Small diffs. One feature per commit. Conventional commits (feat:, fix:,
   eval:, docs:).
8. Domain language from spec §2.1 everywhere. No synonyms.
9. Secrets only via config.py/pydantic-settings. Never hardcode model names
   outside config defaults.
10. When unsure between clever and boring: boring.
11. Build-vs-buy boundary (spec §11.1) is law: NEVER add LangChain, LlamaIndex,
    Haystack, or any RAG framework. Allowed libs: docling, flagembedding,
    rerankers, ragas (judge metrics only), sse-starlette, pgvector. Anything
    new goes through a spec §11 table update first.
12. Pin every dependency version. Judge model name lives in config and is
    snapshotted into every eval run.
13. Never create or modify files under evals/suites/ unless explicitly
    instructed in the current task. That directory is human-owned (P2).
