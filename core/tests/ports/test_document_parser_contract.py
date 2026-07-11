"""Shared DocumentParser port contract test (spec §6 step 1).

Both the PyMuPDF (lite/CI) and Docling (default) adapters MUST satisfy this
contract so a second adapter can never silently drift from the first (spec §6
step 1). The contract is independent of any real corpus: it builds a tiny
text-layer PDF in a tmp file and asserts the parser returns a well-formed
``ParsedDocument`` with page numbers and font-size/bold signals intact.

A new parser adapter adds itself to ``_PARSERS`` and inherits every test here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from groundcite.domain.entities import ParsedDocument
from groundcite.ports.protocols import DocumentParser

# Adapters under contract. Populated lazily: PyMuPDF is an optional extra, so we
# only exercise it when installed (CI installs no extras → this list is empty →
# the contract tests skip). Docling lands in a later session and will append here.
_PARSERS: list[DocumentParser] = []


def _try_register_pymupdf() -> None:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return
    from groundcite.adapters.parser.pymupdf_parser import PyMuPDFParser

    _PARSERS.append(PyMuPDFParser())
    _ = fitz  # presence confirms the extra is installed


_try_register_pymupdf()


def _write_tiny_pdf(path: Path) -> None:
    """Write a 2-page text-layer PDF with a bold heading and a body line."""
    import fitz  # type: ignore[import-not-found]

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Section One", fontsize=14, fontname="Helvetica-Bold")
    p1.insert_text((72, 100), "Body of section one.", fontsize=11, fontname="Helvetica")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Section Two", fontsize=14, fontname="Helvetica-Bold")
    doc.save(str(path))
    doc.close()


pytestmark = pytest.mark.skipif(
    not _PARSERS, reason="no DocumentParser adapter installed (install the pdf extra)"
)


@pytest.fixture(params=_PARSERS, ids=lambda p: type(p).__name__)
def parser(request: pytest.FixtureRequest) -> DocumentParser:
    return request.param


@pytest.fixture
def tiny_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "tiny.pdf"
    _write_tiny_pdf(pdf)
    return pdf


def test_returns_parsed_document(parser: DocumentParser, tiny_pdf: Path) -> None:
    result = parser.parse(tiny_pdf)
    assert isinstance(result, ParsedDocument)
    assert len(result.pages) == 2


def test_page_numbers_are_one_indexed(parser: DocumentParser, tiny_pdf: Path) -> None:
    result = parser.parse(tiny_pdf)
    assert [p.page_number for p in result.pages] == [1, 2]


def test_blocks_carry_font_size_and_bold(parser: DocumentParser, tiny_pdf: Path) -> None:
    result = parser.parse(tiny_pdf)
    page1 = result.pages[0]
    blocks = page1.blocks
    assert blocks, "page 1 must yield text blocks"
    sizes = {b.font_size for b in blocks}
    bolds = {b.is_bold for b in blocks}
    # The tiny PDF has a bold 14pt heading and a non-bold 11pt body, so the parser
    # must distinguish both font size and the bold signal (spec §6 step 1).
    assert 14.0 in sizes or 13.0 in sizes, f"expected the 14pt heading font size, got {sizes}"
    assert True in bolds, f"expected a bold block, got bold={bolds}"
    assert False in bolds, f"expected a non-bold body block, got bold={bolds}"


def test_blocks_preserve_page_number(parser: DocumentParser, tiny_pdf: Path) -> None:
    result = parser.parse(tiny_pdf)
    for page in result.pages:
        for block in page.blocks:
            assert block.page_number == page.page_number
