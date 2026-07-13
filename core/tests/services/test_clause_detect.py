"""Unit tests for clause-ID detection (spec §7 step 0). Pure — no fakes needed."""

from __future__ import annotations

import pytest

from groundcite.services.clause_detect import detect_clause_ids


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # Marked by §
        ("What does §25.1309(b) require?", ["25.1309(b)"]),
        ("What does § 25.1309 require?", ["25.1309"]),
        ("Explain §§ 25.1309 and 25.811.", ["25.1309"]),
        # Marked by a cue word
        ("What does section 25.1309 say?", ["25.1309"]),
        ("Requirements in part 25.807 for exits", ["25.807"]),
        ("clause 5.4.2.1 of the standard", ["5.4.2.1"]),
        # Self-identifying via CFR paragraph suffixes (no § needed)
        ("Tell me about 25.1309(b)(2)(i).", ["25.1309(b)(2)(i)"]),
        # ECSS-style codes
        ("What does ECSS-E-ST-40C require?", ["ECSS-E-ST-40C"]),
        # Semantic questions name no clause — the fast path must not fire
        ("What failure probability is acceptable for catastrophic conditions?", []),
        ("How are emergency exits marked?", []),
        # Bare decimals in prose are NOT clauses (the conservatism that matters)
        ("Can it withstand 1.5 g of load?", []),
        ("What changed in the 1.2 revision?", []),
    ],
)
def test_detects_clause_ids(question: str, expected: list[str]) -> None:
    assert detect_clause_ids(question) == expected


def test_dedupes_and_preserves_first_seen_order() -> None:
    q = "Compare §25.1309 with §25.811, and then §25.1309 again."
    assert detect_clause_ids(q) == ["25.1309", "25.811"]


def test_trailing_punctuation_is_stripped() -> None:
    assert detect_clause_ids("Does §25.1309. apply?") == ["25.1309"]
