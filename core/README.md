# groundcite (core)

The hexagonal core package for [GroundCite](../README.md): `domain`, `ports`,
`services`, `adapters`, plus `config`, `container`, and the `groundcite` CLI.

See [`../GROUNDCITE_PROJECT_SPEC.md`](../GROUNDCITE_PROJECT_SPEC.md) §4 for the
layering and dependency rule (enforced here by import-linter).

## Develop

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy groundcite
uv run lint-imports
uv run pytest
```

## Migrations

```bash
# with the compose Postgres up (docker compose up -d db from repo root)
uv run alembic upgrade head
```
