# `core/` — domain, ports, services, adapters (hexagonal)

Supplements the root [`CLAUDE.md`](../CLAUDE.md) and
[`GROUNDCITE_PROJECT_SPEC.md`](../GROUNDCITE_PROJECT_SPEC.md) — read those first;
this file only adds what's specific to working inside `core/`.

## Gate commands (run before every commit that touches this directory)

```bash
cd core
uv run ruff check .
uv run ruff format --check .
uv run lint-imports          # import-linter: 5 contracts must stay "kept"
uv run mypy --strict groundcite
uv run pytest -q
```

venv: `core/.venv/Scripts/python.exe` (Windows). `uv sync` creates/updates it.

## The mypy CI-parity ritual (do this too, not just the command above)

`mypy --strict` must pass in **both** install states: with the optional
extras present (`embed`/`rerank`/`llm`) AND without them — the ports must
type-check with no `Any` regardless of which adapters are installed. CI only
installs the base package, so a green local run with extras installed can
still be broken in CI. Verify both, every time core changes:

```bash
cd core
# 1. extras present (normal state)
uv run mypy --strict --no-incremental groundcite

# 2. hide the extras, clear the cache, re-check, then restore
SITE_PKGS=".venv/Lib/site-packages"
HIDE_DIR="/tmp/hidden-extras"; mkdir -p "$HIDE_DIR"
for pkg in openai FlagEmbedding rerankers; do
  mv "$SITE_PKGS/$pkg" "$HIDE_DIR/" 2>/dev/null
  mv "$SITE_PKGS"/${pkg,,}-*.dist-info "$HIDE_DIR/" 2>/dev/null
done
rm -rf .mypy_cache
uv run mypy --strict --no-incremental groundcite
# then move everything in $HIDE_DIR back into $SITE_PKGS
```

## Rules specific to this directory

- Dependency rule (root rule 2) is enforced HERE by `lint-imports`: domain
  imports nothing internal; ports import domain only; services import
  domain+ports (never adapters); adapters import domain+ports (never
  services). Don't fight a broken contract by loosening it — fix the import.
- Domain models are frozen pydantic v2 (`_Frozen` base in `domain/entities.py`
  / `domain/results.py`), `extra="forbid"`. New domain types follow that
  pattern, not a dataclass or a loose dict.
- No `Any` in ports (`ports/protocols.py`) — root rule 5. If a port method
  needs a type that doesn't exist yet, add a frozen domain type for it rather
  than reaching for `Any`, `object`, or a raw `dict`.
- New Repository reads go in lockstep, one commit: port protocol → `pg_repo`
  adapter → `FakeRepository` (`tests/fakes.py`) → unit test using the fake →
  live-DB integration test (auto-skips when Postgres is unreachable — copy an
  existing `tests/integration/` module's skip-guard pattern, don't invent one).
- `core` is logging-free (structlog lives in `apps/api` only, spec §12) and
  secret-free (no provider keys read outside `config.py`/pydantic-settings,
  root rule 9).
- Live Postgres for integration tests / manual checks: `docker compose up -d
  db` (host port 5433); `docker exec groundcite-db psql -U groundcite -d
  groundcite` to query directly. Never run destructive SQL against it without
  checking what's there first — it holds the real, currently-ingested
  far-25 corpus and every eval run this project has recorded.
