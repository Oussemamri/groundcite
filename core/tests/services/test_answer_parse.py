"""Unit tests for answer_parse.parse_answer (spec §7; AD-4). Table-driven.

Covers clean JSON / fenced JSON / trailing prose / every malformed shape — the
parser must return a structured ParseError and NEVER raise.
"""

from __future__ import annotations

import json

import pytest

from groundcite.services.answer_parse import ParseError, parse_answer

_CLEAN = json.dumps(
    {
        "answer_md": "Paragraph one.\n\nParagraph two.",
        "citations": [
            {"chunk_id": "c1", "claim": "fact one"},
            {"chunk_id": "c2", "claim": "fact two"},
        ],
        "insufficient": False,
    }
)


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("clean", _CLEAN),
        ("fenced-json", "```json\n" + _CLEAN + "\n```"),
        ("fenced-bare", "```\n" + _CLEAN + "\n```"),
        ("trailing-prose", _CLEAN + "\n\nThat is the answer."),
        ("fenced-then-prose", "```json\n" + _CLEAN + "\n```\n\nExplanation here."),
    ],
)
def test_parses_valid_variants(label: str, text: str) -> None:
    res = parse_answer(text)
    assert not isinstance(res, ParseError), f"{label}: should parse, not error"
    assert res.answer_md == "Paragraph one.\n\nParagraph two."  # type: ignore[union-attr]
    assert res.insufficient is False  # type: ignore[union-attr]
    assert [c.chunk_id for c in res.citations] == ["c1", "c2"]  # type: ignore[union-attr]
    assert [c.claim for c in res.citations] == ["fact one", "fact two"]  # type: ignore[union-attr]


def test_insufficient_true_with_empty_citations() -> None:
    res = parse_answer(
        '{"answer_md": "context is insufficient.", "citations": [], "insufficient": true}'
    )
    assert not isinstance(res, ParseError)
    assert res.insufficient is True  # type: ignore[union-attr]
    assert res.citations == ()  # type: ignore[union-attr]


_MALFORMED = [
    ("not json at all", "I think the answer is 42.", "JSON"),
    ("missing answer_md", '{"citations": [], "insufficient": false}', "answer_md"),
    (
        "answer_md not string",
        '{"answer_md": 5, "citations": [], "insufficient": false}',
        "answer_md",
    ),
    (
        "insufficient not bool",
        '{"answer_md": "x", "citations": [], "insufficient": "no"}',
        "boolean",
    ),
    ("citations not list", '{"answer_md": "x", "citations": {}, "insufficient": false}', "list"),
    (
        "citation not object",
        '{"answer_md": "x", "citations": ["oops"], "insufficient": false}',
        "object",
    ),
    (
        "missing chunk_id",
        '{"answer_md": "x", "citations": [{"claim": "k"}], "insufficient": false}',
        "chunk_id",
    ),
    (
        "empty chunk_id",
        '{"answer_md": "x", "citations": [{"chunk_id": "  "}], "insufficient": false}',
        "chunk_id",
    ),
    (
        "claim not string",
        '{"answer_md": "x", "citations": [{"chunk_id": "c1", "claim": 5}], "insufficient": false}',
        "claim",
    ),
    ("top-level array", "[]", "object"),
]


@pytest.mark.parametrize(("label", "text", "detail_contains"), _MALFORMED)
def test_malformed_returns_error_and_never_raises(
    label: str, text: str, detail_contains: str
) -> None:
    res = parse_answer(text)
    assert isinstance(res, ParseError), f"{label}: must return ParseError, not raise or succeed"
    assert detail_contains.lower() in res.detail.lower()
    assert res.raw == text, "raw preserved for the repair prompt"


def test_extracts_first_object_amongst_surrounding_prose() -> None:
    # leading prose then JSON then trailing prose — the first balanced object is used
    res = parse_answer("Sure! Here is the answer:\n" + _CLEAN + "\nHope it helps.")
    assert not isinstance(res, ParseError)
    assert res.citations[0].chunk_id == "c1"  # type: ignore[union-attr]
