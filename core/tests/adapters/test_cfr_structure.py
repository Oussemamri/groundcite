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


def _h(text: str) -> ParsedBlock:
    """A typographic heading line: govinfo CFR prints real § / Subpart headings
    in bold at body size, while running prose is body weight — the signal the
    detector requires before a regex match may open a section."""
    return ParsedBlock(text=text, page_number=1, font_size=8.0, is_bold=True)


def _big(text: str) -> ParsedBlock:
    """A display heading set larger than body size but not bold — how govinfo
    prints Subpart headings (10pt over an 8pt body)."""
    return ParsedBlock(text=text, page_number=1, font_size=10.0, is_bold=False)


def _small(text: str) -> ParsedBlock:
    """Sub-body type (7pt): govinfo sets appendix BODY text and the table of
    contents below the 8pt modal body size. This is the signal that separates a
    real appendix heading (8pt) from its TOC copy (7pt)."""
    return ParsedBlock(text=text, page_number=1, font_size=7.0, is_bold=False)


def _doc(
    blocks_per_page: list[list[str | ParsedBlock]], document_id: UUID | None = None
) -> ParsedDocument:
    """Plain strings become body-weight blocks (font 8.0, not bold); pass a
    ParsedBlock (e.g. via ``_h``) to control typography."""
    pages = [
        ParsedPage(
            page_number=i + 1,
            blocks=tuple(
                b
                if isinstance(b, ParsedBlock)
                else ParsedBlock(text=b, page_number=i + 1, font_size=8.0, is_bold=False)
                for b in bl
            ),
        )
        for i, bl in enumerate(blocks_per_page)
    ]
    return ParsedDocument(pages=tuple(pages), document_id=document_id)


def test_builds_subpart_section_and_subparagraphs() -> None:
    did = uuid4()
    parsed = _doc(
        [
            [
                _h("Subpart B—Flight"),
                _h("§ 25.1309 Equipment, systems, and installations."),
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
                _h("§ 25.1 Section title."),
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
            [_h("§ 25.1309 Equipment."), "Body one."],
            # Page-top running head: bare § number, NOT bold → recognized noise.
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
                _h("§ 25.1 First section."),
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
                _h("§ 25.1 One short section."),
            ]
        ],
        document_id=did,
    )
    with pytest.raises(StructureError) as exc:
        CfrStructureDetector().detect(parsed)
    assert "90%" in str(exc.value) or "<90" in str(exc.value)


def test_missing_document_id_raises() -> None:
    parsed = _doc([[_h("§ 25.1 Section."), "body"]], document_id=None)
    with pytest.raises(StructureError):
        CfrStructureDetector().detect(parsed)


def test_paragraph_cross_reference_body_is_not_a_header() -> None:
    did = uuid4()
    parsed = _doc(
        [
            [
                _h("§ 25.1 Section."),
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


def test_prose_cross_part_reference_is_not_a_header() -> None:
    """Bug seen on far-25: SFAR body text cites 14 CFR part 21, and the line
    wrap puts ``§ 21.4(a)(6) encountered ...`` at the start of a parsed block.
    That block is NOT bold (running prose), so it must stay body text — never a
    phantom part-21 section swallowing everything until the next real header."""
    did = uuid4()
    parsed = _doc(
        [
            [
                _h("§ 25.1309 Equipment, systems, and installations."),
                "(a) Equipment must be approved as required by 14 CFR part 21 and withstand",
                "§ 21.4(a)(6) encountered during the phases of flight and other operations.",
                _h("§ 25.1310 Power source capacity and distribution."),
                "(a) Each power source must be able to supply its loads reliably.",
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    clauses = {s.clause_id for s in sections}
    assert not any(c.startswith("21") for c in clauses), (
        "in-prose part-21 reference opened a phantom section"
    )
    a = next(s for s in sections if s.clause_id == "25.1309(a)")
    assert "21.4(a)(6) encountered" in text[a.id], "the wrapped reference must stay body text"
    assert "25.1310" in clauses, "the next real bold header must still open a section"


def test_page_top_running_head_does_not_preempt_the_real_heading() -> None:
    """A bare, non-bold ``§ 25.1309`` page running head must neither open a
    titleless section ahead of the real bold heading nor demote that heading
    to a 'repeat' — the failure that blanked every section title on far-25."""
    did = uuid4()
    parsed = _doc(
        [
            [
                "§ 25.1309",  # running head at page top: bare number, not bold
                _h("§ 25.1309 Equipment."),
                "(a) Body text of the equipment section that is long enough to matter.",
            ]
        ],
        document_id=did,
    )
    sections, _ = CfrStructureDetector().detect(parsed)
    matches = [s for s in sections if s.clause_id == "25.1309"]
    assert len(matches) == 1
    assert matches[0].title == "Equipment"


def test_toc_subpart_lines_do_not_open_sections() -> None:
    """Bug seen on far-25: the table of contents repeats every Subpart line at
    body size. Those matched the Subpart regex, opened all subparts up front,
    and left the LAST one on the stack — so every real section nested under
    'Subpart I — Special Federal Aviation'. Only display typography (larger
    than the modal body size, or bold) may open a Subpart."""
    did = uuid4()
    body = "(a) This part prescribes airworthiness standards for transport category airplanes. " * 8
    parsed = _doc(
        [
            [
                "Subpart A—General",  # TOC copy: body size ⇒ not a header
                "Subpart I—Special Federal",  # TOC copy: body size ⇒ not a header
                _big("Subpart A—General"),  # real display heading (10pt > 8pt body)
                _h("§ 25.1 Applicability."),
                body,
            ]
        ],
        document_id=did,
    )
    sections, _ = CfrStructureDetector().detect(parsed)
    level1 = [s for s in sections if s.level == 1]
    assert [s.clause_id for s in level1] == ["Subpart A"], "only the display heading opens"
    sec = next(s for s in sections if s.clause_id == "25.1")
    assert sec.parent_id == level1[0].id, "sections must nest under their true subpart"
    assert not any(s.clause_id == "Subpart I" for s in sections)


def test_wrapped_heading_titles_continue_across_blocks() -> None:
    """govinfo headings wrap in narrow columns: 'Subpart G—Operating
    Limitations' / 'and Information' (both 10pt), and '§ 25.1309' /
    'Equipment, systems, and in-' / 'stallations.' (all bold). Continuation
    blocks share the heading's typography and merge into its title, honoring
    print hyphenation."""
    did = uuid4()
    body = "(a) Each operating limitation must be furnished as specified in this subpart. " * 4
    parsed = _doc(
        [
            [
                _big("Subpart G—Operating Limitations"),
                _big("and Information"),
                _h("§ 25.1309"),
                _h("Equipment, systems, and in-"),
                _h("stallations."),
                body,
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    sub = next(s for s in sections if s.level == 1)
    assert sub.title == "Operating Limitations and Information"
    sec = next(s for s in sections if s.clause_id == "25.1309")
    assert sec.title == "Equipment, systems, and installations"
    assert sec.parent_id == sub.id
    # Body prose after the heading run is NOT part of the title.
    a = next(s for s in sections if s.clause_id == "25.1309(a)")
    assert "operating limitation" in text[a.id]


def test_appendix_headings_open_top_level_sections() -> None:
    """Bug seen on far-25: Part 25's appendices carry no "§ x.y" heading, so ALL
    of their text (22.8% of the document) attached to the nearest preceding
    section — §25.1801 — which then held 187k chars and produced 84 oversized,
    mislabeled chunks. "APPENDIX C TO PART 25" is a real structural boundary and
    must open its own top-level section, sibling to the Subparts."""
    did = uuid4()
    parsed = _doc(
        [
            [
                _big("Subpart I—Special Federal Aviation Regulations"),
                _h("§ 25.1801 SFAR No. 111."),
                _small("The SFAR body text about lavatory oxygen systems."),
                # Real appendix headings sit AT the modal body size (8pt).
                "APPENDIX C TO PART 25",
                _small("Part I—Atmospheric Icing Conditions. Continuous maximum icing applies."),
                "APPENDIX D TO PART 25",
                _small("Criteria for determining minimum flight crew are as follows."),
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    by_clause = {s.clause_id: s for s in sections}

    assert "Appendix C" in by_clause, "an appendix heading must open a section"
    assert "Appendix D" in by_clause
    app_c = by_clause["Appendix C"]
    app_d = by_clause["Appendix D"]

    # Top-level: a sibling of the Subparts, not a child of §25.1801.
    assert app_c.level == 1 and app_d.level == 1
    assert app_c.parent_id is None and app_d.parent_id is None

    # The appendix text belongs to the appendix — NOT to §25.1801.
    assert "Atmospheric Icing" in text[app_c.id]
    assert "minimum flight crew" in text[app_d.id]
    sfar = by_clause["25.1801"]
    assert "Atmospheric Icing" not in text[sfar.id], "appendix text must not leak into §25.1801"
    assert "minimum flight crew" not in text[sfar.id]
    assert "lavatory oxygen" in text[sfar.id], "the SFAR keeps its own body"


def test_toc_appendix_lines_do_not_open_sections() -> None:
    """The same TOC trap as the Subparts: govinfo lists every appendix in the
    table of contents at 7pt, BELOW the 8pt modal body size. Only a heading at
    the modal size is a real boundary — otherwise the TOC would open all 14
    appendices before the document body even starts."""
    did = uuid4()
    # Body text at the modal size must dominate, as it does in the real document
    # (far-25: 17,814 blocks at 8pt vs 8,004 at 7pt) — the modal size IS the body.
    body = [
        f"(a)({i}) A body paragraph of the applicability section, long enough that the "
        f"two orphaned table-of-contents lines stay well under the 10% orphan budget."
        for i in range(6)
    ]
    parsed = _doc(
        [
            [
                _small("APPENDIX C TO PART 25"),  # TOC copy (7pt) ⇒ not a heading
                _small("APPENDIX D TO PART 25"),  # TOC copy ⇒ not a heading
                _big("Subpart A—General"),
                _h("§ 25.1 Applicability."),
                *body,
            ]
        ],
        document_id=did,
    )
    sections, _ = CfrStructureDetector().detect(parsed)
    assert not any(s.clause_id.startswith("Appendix") for s in sections), (
        "table-of-contents appendix lines must not open sections"
    )
    assert [s.clause_id for s in sections if s.level == 1] == ["Subpart A"]


def test_prose_mentioning_an_appendix_is_not_a_heading() -> None:
    """Running prose cites appendices constantly ("in accordance with Appendix K",
    "with appendix F, parts IV and V"). Only the ALL-CAPS "APPENDIX x TO PART n"
    form is a heading — a mixed-case mention is body text."""
    did = uuid4()
    parsed = _doc(
        [
            [
                _big("Subpart A—General"),
                _h("§ 25.1 Applicability."),
                "(a) Each airplane must comply with Appendix K, and need not meet appendix F "
                "parts IV and V, to part 25, when showing compliance with this section.",
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    assert not any(s.clause_id.startswith("Appendix") for s in sections)
    a = next(s for s in sections if s.clause_id == "25.1(a)")
    assert "Appendix K" in text[a.id], "the mention stays body text"


def test_page_furniture_is_dropped_from_chunk_text() -> None:
    """The source PDF stamps print-production footers and running heads on every
    page — together ~4% of far-25's text. None of it is regulatory content, and
    all of it would otherwise be embedded INSIDE retrievable chunks, degrading
    both the dense and the lexical signal. Recognized noise, like page numbers:
    dropped, not counted as orphan text we failed to attach."""
    did = uuid4()
    noise_blocks = [
        # govinfo print footer
        "VerDate Sep<11>2014",
        "09:06 Jun 28, 2024",
        "Jkt 262046",
        "PO 00000",
        "Frm 00204",
        "Fmt 8010",
        "Sfmt 8010",
        r"Y:\SGML\262046.XXX",
        # running heads
        "14 CFR Ch. I (1–1–24 Edition)",
        "Federal Aviation Administration, DOT",
        "Pt. 25, App. C",
        # typesetter proof stamp + SGML graphic refs (figure-only appendices)
        "jspears on DSK121TN23PROD with CFR",
        "262046 EC28SE91.050</GPH>",
    ]
    parsed = _doc(
        [
            [
                _big("Subpart A—General"),
                _h("§ 25.1 Applicability."),
                "(a) This part prescribes airworthiness standards for transport airplanes.",
                *[ParsedBlock(text=t, page_number=1, font_size=6.5) for t in noise_blocks],
                "(b) The airplane must also meet the applicable noise requirements.",
            ]
        ],
        document_id=did,
    )
    _, text = CfrStructureDetector().detect(parsed)  # must not raise on orphans
    joined = "".join(text.values())
    for noise in (
        "VerDate",
        "Jkt 262046",
        "PO 00000",
        "Frm 00204",
        "Sfmt",
        "SGML",
        "CFR Ch.",
        "DOT",
        "Pt. 25",
        "DSK",
        "GPH",
    ):
        assert noise not in joined, f"page furniture {noise!r} leaked into chunk text"
    assert "airworthiness standards" in joined
    assert "noise requirements" in joined


def test_real_content_sharing_the_footer_font_size_survives() -> None:
    """The footer is matched by PATTERN, never by font size — ~564 legitimate
    blocks (table cells) share its 6.5pt, and dropping those would delete real
    regulatory content."""
    did = uuid4()
    parsed = _doc(
        [
            [
                _big("Subpart A—General"),
                _h("§ 25.1 Applicability."),
                "(a) The following table prescribes the required load factors.",
                # Real table content, same 6.5pt as the print footer.
                ParsedBlock(text="Maximum weight 12,500 pounds", page_number=1, font_size=6.5),
                ParsedBlock(text="Load factor 2.5", page_number=1, font_size=6.5),
            ]
        ],
        document_id=did,
    )
    _, text = CfrStructureDetector().detect(parsed)
    joined = "".join(text.values())
    assert "Maximum weight 12,500 pounds" in joined
    assert "Load factor 2.5" in joined


def test_appendix_title_continues_across_wrapped_lines() -> None:
    """Appendix titles wrap at heading size (8pt) while appendix BODY is 7pt, so
    the existing wrapped-title rule picks the title up and stops at the body."""
    did = uuid4()
    parsed = _doc(
        [
            [
                _big("Subpart A—General"),
                _h("§ 25.1 Applicability."),
                _small("(a) Body of the applicability section, long enough to matter here."),
                "APPENDIX H TO PART 25—INSTRUCTIONS",
                "FOR CONTINUED AIRWORTHINESS",
                _small("H25.1 General. This appendix specifies requirements."),
            ]
        ],
        document_id=did,
    )
    sections, text = CfrStructureDetector().detect(parsed)
    app = next(s for s in sections if s.clause_id == "Appendix H")
    assert app.title == "INSTRUCTIONS FOR CONTINUED AIRWORTHINESS"
    assert "H25.1 General" in text[app.id], "7pt body is NOT swallowed into the title"
