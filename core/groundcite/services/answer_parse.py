"""Answer-string parsing for the generation contract (spec §7; AD-4 Build).

The answerer emits JSON ``{"answer_md": str, "citations": [...], "insufficient": bool}``
(spec §7 contract). The parser is hand-rolled (no instructor/outlines/pydantic-ai —
that is the §7 portfolio piece), tolerant of code fences and trailing prose, and
NEVER raises on bad input: a shape/JSON failure returns ``ParseError`` so the
``ask()`` driver can run the ONE repair retry (AD-4) and, on a second failure,
ABSTAIN(reason=UNCITED).

Convention (AD-4) carried by the ``ask()`` driver, NOT this parser:
- ``insufficient: true`` → ABSTAIN(reason=WEAK_RETRIEVAL). The model confirming
  the retrieved context cannot answer is a *retrieval-strength* verdict.
- a citation-validity failure after the repair retry → ABSTAIN(reason=UNCITED).
  WEAK_RETRIEVAL is reserved for the retrieval verdict, UNCITED for citation-validity.

The parser is deliberately pre-Gate-B: it validates the JSON SHAPE only. Whether
the cited ``chunk_id`` values actually exist in the provided context set, and the
"≥1 citation per answer paragraph" rule (spec §7 step 6), is Gate B — checked by
the ``ask()`` driver against the provided context, because the parser does not
know that set.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# Matches a fenced block ```...``` (optionally ```json) anywhere; non-greedy.
_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


@dataclass(frozen=True)
class RawCitation:
    """A citation as the model emitted it — chunk_id is a STRING here (the value
    of the ``id`` attribute on the ``<chunk>`` the prompt provided), validated as
    a real Chunk id by Gate B, not by the parser."""

    chunk_id: str
    claim: str = ""


@dataclass(frozen=True)
class ParsedAnswer:
    """Successful parse of the §7 contract JSON."""

    answer_md: str
    citations: tuple[RawCitation, ...]
    insufficient: bool


@dataclass(frozen=True)
class ParseError:
    """A structured parse failure for the repair-retry prompt (AD-4). Never raised."""

    detail: str
    raw: str


def parse_answer(text: str) -> ParsedAnswer | ParseError:
    """Parse the answerer's JSON output (fence-tolerant) → ParsedAnswer | ParseError."""
    body = _strip_fence(text.strip())
    obj = _load_object(body)
    if obj is None:
        # Fall back to extracting the first balanced {...} object (trailing prose).
        cand = _extract_first_object(body) or _extract_first_object(text)
        obj = _load_object(cand) if cand else None
    if obj is None:
        return ParseError(
            detail=(
                "Output is not valid JSON. Emit ONLY the JSON object "
                '{"answer_md": str, "citations": [{"chunk_id": str, "claim": str}], '
                '"insufficient": bool}.'
            ),
            raw=text,
        )
    if not isinstance(obj, dict):
        return ParseError(detail="Top-level JSON must be an object {...}.", raw=text)

    answer_md = obj.get("answer_md")
    if not isinstance(answer_md, str) or not answer_md.strip():
        return ParseError(detail="'answer_md' must be a non-empty string.", raw=text)

    insufficient = obj.get("insufficient", False)
    if not isinstance(insufficient, bool):
        return ParseError(detail="'insufficient' must be a boolean.", raw=text)

    cits_raw = obj.get("citations", [])
    if not isinstance(cits_raw, list):
        return ParseError(detail="'citations' must be a list of {chunk_id, claim}.", raw=text)

    cits: list[RawCitation] = []
    for i, c in enumerate(cits_raw):
        if not isinstance(c, dict):
            return ParseError(detail=f"citations[{i}] must be an object.", raw=text)
        chunk_id = c.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            return ParseError(
                detail=f"citations[{i}].chunk_id must be a non-empty string.", raw=text
            )
        claim = c.get("claim", "")
        if not isinstance(claim, str):
            return ParseError(detail=f"citations[{i}].claim must be a string.", raw=text)
        cits.append(RawCitation(chunk_id=chunk_id.strip(), claim=claim))

    return ParsedAnswer(answer_md=answer_md, citations=tuple(cits), insufficient=insufficient)


def _strip_fence(body: str) -> str:
    """Return the content of the first ``` fenced block, else ``body`` unchanged."""
    m = _FENCE.search(body)
    return m.group(1) if m else body


def _load_object(s: str) -> object | None:
    try:
        loaded: object = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    return loaded


def _extract_first_object(s: str) -> str | None:
    """First balanced ``{...}`` substring respecting strings/escapes, or None."""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None
