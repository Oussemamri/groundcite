"""Unit tests for the clause_chunker adapter (spec §6 step 3).

Uses a deterministic fake ``count_tokens`` (whitespace split) so no embedding
library is needed (spec §6.1 #4: the real tokenizer is injected in production,
faked here). Covers breadcrumb headers, ≤450-token chunks, 60-token overlap on
splits, and the tiny-leaf merge up to the parent (MIN_LEAF_TOKENS).
"""

from __future__ import annotations

from uuid import uuid4

from groundcite.adapters.chunker.clause_chunker import ClauseChunker, _split
from groundcite.domain.entities import ParsedDocument, Section


def _count_tokens(text: str) -> int:
    return len(text.split())


def _sec(cid: str, level: int, parent_id=None, title=None):
    return Section(
        id=uuid4(),
        document_id=uuid4(),
        parent_id=parent_id,
        clause_id=cid,
        title=title,
        level=level,
        ordinal=0,
    )


def _doc_kwargs(sections, standard_code="14 CFR Part 25"):
    return {
        "pages": (),
        "document_id": sections[0].document_id,
        "standard_code": standard_code,
        "title": "FAR Part 25",
    }


def _words(n: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_one_chunk_per_short_leaf_with_breadcrumb() -> None:
    sub = _sec("Subpart F", 1, parent_id=None, title="Equipment")
    sec = _sec("25.1309", 2, parent_id=sub.id, title="Equipment, systems, and installations.")
    sections = [sub, sec]
    parsed = ParsedDocument(**_doc_kwargs(sections))
    # ≥ MIN_LEAF_TOKENS so sec is a standalone leaf (not merged up to the subpart).
    text = {sec.id: _words(70)}
    chunks = ClauseChunker(min_leaf_tokens=64).chunk(parsed, sections, text, _count_tokens)

    assert len(chunks) == 1
    c = chunks[0]
    assert c.section_id == sec.id
    assert c.clause_path == "14 CFR Part 25 §25.1309"
    assert c.content.startswith(
        "[14 CFR Part 25 §25.1309 — Equipment > Equipment, systems, and installations.]"
    )
    assert _words(0) in c.content  # the body survives
    assert c.token_count == _count_tokens(c.content)


def test_long_clause_splits_into_bounded_chunks() -> None:
    sec = _sec("25.1", 2, title="Title")
    sections = [sec]
    parsed = ParsedDocument(**_doc_kwargs(sections))
    body = " ".join(f"sentence{i}." for i in range(1000))  # 1000 tokens
    text = {sec.id: body}

    chunks = ClauseChunker(min_leaf_tokens=64).chunk(parsed, sections, text, _count_tokens)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.token_count <= 500  # ≤450 chunk + sentence-boundary slack


def test_split_helper_produces_overlap() -> None:
    # Direct test of the sentence-bounded splitter (no breadcrumb in the way).
    body = " ".join(f"s{i}." for i in range(1000))
    pieces = _split(body, _count_tokens, 450, 60)
    assert len(pieces) >= 2
    # The carry from the end of piece 0 reappears at the start of piece 1.
    tail = pieces[0].split()[-60:]
    head = pieces[1].split()[:60]
    assert tail == head


def test_tiny_leaf_merges_up_to_parent() -> None:
    parent = _sec("25.2", 2, title="Parent section")
    a = _sec("25.2(a)", 3, parent_id=parent.id, title=None)
    sections = [parent, a]
    parsed = ParsedDocument(**_doc_kwargs(sections))
    # (a) is tiny (< 64 tokens) → merges up into the parent's chunk.
    text = {parent.id: _words(40, "intro"), a.id: "Tiny clause."}

    chunks = ClauseChunker(min_leaf_tokens=64).chunk(parsed, sections, text, _count_tokens)
    assert len(chunks) == 1
    assert chunks[0].section_id == parent.id
    assert "Tiny clause." in chunks[0].content
    assert "intro0" in chunks[0].content


def test_tiny_root_leaf_emits_own_chunk() -> None:
    # A tiny leaf at the document root (no parent to merge into) still emits.
    sec = _sec("25.9", 2, title="T")
    parsed = ParsedDocument(**_doc_kwargs([sec]))
    chunks = ClauseChunker(min_leaf_tokens=64).chunk(
        parsed, [sec], {sec.id: "tiny body"}, _count_tokens
    )
    assert len(chunks) == 1
    assert chunks[0].section_id == sec.id


def test_subparagraph_leaf_emits_qualified_clause_path() -> None:
    sec = _sec("25.3", 2, title="S")
    a = _sec("25.3(a)", 3, parent_id=sec.id, title=None)
    sections = [sec, a]
    parsed = ParsedDocument(**_doc_kwargs(sections))
    # The section's own intro is tiny → it attaches to its first leaf (a),
    # which is a standalone leaf emitting at §25.3(a). So only §25.3(a) emits.
    text = {
        sec.id: "Section intro words.",
        a.id: _words(80, "para"),
    }

    chunks = ClauseChunker(min_leaf_tokens=64).chunk(parsed, sections, text, _count_tokens)
    clause_paths = {c.clause_path for c in chunks}
    assert clause_paths == {"14 CFR Part 25 §25.3(a)"}
    # The section intro rides with its first paragraph:
    assert "Section intro words." in chunks[0].content


def test_missing_document_id_yields_no_chunks() -> None:
    sec = _sec("25.9", 2, title="T")
    parsed = ParsedDocument(pages=(), standard_code="X", title="t")  # document_id None
    chunks = ClauseChunker().chunk(parsed, [sec], {sec.id: "body"}, _count_tokens)
    assert chunks == []


def test_chunk_token_count_includes_breadcrumb() -> None:
    sec = _sec("25.1309", 2, title="E")
    parsed = ParsedDocument(**_doc_kwargs([sec]))
    body = _words(70)
    chunks = ClauseChunker().chunk(parsed, [sec], {sec.id: body}, _count_tokens)
    assert chunks[0].token_count == _count_tokens(chunks[0].content)
