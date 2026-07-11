"""Implements Chunker (spec §6 step 3): clause-aware chunking with breadcrumb
headers, leaf-merge, and sentence-boundary splitting.

Consumes ``(doc, sections, section_text, count_tokens)`` (spec §6 binding
signature / §6.1 #1). The chunker NEVER imports an embedding library directly —
``count_tokens`` is injected (the configured embedder's own tokenizer, wired via
container.py) so chunk-size limits stay accurate for whichever embedder is
active (§6.1 #4).

Rules (spec §6 step 3):
- One chunk per leaf clause when ≤ ~450 tokens (``count_tokens``); long clauses
  split on sentence boundaries with a 60-token overlap.
- A leaf with no children and ``token_count < MIN_LEAF_TOKENS`` (default 64,
  from config) merges UP into its parent's chunk ("merge tiny sibling clauses").
- A breadcrumb header is prepended to every chunk's ``content``:
  ``[<standard_code> §<clause_id> — title > chain > of > ancestors]`` — the
  single retrieval trick (§6 step 3).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from uuid import UUID, uuid4

from groundcite.domain.entities import Chunk, ParsedDocument, Section
from groundcite.ports.protocols import SectionTextMap

# Spec §6 step 3 sizing. Kept as adapter defaults (not env) since the spec fixes
# them; only MIN_LEAF_TOKENS is configurable (§6.1 #5, via constructor/config).
_MAX_CHUNK_TOKENS = 450
_OVERLAP_TOKENS = 60

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class ClauseChunker:
    """Clause-aware chunker implementing the Chunker port (spec §6 step 3)."""

    def __init__(self, min_leaf_tokens: int = 64) -> None:
        self._min_leaf_tokens = min_leaf_tokens

    def chunk(
        self,
        doc: ParsedDocument,
        sections: Sequence[Section],
        section_text: SectionTextMap,
        count_tokens: Callable[[str], int],
    ) -> list[Chunk]:
        standard_code = doc.standard_code or ""
        by_id: dict[UUID, Section] = {s.id: s for s in sections}
        children: dict[UUID | None, list[Section]] = {}
        for s in sections:
            children.setdefault(s.parent_id, []).append(s)
        for kids in children.values():
            kids.sort(key=lambda s: s.ordinal)

        emitters: list[tuple[Section, list[str]]] = []

        def process(node: Section) -> str | None:
            """Post-order: return text to LIFT to the parent (tiny leaf /
            empty subtree), else None. Emitters are appended (node, [texts])
            as a side effect."""
            kids = children.get(node.id, [])
            own = section_text.get(node.id, "") or ""
            if not kids:
                # leaf
                if own and count_tokens(own) < self._min_leaf_tokens:
                    return own  # tiny leaf → lift/merge up to parent
                if own:
                    emitters.append((node, [own]))
                return None
            # internal node
            start = len(emitters)
            lifts: list[str] = []
            for kid in kids:
                lift = process(kid)
                if lift:
                    lifts.append(lift)
            merged = "\n".join(x for x in lifts if x)
            new_emitters = emitters[start:]
            if new_emitters:
                if merged:
                    # Tiny siblings merge UP to this parent as its own chunk
                    # (intro + merged); big siblings stay standalone.
                    payload = (own + "\n" + merged).strip() if own else merged
                    if payload:
                        emitters.insert(start, (node, [payload]))
                elif own:
                    # No tiny merge: prepend this intro to the first big
                    # descendant's chunk so a section's lead-in rides with its
                    # first paragraph.
                    _, first_texts = new_emitters[0]
                    if first_texts:
                        first_texts[0] = (own + "\n" + first_texts[0]).strip()
                return None
            # no standalone descendants
            combined = "\n".join(x for x in (own, merged) if x)
            if combined:
                emitters.append((node, [combined]))
                return None
            return ""  # nothing to emit, nothing to lift

        for root in children.get(None, []):
            lift = process(root)
            if lift:
                # A tiny leaf at the document root has no parent to merge up
                # into — emit it as its own chunk so its text is not lost.
                emitters.append((root, [lift]))

        chunks: list[Chunk] = []
        document_id = doc.document_id
        if document_id is None:
            return chunks  # IngestionService must enrich document_id first (spec §6)
        for section, texts in emitters:
            clause_path = _clause_path(standard_code, section.clause_id)
            breadcrumb = _breadcrumb(standard_code, section, by_id)
            for body in texts:
                for piece in _split(body, count_tokens, _MAX_CHUNK_TOKENS, _OVERLAP_TOKENS):
                    content = f"{breadcrumb}\n{piece.strip()}" if breadcrumb else piece.strip()
                    chunks.append(
                        Chunk(
                            id=uuid4(),
                            document_id=document_id,
                            section_id=section.id,
                            clause_path=clause_path,
                            content=content,
                            token_count=count_tokens(content),
                        )
                    )
        return chunks


def _clause_path(standard_code: str, clause_id: str) -> str:
    """``<standard_code> §<clause_id>`` for section-style ids (start with a
    digit, e.g. '25.1309(a)(1)'), else ``<standard_code> <clause_id>`` (e.g.
    'Subpart B'). Matches spec §5 'ECSS-E-ST-40C §5.4.2.1'."""
    prefix = "§" if clause_id[:1].isdigit() else ""
    return f"{standard_code} {prefix}{clause_id}".strip()


def _breadcrumb(standard_code: str, section: Section, by_id: dict[UUID, Section]) -> str:
    """Build the chunk breadcrumb header (spec §6 step 3 example):
    ``[<clause_path> — Title > chain > … > leaf title]`` walking root→self,
    skipping nodes with no title."""
    titles: list[str] = []
    node: Section | None = section
    while node is not None:
        if node.title:
            titles.append(node.title)
        node = by_id.get(node.parent_id) if node.parent_id is not None else None
    titles.reverse()
    clause_path = _clause_path(standard_code, section.clause_id)
    if titles:
        return f"[{clause_path} — {' > '.join(titles)}]"
    return f"[{clause_path}]"


def _split(
    text: str,
    count_tokens: Callable[[str], int],
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Sentence-boundary chunking: accumulate sentences into ≤ ``max_tokens``
    chunks with an ``overlap_tokens`` carry from the end of each closed chunk."""
    text = text.strip()
    if not text:
        return []
    if count_tokens(text) <= max_tokens:
        return [text]
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return [text]
    pieces: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for sent in sentences:
        st = count_tokens(sent)
        if cur and cur_tokens + st > max_tokens:
            pieces.append(" ".join(cur))
            # overlap: carry trailing sentences totalling ≥ overlap_tokens.
            ov: list[str] = []
            ov_tokens = 0
            for s2 in reversed(cur):
                if ov_tokens >= overlap_tokens:
                    break
                ov.insert(0, s2)
                ov_tokens += count_tokens(s2)
            cur = ov
            cur_tokens = ov_tokens
        cur.append(sent)
        cur_tokens += st
    if cur:
        pieces.append(" ".join(cur))
    return pieces or [text]


def make_clause_chunker(min_leaf_tokens: int = 64) -> ClauseChunker:
    """Container factory (spec §4 wiring seam)."""
    return ClauseChunker(min_leaf_tokens=min_leaf_tokens)
