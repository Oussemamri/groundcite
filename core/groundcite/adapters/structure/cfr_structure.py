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
"""

from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID, uuid4

from groundcite.domain.entities import ParsedDocument, Section
from groundcite.ports.protocols import SectionTextMap, StructureDetector

# Header regexes (operate on a single block's text, at line start).
_SUBPART_RE = re.compile(r"^Subpart\s+([A-Z])\s*[—–\-]\s*(.+)$")
_SECTION_RE = re.compile(r"^§\s*(\d+(?:\.\d+)*)\s*(.*)$")
# A compound "(a)(1)(i)" chain of leading paren groups, followed by body text.
# The inner [^)]{1,8} also rejects "(see paragraph ...)" mid-text cross-refs
# whose label is a long sentence, so they never parse as headers.
_PAREN_CHAIN_RE = re.compile(r"^((?:\([^)]{1,8}\))+)\s*(.*)$")
_LABEL_RE = re.compile(r"\(([^)]{1,8})\)")
_PURE_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")

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

        for page in doc.pages:
            for block in page.blocks:
                text = block.text.rstrip()
                if not text:
                    continue

                # Recognized noise (page numbers / repeated running headers) is
                # excluded from the 90% accounting: it is structural we
                # deliberately dropped, not "orphan text we couldn't account for".
                if _PURE_PAGE_NUM_RE.match(text):
                    continue

                subpart = _SUBPART_RE.match(text)
                section_m = _SECTION_RE.match(text)
                if section_m is not None and not block.is_bold:
                    # Not typographically a heading (see module docstring):
                    # bare number ⇒ page running head (recognized noise),
                    # trailing prose ⇒ wrapped in-body cross-reference (body).
                    if section_m.group(2).strip() in ("", "."):
                        continue
                    section_m = None
                chain = self._match_paren_chain(text, stack)

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
                    text_map[sections[-1].id] += text + "\n"
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
                    text_map[sections[-1].id] += text + "\n"
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
                    text_map[stack[-1].id] += text + "\n"
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
        text_map[deepest.id] += block_text + "\n"
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


def make_cfr_structure_detector() -> CfrStructureDetector:
    """Container factory (spec §4 wiring seam)."""
    return CfrStructureDetector()
