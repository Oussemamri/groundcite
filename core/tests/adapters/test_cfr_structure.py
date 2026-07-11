"""Unit tests for the cfr_structure StructureDetector adapter (spec §6 step 2).

No fake port needed — StructureDetector.detect takes a ParsedDocument (a domain
object), so these build a synthetic ParsedDocument directly and assert on the
returned Section tree + SectionTextMap. This is the spec §6 step 2 contract:
CFR headers (§25.1309, (a)(1)(i) sub-levels), orphan attachment to the nearest
preceding section, and the loud <90% failure.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from groundcite.adapters.structure.cfr_structure import (
    CfrStructureDetector,
    StructureError,
)
from groundcite.domain.entities import ParsedBlock, ParsedDocument, ParsedPage


def _doc(blocks_per_page: list[list[str]], document_id: UUID | None = None) -> ParsedDocument:
    pages = [
        ParsedPage(
            page_number=i + 1, blocks=tuple(ParsedBlock(text=t, page_number=i + 1) for t in bl)
        )
        for i, bl in enumerate(blocks_per_page)
    ]
    return ParsedDocument(pages=tuple(pages), document_id=document_id)


def test_builds_subpart_section_and_subparagraphs() -> None:
    did = uuid4()
    parsed = _doc(
        [
            [
                "Subpart B—Flight",
                "§ 25.1309 Equipment, systems, and installations.",
                "The applicant must show that the equipment is designed to function.",
                "(a) Each item of equipment must independently perform its function.",
                "(a)(1) For catastrophic conditions, a one-to-million probability.",
                "(b) Each item must be installed in a safe manner.",
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)

    by_clause = {s.clause_id: s for s in sections}
    assert "Subpart B" in by_clause
    assert "25.1309" in by_clause
    assert "25.1309(a)" in by_clause
    assert "25.1309(a)(1)" in by_clause
    assert "25.1309(b)" in by_clause

    sub = by_clause["Subpart B"]
    sec = by_clause["25.1309"]
    a = by_clause["25.1309(a)"]
    a1 = by_clause["25.1309(a)(1)"]
    b = by_clause["25.1309(b)"]

    assert sub.level == 1 and sec.level == 2 and a.level == 3
    assert a1.level == 4 and b.level == 3
    assert sec.parent_id == sub.id
    assert a.parent_id == sec.id and b.parent_id == sec.id
    assert a1.parent_id == a.id
    assert a.ordinal == 0 and b.ordinal == 1
    assert sec.title == "Equipment, systems, and installations"
    assert sub.title == "Flight"
    assert a.title is None  # sub-paragraphs carry body text, not a title

    # Each section's text map carries its body; the body block "The applicant..."
    # attaches to the nearest preceding section (the §25.1309 section).
    assert "applicant must show" in text[sec.id]
    assert "For catastrophic conditions" in text[a1.id]
    assert "independently perform" in text[a.id]


def test_roman_and_uppercase_sublevels_use_parent_context() -> None:
    did = uuid4()
    parsed = _doc(
        [
            [
                "§ 25.1 Section title.",
                "(a) Top paragraph.",
                "(1) Sub paragraph.",
                "(i) Roman level.",
                "(A) Uppercase level.",
            ]
        ],
        document_id=did,
    )
    sections, _ = CfrStructureDetector().detect(parsed)
    by_clause = {s.clause_id: s for s in sections}
    assert by_clause["25.1(a)"].level == 3
    assert by_clause["25.1(a)(1)"].level == 4
    assert by_clause["25.1(a)(1)(i)"].level == 5
    assert by_clause["25.1(a)(1)(i)(A)"].level == 6


def test_repeat_header_is_running_header_not_new_section() -> None:
    did = uuid4()
    parsed = _doc(
        [
            ["§ 25.1309 Equipment.", "Body one."],
            ["§ 25.1309", "Body two continuing under the same section."],
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    section_1309s = [s for s in sections if s.clause_id == "25.1309"]
    assert len(section_1309s) == 1, "a repeated §-header must not open a new section"
    sid = section_1309s[0].id
    assert "Body one." in text[sid]
    assert "continuing under the same section" in text[sid]


def test_body_before_first_section_is_orphan_without_failing_when_minor() -> None:
    did = uuid4()
    parsed = _doc(
        [
            [
                "Hdr",  # tiny front-matter orphan (< 10% of total)
                "§ 25.1 First section.",
                "Body of first section that is reasonably long so the orphan is minor.",
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    assert any(s.clause_id == "25.1" for s in sections)
    # The orphan front matter is attached to no section:
    total_text = "".join(text.values())
    assert "Hdr" not in total_text


def test_fails_loudly_when_attached_ratio_below_90() -> None:
    did = uuid4()
    parsed = _doc(
        [
            [
                # A large volume of front-matter text with NO enclosing section,
                # then a tiny section at the end → attached ratio < 90%.
                "orphan body line that is long " * 60,
                "§ 25.1 One short section.",
            ]
        ],
        document_id=did,
    )
    with pytest.raises(StructureError) as exc:
        CfrStructureDetector().detect(parsed)
    assert "90%" in str(exc.value) or "<90" in str(exc.value)


def test_missing_document_id_raises() -> None:
    parsed = _doc([["§ 25.1 Section.", "body"]], document_id=None)
    with pytest.raises(StructureError):
        CfrStructureDetector().detect(parsed)


def test_paragraph_cross_reference_body_is_not_a_header() -> None:
    did = uuid4()
    parsed = _doc(
        [
            [
                "§ 25.1 Section.",
                "(a) A paragraph.",
                "Refer to paragraph (a)(1) for the catastrophic case.",  # not a header
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    clauses = {s.clause_id for s in sections}
    assert "25.1(a)(1)" not in clauses, "a mid-text cross-reference must not parse as a header"
    a = next(s for s in sections if s.clause_id == "25.1(a)")
    assert "Refer to paragraph" in text[a.id]
