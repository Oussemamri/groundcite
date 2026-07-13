"""Clause-ID detection — spec §7 step 0 ("language + clause-ID detection").

Pure functions, zero I/O. Recovers the clause identifiers a question refers to
("What does §25.1309(b) require?" → ``25.1309(b)``) so the ask pipeline can fire
the exact-match fast path (§7 step 1c) and inject that clause at rank 1.

Detection is deliberately CONSERVATIVE: a false positive sends a wrong clause to
rank 1, which is worse than no fast path at all in a domain where a wrong citation
is worse than no answer (§1). So we require a clause-shaped token — a dotted
number (``25.1309``), optionally with CFR paragraph suffixes (``(b)``, ``(b)(2)``,
``(b)(2)(i)``) — and we do NOT treat bare integers, years, or decimals inside
prose ("1.5 g", "in 2024") as clauses: a clause needs the § marker, a "part/
section" cue word, or CFR-style paragraph suffixes to qualify.

Language detection is intentionally NOT implemented here. Spec §7 step 0 pairs it
with clause detection, but nothing in the Week-2 retrieval path consumes it
(bge-m3 is multilingual, and the lexical index is english-only by construction);
the answerer needs it in Week 3, which is where it belongs. Building it now would
be a knob nobody turns (rule 0: simplicity).
"""

from __future__ import annotations

import re

# A dotted clause number: 25.1309, 5.4.2.1 — at least one dot, digits throughout.
_NUMBER = r"\d+(?:\.\d+)+"
# CFR paragraph suffixes that may trail a clause number: (a), (b)(2), (b)(2)(i).
_SUFFIXES = r"(?:\([0-9A-Za-z]{1,4}\))*"

# Strong signals — a dotted number is a clause when it is marked as one:
#   "§ 25.1309(b)"  |  "section 25.1309"  |  "part 25.1309"  |  "clause 5.4.2.1"
_MARKED_RE = re.compile(
    rf"(?:§+\s*|\b(?:sections?|parts?|clauses?|paragraphs?|abschnitt|absatz)\s+)"
    rf"({_NUMBER}{_SUFFIXES})",
    re.IGNORECASE,
)
# A dotted number carrying CFR paragraph suffixes is self-identifying:
#   "25.1309(b)" needs no § to be unambiguous.
_SUFFIXED_RE = re.compile(rf"\b({_NUMBER}(?:\([0-9A-Za-z]{{1,4}}\))+)")
# ECSS-style standard codes: ECSS-E-ST-40C. Captured so a future ECSS corpus's
# clause paths resolve; harmless on a CFR-only corpus.
_ECSS_RE = re.compile(r"\b(ECSS-[A-Z]-ST-\d+[A-Z]?(?:-\d+[A-Z]?)?)\b", re.IGNORECASE)


def detect_clause_ids(question: str) -> list[str]:
    """Clause ids referenced by ``question``, in first-seen order, deduplicated.

    Returns [] when the question names no clause — the common case for semantic
    questions, where the fast path simply does not fire.
    """
    found: list[str] = []
    for pattern in (_MARKED_RE, _SUFFIXED_RE, _ECSS_RE):
        for match in pattern.finditer(question):
            clause = _normalize(match.group(1))
            if clause and clause not in found:
                found.append(clause)
    return found


def _normalize(raw: str) -> str:
    """Strip trailing punctuation the regex may have swept up ("25.1309." → "25.1309")."""
    return raw.strip().rstrip(".,;:")
