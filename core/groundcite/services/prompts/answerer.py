"""Answerer prompts for the generation contract (spec §7; AD-4 Build).

Spec §11.1 puts ALL prompts under Build (never buy, never a framework). This
module holds the system prompt constants and the context renderer that tags each
chunk as ``<chunk id="…" clause="…">…</chunk>`` so the model can cite verbatim
chunk ids back (Gate B then checks those ids exist in the provided set, AD-5).

Mapping convention (AD-4, recorded here as the single source of truth for the
``ask()`` driver — this module only shapes the model's behaviour, it does not
interpret ``insufficient``):
- ``insufficient: true``  → ABSTAIN(reason=WEAK_RETRIEVAL). The model confirming
  the retrieved context cannot answer is a RETRIEVAL-STRENGTH verdict.
- citation-validity failure after the repair retry → ABSTAIN(reason=UNCITED).
  WEAK_RETRIEVAL is reserved for the retrieval verdict; UNCITED for citation-validity.

Gate B paragraph rule (spec §7 step 6): "≥1 citation per answer paragraph". The
JSON contract has no paragraph anchor on a citation, so the driver checks the
pragmatic, defensible reading: at least as many citations as non-empty
paragraphs (``answer_md`` split on blank lines), and every cited chunk_id in the
provided context set. A paragraph may carry more than one citation; it may not
carry none. Recorded here so the prompt and Gate B agree on the rule's meaning.
"""

from __future__ import annotations

from collections.abc import Sequence

from groundcite.domain.results import RetrievedChunk

SYSTEM_PROMPT = """\
You are GroundCite, a grounded Q&A engine over aerospace engineering standards.
You answer a user's Ask STRICTLY from the provided context chunks.

Hard rules:
1. Answer ONLY from the provided <chunk> blocks. Do not use outside knowledge, \
and do not infer facts the chunks do not state.
2. Every factual sentence in your answer must be supported by at least one \
citation to a chunk id from the provided context. Cite by the exact value of the \
chunk's id attribute.
3. A cited chunk_id MUST be one of the id attributes given in the context. Never \
invent ids.
4. Every answer paragraph (text separated by a blank line) must carry at least \
one citation; a paragraph with facts and no citation is a violation.
5. Write clause identifiers VERBATIM in the § form shown in the chunk's clause \
attribute, e.g. §25.1309(b) — never paraphrase or shorten a clause number.
6. If the provided chunks do not contain the answer, set "insufficient": true, \
put a single short sentence in "answer_md" saying the context is insufficient, \
and return an empty "citations" list. Do not guess.
7. Answer in the SAME natural language as the user's question.
8. Output ONLY a JSON object with exactly these keys:
   {"answer_md": string, "citations": [{"chunk_id": string, "claim": string}], \
"insufficient": boolean}
   Do not wrap the JSON in prose. A ```json code fence is acceptable but nothing \
else may surround it.
9. "claim" is a short verbatim phrase from the cited chunk that grounds the \
sentence(s) it supports.
"""

_LANGUAGE_HINT = {"de": "Answer in German.", "en": "Answer in English."}


def render_context(chunks: Sequence[RetrievedChunk]) -> str:
    """Render chunks as ``<chunk id="…" clause="…">…</chunk>`` blocks (spec §7).

    Each chunk_id appears EXACTLY once (table-tested). The id is the chunk's UUID
    string — the model cites it back and Gate B checks membership in this set.
    """
    parts: list[str] = []
    for c in chunks:
        parts.append(f'<chunk id="{c.chunk_id}" clause="{c.clause_path}">\n{c.content}\n</chunk>')
    return "\n\n".join(parts)


def chunk_id_set(chunks: Sequence[RetrievedChunk]) -> frozenset[str]:
    """The set of valid chunk id strings the model may cite (Gate B's context set)."""
    return frozenset(str(c.chunk_id) for c in chunks)


def render_user(question: str, chunks: Sequence[RetrievedChunk], language: str = "en") -> str:
    """The user turn: context chunks + the question + a language directive."""
    hint = _LANGUAGE_HINT.get(language, _LANGUAGE_HINT["en"])
    return (
        f"Context:\n{render_context(chunks)}\n\n"
        f"Question: {question}\n\n"
        f"{hint}\n\n"
        "Emit ONLY the JSON answer object described in the system rules."
    )


def render_repair(
    question: str,
    chunks: Sequence[RetrievedChunk],
    language: str,
    critique: str,
) -> str:
    """Repair-retry user turn (AD-4/AD-5): re-provide the context, name the exact
    defect, and ask for ONLY the corrected JSON. One retry — a second failure
    abstains (UNCITED). The driver composes ``critique`` (parse error detail OR
    the invalid ids / uncited-paragraph counts); this module owns the wrapper.
    """
    hint = _LANGUAGE_HINT.get(language, _LANGUAGE_HINT["en"])
    return (
        f"Context:\n{render_context(chunks)}\n\n"
        f"Question: {question}\n\n"
        f"{hint}\n\n"
        f"Your previous answer was not usable:\n{critique}\n\n"
        "Re-emit ONLY a corrected JSON answer object following ALL the system rules. "
        "Cite only chunk ids present in the context above."
    )
