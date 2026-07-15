"""Unit tests for the DE/EN stopword-ratio heuristic (spec §7 step 0).

Primary coverage is a small HARDCODED table (deterministic, always available):
``detect_language`` is a pure function and its correctness must not depend on
the golden set's size, which is outside code's control (evals/suites/ is
human-owned, rule 13, and not yet frozen — the committed suites may legitimately
hold zero cases at any point, as they do right now).

The golden-set checks below are a BONUS sanity pass, not the primary contract:
they SKIP (not fail) when a suite has too few committed cases, mirroring the
established "skip when the external precondition isn't met" pattern used for
the DB-dependent integration tests (tests/integration/conftest.py).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from groundcite.adapters.evalsuite.jsonl_suite import load_suite
from groundcite.domain.entities import EvalCase
from groundcite.services.lang_detect import detect_language

_SUITES_DIR = Path(__file__).resolve().parents[3] / "evals" / "suites"

# A small, permanent, deterministic table — real aerospace-flavoured questions
# in both languages, independent of the (unfrozen, human-owned) golden set.
_GERMAN_QUESTIONS = [
    "Welche Ausfallwahrscheinlichkeit ist für Fehlerzustände akzeptabel, die einen "
    "sicheren Weiterflug verhindern?",
    "Welchen Sicherheitsfaktor schreibt §25.303 vor und auf welche Lasten wird er angewendet?",
    "Wie schnell muss nachgewiesen werden, dass ein voll besetztes Flugzeug im "
    "Notfall evakuiert werden kann?",
    "Welche Kabinendruckhöhe darf im normalen Betrieb nicht überschritten werden?",
    "Was verlangen die Vorschriften zur Ermüdungs- und Schadenstoleranzbewertung?",
    "Welche Farben sind für Warn- und Vorsichtshinweise an die Flugbesatzung vorgesehen?",
    "Welche Lasten muss die Struktur ohne bleibende Verformung tragen?",
    "Wie werden die Start- und Sicherheitsgeschwindigkeiten definiert?",
    "Was unterscheidet die verschiedenen Klassen von Frachträumen?",
    "Welche Überziehwarnung müssen die Piloten vor dem Strömungsabriss erhalten?",
]

_ENGLISH_QUESTIONS = [
    "What does §25.1309(b) require for catastrophic failure conditions?",
    "What factor of safety does §25.303 prescribe, and to what loads does it apply?",
    "How quickly must it be demonstrated that everyone can get out of a fully "
    "loaded airplane in an emergency?",
    "What cabin pressure altitude limit applies at maximum operating altitude?",
    "What do the fatigue and damage-tolerance evaluation rules require?",
    "What colors are prescribed for flight-crew alerting and caution indications?",
    "What loads must the structure support without permanent deformation?",
    "How are the takeoff decision and safety speeds defined?",
    "What distinguishes the different classes of cargo compartments?",
    "What stall warning must pilots receive before the wing loses lift?",
]


def test_hardcoded_german_questions_classify_as_de() -> None:
    wrong = [q for q in _GERMAN_QUESTIONS if detect_language(q) != "de"]
    assert wrong == [], f"misclassified as non-DE: {wrong}"


def test_hardcoded_english_questions_classify_as_en() -> None:
    wrong = [q for q in _ENGLISH_QUESTIONS if detect_language(q) != "en"]
    assert wrong == [], f"misclassified as non-EN: {wrong}"


def test_empty_and_tie_break_to_english() -> None:
    assert detect_language("") == "en"
    assert detect_language("§25.1309(b)") == "en", "no function words ⇒ English (corpus lang)"


def test_german_question_with_english_clause_id() -> None:
    q = "Welchen Sicherheitsfaktor schreibt §25.303 vor und auf welche Lasten wird er angewendet?"
    assert detect_language(q) == "de"


# --- golden-set bonus checks (skip when the committed suite is too thin) ------


def _questions(suite: str) -> Sequence[EvalCase]:
    return load_suite(suite, _SUITES_DIR)


def test_classifies_all_german_suite_questions_as_de() -> None:
    cases = _questions("german")
    if len(cases) < 10:
        pytest.skip(
            f"german suite has {len(cases)} committed cases (<10) — "
            "evals/suites/ is human-owned and not yet frozen (rule 13)"
        )
    wrong = [c.question for c in cases if detect_language(c.question) != "de"]
    assert wrong == [], f"misclassified as non-DE: {wrong}"


def test_classifies_core_suite_questions_as_en() -> None:
    cases = _questions("core")
    if len(cases) < 10:
        pytest.skip(
            f"core suite has {len(cases)} committed cases (<10) — "
            "evals/suites/ is human-owned and not yet frozen (rule 13)"
        )
    sample = cases[:10]
    wrong = [c.question for c in sample if detect_language(c.question) != "en"]
    assert wrong == [], f"misclassified as non-EN: {wrong}"


def test_negative_suite_questions_are_english() -> None:
    cases = _questions("negative")
    if not cases:
        pytest.skip("negative suite has 0 committed cases (rule 13, not yet frozen)")
    wrong = [c.question for c in cases if detect_language(c.question) != "en"]
    assert wrong == [], f"negative suite should be English: {wrong}"
