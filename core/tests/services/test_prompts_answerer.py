"""Unit tests for the answerer prompt renderer (spec §7; AD-4). Fake ports only."""

from __future__ import annotations

from uuid import UUID, uuid4

from groundcite.domain.results import RetrievedChunk
from groundcite.services.prompts.answerer import (
    chunk_id_set,
    render_context,
    render_repair,
    render_user,
)


def _rc(clause: str, cid: UUID | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid or uuid4(),
        clause_path=f"14 CFR Part 25 §{clause}",
        content=f"body of {clause}",
        score=0.9,
    )


def test_render_context_tags_each_chunk_id_exactly_once() -> None:
    a, b, c = _rc("25.1"), _rc("25.2"), _rc("25.3")
    out = render_context([a, b, c])
    assert out.count(f'id="{a.chunk_id}"') == 1
    assert out.count(f'id="{b.chunk_id}"') == 1
    assert out.count(f'id="{c.chunk_id}"') == 1
    assert "<chunk " in out and "</chunk>" in out
    assert "14 CFR Part 25 §25.2" in out, "clause attribute present"


def test_chunk_id_set_is_the_valid_citation_set() -> None:
    a, b = _rc("25.1"), _rc("25.2")
    ids = chunk_id_set([a, b])
    assert ids == frozenset({str(a.chunk_id), str(b.chunk_id)})


def test_render_user_includes_context_question_and_language_hint() -> None:
    a = _rc("25.1309(b)")
    out = render_user("What does §25.1309(b) require?", [a], language="de")
    assert "Question: What does §25.1309(b) require?" in out
    assert "Answer in German." in out
    assert f'id="{a.chunk_id}"' in out


def test_render_user_defaults_to_english_hint() -> None:
    out = render_user("q", [_rc("25.1")], language="fr")
    assert "Answer in English." in out, "unknown language falls back to English"


def test_render_repair_names_the_critique_and_keeps_context() -> None:
    a = _rc("25.1")
    out = render_repair("q", [a], "en", "citations[0].chunk_id 'zzz' is not in the context.")
    assert "not usable" in out
    assert "citations[0].chunk_id 'zzz' is not in the context." in out
    assert f'id="{a.chunk_id}"' in out, "repair re-provides the context"
    assert "Re-emit ONLY a corrected JSON" in out
