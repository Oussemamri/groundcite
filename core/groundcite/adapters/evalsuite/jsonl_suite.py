"""Loads golden eval Cases from the committed JSONL suites (spec §8, §4.1).

``evals/suites/*.jsonl`` is the human-owned source of truth for the golden set
(prep task P2; CLAUDE.md rule 13 — this adapter READS it and never writes it).
The `eval_cases` table (spec §5) is the API's query surface and is seeded from
these files; the CLI eval runner reads the files directly, so a run needs no DB
seeding step and the committed set is always exactly what was scored.

Lines beginning with ``##`` are the suites' own draft/section annotations, not
cases — they are skipped, as are blank lines.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from groundcite.domain.entities import EvalCase


class SuiteNotFoundError(FileNotFoundError):
    """Raised when a suite name has no committed JSONL file."""


def load_suite(suite: str, suites_dir: Path) -> list[EvalCase]:
    """Parse ``<suites_dir>/<suite>.jsonl`` into EvalCases (spec §8).

    Case ids are derived deterministically from (suite, question) so the same
    committed case keeps the same id across runs, making eval_results comparable
    run-over-run without storing ids in the JSONL.
    """
    path = suites_dir / f"{suite}.jsonl"
    if not path.is_file():
        raise SuiteNotFoundError(f"no such suite: {path}")

    cases: list[EvalCase] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("##"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON — {exc}") from exc
        question = record["question"]
        cases.append(
            EvalCase(
                id=uuid5(NAMESPACE_URL, f"groundcite/eval/{suite}/{question}"),
                suite=record.get("suite", suite),
                question=question,
                expected_clauses=tuple(record.get("expected_clauses", ())),
                expected_facts=tuple(record.get("expected_facts", ())),
                must_abstain=bool(record.get("must_abstain", False)),
                language=record.get("language", "en"),
            )
        )
    return cases


def make_jsonl_suite_loader(suites_dir: Path) -> Callable[[str], list[EvalCase]]:
    """Container factory (spec §4 wiring seam): binds the suites directory."""

    def _load(suite: str) -> list[EvalCase]:
        return load_suite(suite, suites_dir)

    return _load
