"""Implements StructureDetector (spec §6 step 2): CFR-style clause tree builder.

Organization: FAA / EASA CFR numbering (spec §6 step 2 "CFR style: § 25.1309,
(a)(1)(i) sub-levels"). An ECSS/NASA numeric-hierarchy adapter (``ecss_structure``)
arrives later (spec §16) behind the same port — this one is the FAA default.

The detector is pure given a ``ParsedDocument``: it walks the ordered text
blocks, detects clause headers with regex, builds the ``Section`` tree, and
attaches non-header text to the nearest preceding section (spec §6 step 2).
It FAILS LOUDLY (raises) if <90% of document text attaches to a section.

Sub-paragraph levels are disambiguated by ANCESTOR CONTEXT, not by the label
pattern alone, because lowercase roman (i, v, x, ...) collides with the letter
level (a-z). A paren token is matched to the deepest ancestor whose expected
child level the token satisfies: a sibling ``(b)`` after ``(a)(1)`` pops back to
the section level (letter L3) while ``(i)`` after ``(1)`` nests as roman L5.
CFR order:
    L2 §25.1309  → L3 (a)   one lowercase letter
    L3 (a)       → L4 (1)   digits
    L4 (1)       → L5 (i)   lowercase roman
    L5 (i)       → L6 (A)   one uppercase letter

Real CFR paragraphs often carry the full chain on one line ("(a)(1) When...");
the detector opens the chain as nested sub-sections.

A ``§ X.Y`` match alone is NOT a header: govinfo CFR prints real section
headings in bold, while running prose is body weight. A NON-bold §-line is
either a page-top running head (bare number, e.g. ``§ 25.1309`` — recognized
noise, excluded from the 90% accounting like page numbers) or an in-prose
cross-reference that line-wrapped onto a fresh line (e.g. SFAR text citing
``§ 21.4(a)(6) encountered during ...`` from 14 CFR part 21) — body text
attached to the open section, never a section boundary. Clause-id uniqueness
remains as a second guard: a bold header whose clause_id already exists is a
repeat and does not open a new section. The parser stays a dumb extractor;
noise lives here.

Likewise a ``Subpart X—Title`` match is a header only with display typography:
bold, or a font size LARGER than the document's modal (body) size. The
table of contents repeats every Subpart line at body size — matching those
would open all nine subparts up front and leave the LAST one on the stack, so
every real section would nest under it (the far-25 "everything under Subpart I"
bug). Headings also wrap in the narrow govinfo columns; blocks that follow a
just-opened heading with the SAME typography and match no header pattern are
title continuations ("Subpart G—Operating Limitations" / "and Information",
"§ 25.1309" / "Equipment, systems, and in-" / "stallations."), merged into the
section title with print-hyphenation ("in-" + "stallations") joined.

APPENDICES are the third top-level structure. Part 25's appendices carry no
"§ x.y" heading at all, so without this rule ALL of their text (22.8% of the
document) attached to the nearest preceding section — §25.1801 — leaving it with
187k chars and 84 oversized, mislabeled chunks. An "APPENDIX C TO PART 25" line
opens a level-1 section, sibling to the Subparts. Two guards, both measured on
far-25: the match is CASE-SENSITIVE all-caps, so the constant mixed-case prose
mentions ("in accordance with Appendix K", "with appendix F, parts IV and V")
are body text; and the heading must sit AT the modal body size, because the
table of contents lists every appendix one size DOWN (7pt vs the 8pt body) —
the same TOC trap the Subparts had. Appendix titles wrap at heading size while
appendix body text is smaller, so the title-continuation rule above picks the
title up and stops cleanly at the body.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from uuid import UUID, uuid4

from groundcite.domain.entities import ParsedBlock, ParsedDocument, Section
from groundcite.ports.protocols import SectionTextMap, StructureDetector

# Header regexes (operate on a single block's text, at line start).
_SUBPART_RE = re.compile(r"^Subpart\s+([A-Z])\s*[—–\-]\s*(.+)$")
_SECTION_RE = re.compile(r"^§\s*(\d+(?:\.\d+)*)\s*(.*)$")
# "APPENDIX C TO PART 25" / "APPENDIX H TO PART 25—INSTRUCTIONS ...".
# CASE-SENSITIVE on purpose: prose cites appendices constantly in mixed case
# ("Appendix K", "appendix F, parts IV and V"), and those are body text.
_APPENDIX_RE = re.compile(r"^APPENDIX\s+([A-Z])\s+TO\s+PART\s+\d+\s*(?:[—–\-]\s*(.*))?$")
# A compound "(a)(1)(i)" chain of leading paren groups, followed by body text.
# The inner [^)]{1,8} also rejects "(see paragraph ...)" mid-text cross-refs
# whose label is a long sentence, so they never parse as headers.
_PAREN_CHAIN_RE = re.compile(r"^((?:\([^)]{1,8}\))+)\s*(.*)$")
_LABEL_RE = re.compile(r"\(([^)]{1,8})\)")
_PURE_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")
# Page furniture the source PDF stamps on every page — print-production footers
# and running heads. Measured on far-25 (blocks / chars):
#   VerDate|Jkt|PO|Frm|Fmt|Sfmt|timestamp   1,939 / 22,437   govinfo print footer
#   Y:\SGML\262046.XXX                        277 /  4,986   typesetter paths
#   "14 CFR Ch. I (1-1-24 Edition)"           139 /  4,031   running head (verso)
#   "Federal Aviation Administration, DOT"    138 /  4,968   running head (recto)
#   "Pt. 25, App. C"                          104 /  1,445   running head
# Together ~4% of the document's text. None of it is regulatory content, and all
# of it would otherwise be embedded INSIDE retrievable chunks, degrading both the
# dense and lexical signal. Dropped like page numbers: recognized noise, excluded
# from the 90% orphan accounting rather than counted as text we failed to attach.
#
# Matched by PATTERN, never by font size — ~564 legitimate blocks (table cells)
# share the footer's 6.5pt, and filtering by size would delete real content.
_PAGE_NOISE_RE = re.compile(
    r"^(?:VerDate\b"
    r"|Jkt\s+\d"
    r"|PO\s+\d"
    r"|Frm\s+\d"
    r"|Fmt\s+\d"
    r"|Sfmt\s+\d"
    r"|[A-Za-z]:\\"  # Y:\SGML\..., E:\FR\FM\...
    r"|\d+\s+CFR\s+Ch\."  # "14 CFR Ch. I (1-1-24 Edition)"
    r"|Federal Aviation Administration, DOT\s*$"
    r"|Pt\.\s+\d"  # "Pt. 25, App. C"
    r"|\w+\s+on\s+DSK"  # "jspears on DSK121TN23PROD with CFR" (proof stamp)
    r"|\d{2}:\d{2}\s+\w{3}\s+\d{1,2},\s+\d{4}$)"
)
# SGML graphic references left in the text layer of figure-only appendices, e.g.
# "ER18FE98.004</GPH>", "262046 EC28SE91.050</GPH>". Searched (not anchored)
# because the tag trails a document id. 77 blocks on far-25.
_GRAPHIC_REF_RE = re.compile(r"</?GPH>")
# A word broken across a line by govinfo's justified two-column layout:
# "within 90 sec-" + "onds". 17.4% of far-25's lines end this way (see _append_line).
_SOFT_HYPHEN_END_RE = re.compile(r"[A-Za-z]-$")

# Valid lowercase roman numerals (enough for CFR sub-sub levels).
_ROMAN = {
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "vi",
    "vii",
    "viii",
    "ix",
    "x",
    "xi",
    "xii",
    "xiii",
    "xiv",
    "xv",
    "xvi",
    "xvii",
    "xviii",
    "xix",
    "xx",
    "l",
    "c",
    "d",
    "m",
}

# Below this fraction of document text attached to a section, ingestion fails
# (spec §6 step 2 / step 5: "fail loudly on <90% text attached to sections").
MIN_ATTACHED_RATIO = 0.90


class StructureError(RuntimeError):
    """Raised when structure detection cannot attach ≥90% of document text
    to sections (spec §6 step 2). The message carries the measured ratio."""


class CfrStructureDetector(StructureDetector):
    """Builds the CFR-style Section clause tree (spec §6 step 2)."""

    def detect(self, doc: ParsedDocument) -> tuple[list[Section], SectionTextMap]:
        document_id = doc.document_id
        if document_id is None:
            raise StructureError(
                "ParsedDocument.document_id is None — IngestionService must enrich "
                "the parsed document with the upserted Document.id before detection "
                "(spec §6 ParsedDocument seam)."
            )
        sections: list[Section] = []
        text_map: dict[UUID, str] = defaultdict(str)
        clause_to_section: dict[str, Section] = {}
        stack: list[Section] = []
        next_ordinal: dict[tuple[UUID | None, int], int] = defaultdict(int)

        attached_chars = 0
        total_chars = 0

        modal_size = _modal_font_size(doc)
        # Wrapped-heading continuation state: id of the section whose heading
        # may continue on the next block, and the typography of the heading's
        # first block (continuation lines share it exactly).
        title_open: UUID | None = None
        title_sig: tuple[float | None, bool] | None = None

        for page in doc.pages:
            for block in page.blocks:
                text = block.text.rstrip()
                if not text:
                    continue

                # Recognized noise (page numbers, print footers, running heads) is
                # excluded from the 90% accounting: it is structure we deliberately
                # dropped, not "orphan text we couldn't account for".
                if (
                    _PURE_PAGE_NUM_RE.match(text)
                    or _PAGE_NOISE_RE.match(text)
                    or _GRAPHIC_REF_RE.search(text)
                ):
                    title_open = None
                    continue

                subpart = _SUBPART_RE.match(text)
                section_m = _SECTION_RE.match(text)
                if section_m is not None and not block.is_bold:
                    # Not typographically a heading (see module docstring):
                    # bare number ⇒ page running head (recognized noise),
                    # trailing prose ⇒ wrapped in-body cross-reference (body).
                    if section_m.group(2).strip() in ("", "."):
                        title_open = None
                        continue
                    section_m = None
                if subpart is not None and not _is_display_heading(block, modal_size):
                    # Body-size Subpart line ⇒ the table-of-contents copy, not
                    # a section boundary (see module docstring).
                    subpart = None
                appendix = _APPENDIX_RE.match(text)
                if appendix is not None and block.font_size != modal_size:
                    # Appendix headings sit AT the body size; the table of
                    # contents lists them one size DOWN (see module docstring).
                    appendix = None
                chain = self._match_paren_chain(text, stack)

                if (
                    title_open is not None
                    and subpart is None
                    and section_m is None
                    and appendix is None
                    and chain is None
                    and stack
                    and stack[-1].id == title_open
                    and (block.font_size, block.is_bold) == title_sig
                ):
                    # Same-typography non-header block right after a heading:
                    # the wrapped remainder of that heading's title.
                    self._extend_title(stack, sections, clause_to_section, text)
                    _append_line(text_map, stack[-1].id, text)
                    total_chars += len(text)
                    attached_chars += len(text)
                    continue
                title_open = None

                if subpart is not None:
                    clause_id = f"Subpart {subpart.group(1)}"
                    if clause_id in clause_to_section:
                        continue  # repeat ⇒ running header (not counted)
                    title = subpart.group(2).strip().rstrip(".")
                    self._open(
                        (clause_id, 1, title),
                        stack,
                        sections,
                        clause_to_section,
                        next_ordinal,
                        document_id,
                    )
                    title_open = sections[-1].id
                    title_sig = (block.font_size, block.is_bold)
                    _append_line(text_map, sections[-1].id, text)
                    total_chars += len(text)
                    attached_chars += len(text)
                elif appendix is not None:
                    clause_id = f"Appendix {appendix.group(1)}"
                    if clause_id in clause_to_section:
                        continue  # repeat ⇒ running header (not counted)
                    inline_title = (appendix.group(2) or "").strip().rstrip(".")
                    # Level 1: an appendix is a top-level division of the part,
                    # a sibling of the Subparts — never a child of the last
                    # section that happened to precede it.
                    self._open(
                        (clause_id, 1, inline_title or None),
                        stack,
                        sections,
                        clause_to_section,
                        next_ordinal,
                        document_id,
                    )
                    title_open = sections[-1].id
                    title_sig = (block.font_size, block.is_bold)
                    _append_line(text_map, sections[-1].id, text)
                    total_chars += len(text)
                    attached_chars += len(text)
                elif section_m is not None:
                    number = section_m.group(1)
                    if number in clause_to_section:
                        continue  # repeat ⇒ running header (not counted)
                    rest = section_m.group(2).strip()
                    title = rest.rstrip(".") if rest else None
                    self._open(
                        (number, 2, title),
                        stack,
                        sections,
                        clause_to_section,
                        next_ordinal,
                        document_id,
                    )
                    title_open = sections[-1].id
                    title_sig = (block.font_size, block.is_bold)
                    _append_line(text_map, sections[-1].id, text)
                    total_chars += len(text)
                    attached_chars += len(text)
                elif chain is not None:
                    n = self._open_chain(
                        chain,
                        stack,
                        sections,
                        clause_to_section,
                        text_map,
                        next_ordinal,
                        document_id,
                        text,
                    )
                    if n == 0:
                        continue  # whole chain already existed ⇒ running header
                    total_chars += len(text)
                    attached_chars += n
                elif stack:
                    _append_line(text_map, stack[-1].id, text)
                    total_chars += len(text)
                    attached_chars += len(text)
                else:
                    # front-matter orphan (no section yet) ⇒ counts as orphan
                    total_chars += len(text)

        ratio = attached_chars / total_chars if total_chars else 1.0
        if ratio < MIN_ATTACHED_RATIO:
            orphans = total_chars - attached_chars
            raise StructureError(
                f"Structure detection attached {ratio:.1%} of document text to "
                f"sections (<{MIN_ATTACHED_RATIO:.0%} threshold); {orphans} orphan "
                f"chars. Inspect unmatched blocks/regexes (spec §6 step 2)."
            )
        return sections, text_map

    # --- header opening ---------------------------------------------------

    @staticmethod
    def _extend_title(
        stack: list[Section],
        sections: list[Section],
        clause_to_section: dict[str, Section],
        fragment: str,
    ) -> None:
        """Merge a wrapped-heading continuation line into the just-opened
        section's title. ``Section`` is frozen, so the object is replaced in
        every registry that holds it. A trailing ``-`` on the accumulated title
        is print hyphenation: join without a space ("in-" + "stallations.")."""
        old = stack[-1]
        base = old.title or ""
        if base.endswith("-"):
            merged = base[:-1] + fragment
        elif base:
            merged = f"{base} {fragment}"
        else:
            merged = fragment
        new = old.model_copy(update={"title": merged.rstrip(".")})
        stack[-1] = new
        clause_to_section[new.clause_id] = new
        for i in range(len(sections) - 1, -1, -1):
            if sections[i].id == new.id:
                sections[i] = new
                break

    @staticmethod
    def _open(
        header: tuple[str, int, str | None],
        stack: list[Section],
        sections: list[Section],
        clause_to_section: dict[str, Section],
        next_ordinal: dict[tuple[UUID | None, int], int],
        document_id: UUID,
    ) -> Section:
        """Create one Section from ``header`` (clause_id, level, title), popping
        the stack to its parent level, register it, push it."""
        clause_id, level, title = header
        while stack and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        key = (parent.id if parent else None, level)
        ordinal = next_ordinal[key]
        next_ordinal[key] += 1
        section = Section(
            id=uuid4(),
            document_id=document_id,
            parent_id=parent.id if parent else None,
            clause_id=clause_id,
            title=title,
            level=level,
            ordinal=ordinal,
        )
        sections.append(section)
        clause_to_section[clause_id] = section
        stack.append(section)
        return section

    def _open_chain(
        self,
        chain: tuple[list[tuple[str, int]], int, str],
        stack: list[Section],
        sections: list[Section],
        clause_to_section: dict[str, Section],
        text_map: dict[UUID, str],
        next_ordinal: dict[tuple[UUID | None, int], int],
        document_id: UUID,
        block_text: str,
    ) -> int:
        """Open a compound ``(a)(1)(i)`` chain as nested sub-sections and append
        the whole header line to the deepest section's text. Prefix clause_ids
        that already exist (e.g. ``(a)`` from an earlier line) are REUSED as the
        parent for the rest of the chain, so ``(a)(1)`` after ``(a)`` only
        creates the ``(1)``. Returns chars attached; 0 if the whole chain already
        exists (⇒ pure running header → orphan)."""
        labels_levels, first_parent_level, _trailing = chain
        first_level = labels_levels[0][1]
        while stack and stack[-1].level >= first_level:
            stack.pop()
        parent = next((s for s in reversed(stack) if s.level == first_parent_level), None)
        if parent is None:
            return 0  # validated in _match_paren_chain; defensive
        ancestor = parent
        parent_clause = parent.clause_id
        deepest = parent
        created_any = False
        for label, level in labels_levels:
            clause_id = f"{parent_clause}({label})"
            existing = clause_to_section.get(clause_id)
            if existing is not None:
                # Reuse the already-open prefix (e.g. (a)) and continue the chain
                # under it, so (a)(1) after (a) only creates the (1).
                deepest = existing
                ancestor = existing
                parent_clause = clause_id
                continue
            deepest = self._create_under(ancestor, clause_id, level, next_ordinal, document_id)
            sections.append(deepest)
            clause_to_section[clause_id] = deepest
            stack.append(deepest)
            parent_clause = clause_id
            ancestor = deepest
            created_any = True
        if not created_any:
            return 0  # whole chain already existed ⇒ running header
        _append_line(text_map, deepest.id, block_text)
        return len(block_text)

    @staticmethod
    def _create_under(
        parent: Section,
        clause_id: str,
        level: int,
        next_ordinal: dict[tuple[UUID | None, int], int],
        document_id: UUID,
    ) -> Section:
        """Create a child Section under an explicit parent (no stack pop) — used
        by the paren-chain walker where the parent is the previous chain node."""
        key = (parent.id, level)
        ordinal = next_ordinal[key]
        next_ordinal[key] += 1
        return Section(
            id=uuid4(),
            document_id=document_id,
            parent_id=parent.id,
            clause_id=clause_id,
            title=None,
            level=level,
            ordinal=ordinal,
        )

    # --- header classification -------------------------------------------

    @staticmethod
    def _match_paren_chain(
        text: str, stack: list[Section]
    ) -> tuple[list[tuple[str, int]], int, str] | None:
        """Match a leading ``"(a)(1)(i)"`` chain. Returns
        ``(labels_levels, first_parent_level, trailing)`` or None.

        The first label's (level, parent_level) is resolved by ancestor context
        (letter L3 / roman L5 disambiguation); subsequent labels must follow the
        strict CFR order (letter→digit→roman→uppercase), else the line is body.
        """
        m = _PAREN_CHAIN_RE.match(text)
        if m is None or not stack:
            return None
        labels = _LABEL_RE.findall(m.group(1))
        trailing = m.group(2)
        if not labels:
            return None
        first = CfrStructureDetector._child_level(labels[0], stack)
        if first is None:
            return None
        first_level, first_parent_level = first
        result: list[tuple[str, int]] = [(labels[0], first_level)]
        cur_level = first_level
        for lab in labels[1:]:
            nxt = CfrStructureDetector._next_cfr_level(cur_level, lab)
            if nxt is None:
                return None  # order broken → body text
            result.append((lab, nxt))
            cur_level = nxt
        return result, first_parent_level, trailing

    @staticmethod
    def _child_level(label: str, stack: list[Section]) -> tuple[int, int] | None:
        """Resolve ``(child_level, parent_level)`` for a single ``(label)`` token
        given the open-ancestor stack. Picks the NEAREST ancestor whose expected
        CFR child the label matches, so local nesting context wins: ``(i)`` inside
        an open ``(1)`` resolves to roman L5, while a letter ``(b)`` after
        ``(a)(1)`` pops back to the section level (L3). A lowercase token that is
        both a letter and a roman (i, v, x, ...) is roman when an L4 number is
        the immediate context, else a letter under the L2 section."""
        candidates: list[tuple[int, int]] = []
        if label.isdigit():
            candidates.append((4, 3))
        if len(label) == 1 and label.isupper():
            candidates.append((6, 5))
        if len(label) == 1 and label.islower():
            candidates.append((3, 2))
        if label in _ROMAN:
            candidates.append((5, 4))
        if not candidates:
            return None
        best: tuple[int, int] | None = None
        best_depth = len(stack)  # shallowest (smallest reversed-index) wins
        for child_level, parent_level in candidates:
            for idx, sect in enumerate(reversed(stack)):
                if sect.level == parent_level:
                    if idx < best_depth:
                        best_depth = idx
                        best = (child_level, parent_level)
                    break
        return best

    @staticmethod
    def _next_cfr_level(cur_level: int, label: str) -> int | None:
        """Next CFR level for a chained label after ``cur_level``."""
        if cur_level == 3 and label.isdigit():
            return 4
        if cur_level == 4 and label in _ROMAN:
            return 5
        if cur_level == 5 and len(label) == 1 and label.isupper():
            return 6
        return None


def _append_line(text_map: dict[UUID, str], section_id: UUID, line: str) -> None:
    """Append one parsed line to a section's text, healing print hyphenation.

    govinfo sets the CFR in justified two columns, so words break across lines
    with a soft hyphen ("within 90 sec-" / "onds") and the parser emits one block
    per line. 17.4% of far-25's lines end that way, which left 90% of chunks with
    mangled vocabulary: "seconds" became the tokens "sec" and "onds", so a lexical
    search for "seconds" could never match the clause that contains it, and the
    embedder saw broken words.

    Heal only a hyphen at a line END whose continuation starts LOWERCASE — that is
    a broken word. A hyphen inside a line is a real compound ("fail-safe",
    "damage-tolerance") and is untouched, as is a hyphen before an uppercase
    continuation. The residual risk is a genuine compound that happens to break at
    its hyphen ("fail-" / "safe" -> "failsafe"); that is rare, and far cheaper than
    losing 90% of the corpus's vocabulary to the alternative.
    """
    previous = text_map[section_id]
    body = previous.rstrip("\n")
    if body and _SOFT_HYPHEN_END_RE.search(body) and line[:1].islower():
        text_map[section_id] = f"{body[:-1]}{line}\n"
    else:
        text_map[section_id] = f"{previous}{line}\n"


def _modal_font_size(doc: ParsedDocument) -> float | None:
    """The document's dominant (modal) font size — the body-text size. Subpart
    headings must print larger than this (or bold) to count as headings; the
    table of contents repeats them at body size (see module docstring)."""
    sizes = Counter(
        block.font_size
        for page in doc.pages
        for block in page.blocks
        if block.font_size is not None and block.text.strip()
    )
    if not sizes:
        return None
    return sizes.most_common(1)[0][0]


def _is_display_heading(block: ParsedBlock, modal_size: float | None) -> bool:
    """Typography gate for display headings (Subpart lines): bold, or set
    larger than the modal body size."""
    if block.is_bold:
        return True
    return block.font_size is not None and modal_size is not None and block.font_size > modal_size


def make_cfr_structure_detector() -> CfrStructureDetector:
    """Container factory (spec §4 wiring seam)."""
    return CfrStructureDetector()
