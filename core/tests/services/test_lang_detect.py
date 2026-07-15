"""Unit tests for the DE/EN stopword-ratio heuristic (spec §7 step 0).

Table-tested against the committed golden suites via the read-only eval loader
(rule 13: this test READS evals/suites/*.jsonl; it never writes them).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from groundcite.adapters.evalsuite.jsonl_suite import load_suite
from groundcite.domain.entities import EvalCase
from groundcite.services.lang_detect import detect_language

_SUITES_DIR = Path(__file__).resolve().parents[3] / "evals" / "suites"


def _questions(suite: str) -> Sequence[EvalCase]:
    return load_suite(suite, _SUITES_DIR)


def test_classifies_all_german_suite_questions_as_de() -> None:
    cases = _questions("german")
    assert len(cases) >= 10, "german suite must have ≥10 cases for the table test"
    wrong = [c.question for c in cases if detect_language(c.question) != "de"]
    assert wrong == [], f"misclassified as non-DE: {wrong}"


def test_classifies_core_suite_questions_as_en() -> None:
    cases = _questions("core")
    sample = cases[:10]  # 10 English cases for the Phase-3 verify line
    assert len(sample) == 10
    wrong = [c.question for c in sample if detect_language(c.question) != "en"]
    assert wrong == [], f"misclassified as non-EN: {wrong}"


def test_negative_suite_questions_are_english() -> None:
    cases = _questions("negative")
    wrong = [c.question for c in cases if detect_language(c.question) != "en"]
    assert wrong == [], f"negative suite should be English: {wrong}"


def test_empty_and_tie_break_to_english() -> None:
    assert detect_language("") == "en"
    assert detect_language("§25.1309(b)") == "en", "no function words ⇒ English (corpus lang)"


def test_german_question_with_english_clause_id() -> None:
    q = "Welchen Sicherheitsfaktor schreibt §25.303 vor und auf welche Lasten wird er angewendet?"
    assert detect_language(q) == "de"
