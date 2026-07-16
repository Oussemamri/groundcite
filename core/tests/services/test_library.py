"""Unit tests for LibraryService (spec §9, §10; Week 4 AD-4; §17 rule 3: fakes).

Covers the read side behind ``GET /documents`` / ``GET /documents/{slug}`` and
the reader's clause tree: list_documents, get_document (+ section tree +
chunks). Also covers the new Repository reads that the API replay/evals routes
need (ask citations ordered by rank, eval runs newest-first). All via
FakeRepository — no network, no DB, no models.
"""

from __future__ import annotations

from uuid import uuid4

from groundcite.domain.entities import Ask, Chunk, Document, Section
from groundcite.domain.results import AskStatus, Citation, EvalRun
from groundcite.services.library import LibraryService
from tests.fakes import FakeRepository


def _doc(slug: str = "far-25") -> Document:
    return Document(
        id=uuid4(),
        slug=slug,
        standard_code="14 CFR Part 25",
        title="Airworthiness standards",
        organization="FAA",
        license_note="US public domain",
    )


def _section(doc: Document, clause_id: str, level: int, ordinal: int, parent_id=None) -> Section:  # type: ignore[no-untyped-def]
    return Section(
        id=uuid4(),
        document_id=doc.id,
        parent_id=parent_id,
        clause_id=clause_id,
        title=None,
        level=level,
        ordinal=ordinal,
    )


def _chunk(doc: Document, section: Section, clause_path: str, token_count: int) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=doc.id,
        section_id=section.id,
        clause_path=clause_path,
        content=f"[{doc.standard_code} {clause_path}] body",
        token_count=token_count,
    )


def test_list_documents_empty_library_returns_empty() -> None:
    lib = LibraryService(repository=FakeRepository())
    assert lib.list_documents() == []


def test_list_documents_and_get_document_round_trip() -> None:
    repo = FakeRepository()
    doc = repo.upsert_document(_doc("far-25"))
    lib = LibraryService(repository=repo)

    listed = lib.list_documents()
    assert [d.slug for d in listed] == ["far-25"]
    assert lib.get_document("far-25") == doc


def test_get_document_unknown_slug_returns_none_does_not_raise() -> None:
    lib = LibraryService(repository=FakeRepository())
    assert lib.get_document("no-such-slug") is None


def test_section_tree_parents_before_children_in_order() -> None:
    repo = FakeRepository()
    doc = repo.upsert_document(_doc("far-25"))
    parent = _section(doc, "25.1309", level=2, ordinal=10)
    child_a = _section(doc, "25.1309(a)", level=3, ordinal=11, parent_id=parent.id)
    child_b = _section(doc, "25.1309(b)", level=3, ordinal=12, parent_id=parent.id)
    repo.replace_sections_and_chunks(doc.id, [parent, child_a, child_b], [])

    tree = LibraryService(repository=repo).get_section_tree(doc.id)
    # FakeRepository / pg_repo both order by (level, ordinal): parent first.
    assert [s.clause_id for s in tree] == ["25.1309", "25.1309(a)", "25.1309(b)"]


def test_section_tree_unknown_document_returns_empty() -> None:
    lib = LibraryService(repository=FakeRepository())
    assert lib.list_chunks(uuid4()) == []
    assert lib.get_section_tree(uuid4()) == []


def test_list_chunks_ordered_by_clause_path() -> None:
    repo = FakeRepository()
    doc = repo.upsert_document(_doc("far-25"))
    sec = _section(doc, "25.1309", level=2, ordinal=10)
    # Insert in a deliberately non-sorted order; list_chunks must sort by clause_path.
    c3 = _chunk(doc, sec, "14 CFR Part 25 §25.1309", 100)
    c1 = _chunk(doc, sec, "14 CFR Part 25 §25.1001", 100)
    c2 = _chunk(doc, sec, "14 CFR Part 25 §25.1309(a)", 100)
    repo.replace_sections_and_chunks(doc.id, [sec], [c3, c1, c2])

    chunks = LibraryService(repository=repo).list_chunks(doc.id)
    assert [c.clause_path for c in chunks] == [
        "14 CFR Part 25 §25.1001",
        "14 CFR Part 25 §25.1309",
        "14 CFR Part 25 §25.1309(a)",
    ]


def test_get_ask_citations_ordered_by_rank_and_unknown_returns_empty() -> None:
    repo = FakeRepository()
    ask = Ask(id=uuid4(), question="q", status=AskStatus.GROUNDED, answer_md="a")
    cit3 = Citation(chunk_id=uuid4(), rank=3, score=0.5, clause_path="§25.999")
    cit1 = Citation(chunk_id=uuid4(), rank=1, score=0.9, clause_path="§25.1309")
    cit2 = Citation(chunk_id=uuid4(), rank=2, score=0.8, clause_path="§25.1309(a)")
    repo.save_ask(ask, [cit3, cit1, cit2])  # deliberately unsorted by rank

    assert [c.rank for c in repo.get_ask_citations(ask.id)] == [1, 2, 3]
    assert repo.get_ask_citations(uuid4()) == []  # unknown ask → empty, not raise


def test_list_eval_runs_newest_first_and_unknown_returns_none() -> None:
    repo = FakeRepository()
    run_old = EvalRun(id=uuid4(), git_sha="aaa", config={})
    run_new = EvalRun(id=uuid4(), git_sha="bbb", config={})
    repo.save_eval_run(run_old, [], [])
    repo.save_eval_run(run_new, [], [])

    runs = repo.list_eval_runs()
    # Newest first: the run inserted later leads.
    assert runs[0].id == run_new.id
    assert runs[1].id == run_old.id
    assert repo.get_eval_run(uuid4()) is None
