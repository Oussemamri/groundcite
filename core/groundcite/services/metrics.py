"""Retrieval metrics — recall@k, MRR (spec §8). Pure arithmetic, zero I/O.

Hand-rolled on purpose: spec §8 says "hand-roll recall@k, MRR, citation_precision
and abstention checks (they're ~15 lines each and we need per-case debug detail)".
Ragas is imported ONLY for judge metrics (faithfulness), which is Week 3.

THE MATCHING RULE (the decision that most affects every number below):
a golden case names a clause NUMBER — ``"25.1309"`` — while a retrieved chunk
carries a full clause_path — ``"14 CFR Part 25 §25.1309(b)"``. A chunk counts as
retrieving its expected clause when its clause id is that clause **or a
sub-paragraph of it**:

    expected 25.1309  ← matched by  25.1309, 25.1309(b), 25.1309(b)(2)
    expected 25.1309  ← NOT matched by  25.130, 25.13099, 25.1709

Sub-paragraphs count because §25.1309(b) IS the text of clause 25.1309 — the
clause-aware chunker (spec §6) splits a section into its paragraphs, so demanding
an exact clause_path match would score the pipeline as failing precisely when it
returned the right paragraph. Prefix bleed is impossible: the match requires
either exact equality or a literal ``(`` after the expected id.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def clause_id_of(clause_path: str) -> str:
    """Clause id from a clause_path: '14 CFR Part 25 §25.1309(b)' -> '25.1309(b)'."""
    return clause_path.rsplit("§", 1)[-1].strip()


def matches(retrieved_clause_path: str, expected_clause: str) -> bool:
    """True when a retrieved chunk covers ``expected_clause`` (see module docstring)."""
    retrieved = clause_id_of(retrieved_clause_path)
    expected = clause_id_of(expected_clause)
    return retrieved == expected or retrieved.startswith(f"{expected}(")


def recall_at_k(
    retrieved_clause_paths: Sequence[str],
    expected_clauses: Iterable[str],
    k: int,
) -> float:
    """Fraction of the case's expected clauses found in the top-``k`` (spec §8).

    1.0 when every expected clause is present; 0.0 when none is. A case with no
    expected clauses (a must-abstain case) is not scorable here and returns 0.0 —
    callers exclude those from the mean (abstention correctness is Gate A, Week 3).
    """
    expected = list(expected_clauses)
    if not expected:
        return 0.0
    top = retrieved_clause_paths[:k]
    found = sum(1 for clause in expected if any(matches(path, clause) for path in top))
    return found / len(expected)


def reciprocal_rank(
    retrieved_clause_paths: Sequence[str],
    expected_clauses: Iterable[str],
) -> float:
    """1/rank of the FIRST retrieved chunk covering any expected clause; 0.0 if none.

    Averaged across cases by the caller, this is MRR (spec §8).
    """
    expected = list(expected_clauses)
    if not expected:
        return 0.0
    for rank, path in enumerate(retrieved_clause_paths, start=1):
        if any(matches(path, clause) for clause in expected):
            return 1.0 / rank
    return 0.0


def first_hit_rank(
    retrieved_clause_paths: Sequence[str],
    expected_clauses: Iterable[str],
) -> int | None:
    """1-based rank of the first correct chunk, or None — per-case debug detail
    (spec §8: "we need per-case debug detail")."""
    expected = list(expected_clauses)
    if not expected:
        return None
    for rank, path in enumerate(retrieved_clause_paths, start=1):
        if any(matches(path, clause) for clause in expected):
            return rank
    return None


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
