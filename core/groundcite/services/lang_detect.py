"""Language detection for the ask pipeline (spec §7 step 0: language + clause-ID
detection) — a DE/EN stopword-ratio heuristic.

Spec §11.1 keeps this OUT of the buy column (no langdetect/lingua/fasttext): a
binary DE/EN decision over one short question does not justify a dependency
(look-outside survey, reject). The corpus is English; the question may be German
(§3.1 goal 7). A stopword-ratio check is ~15 lines, deterministic, table-tested
against the committed golden suites, and needs no model.

Hand-rolled on purpose (§11.1 Build). Tokenizes the question, counts tokens in a
small German vs English function-word list, and returns the language with the
higher count; ties break to English (the corpus language). The golden-suite
table test (Phase 3 verify) loads german.jsonl + core.jsonl read-only (rule 13)
and asserts 10/10 DE + 10/10 EN.
"""

from __future__ import annotations

import re

_LANG_TOKEN = re.compile(r"\b[\wäöüß]+\b", re.UNICODE)

# Compact function-word lists. German drops the few token shapes that collide
# with English clause numbers; overlap (e.g. "was") is harmless — the SIDE with
# more stopwords wins, and German questions are saturated with der/die/das/und.
_GERMAN = {
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einer",
    "eines",
    "und",
    "oder",
    "ist",
    "sind",
    "war",
    "sein",
    "werden",
    "wird",
    "muss",
    "müssen",
    "kann",
    "darf",
    "soll",
    "nicht",
    "kein",
    "keine",
    "auf",
    "für",
    "von",
    "mit",
    "zur",
    "zu",
    "an",
    "in",
    "bei",
    "nach",
    "über",
    "unter",
    "wie",
    "was",
    "welche",
    "welchen",
    "welches",
    "wann",
    "wenn",
    "dass",
    "daß",
    "auch",
    "noch",
    "aber",
    "nur",
}
_ENGLISH = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "must",
    "shall",
    "should",
    "can",
    "may",
    "does",
    "do",
    "did",
    "what",
    "which",
    "how",
    "when",
    "that",
    "this",
    "these",
    "those",
    "not",
    "no",
    "any",
    "all",
    "each",
    "it",
    "they",
    "their",
    "if",
    "than",
}


def detect_language(text: str) -> str:
    """Return ``"de"`` or ``"en"`` for ``text`` (spec §7 step 0). Ties → ``"en"``."""
    toks = [t.lower() for t in _LANG_TOKEN.findall(text)]
    de = sum(1 for t in toks if t in _GERMAN)
    en = sum(1 for t in toks if t in _ENGLISH)
    return "de" if de > en else "en"
