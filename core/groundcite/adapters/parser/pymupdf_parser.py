"""Implements DocumentParser (spec §6 step 1, lite/CI path): PyMuPDF text
extraction with page numbers plus per-block font-size/bold signals.

PyMuPDF (``fitz``) is an optional dependency — ``uv sync --extra pdf``. The import
is lazy so importing this module never requires the package (CI installs no
extras; tests use a fake parser). This is the air-gapped fast path; the default
parser is Docling (spec §6 step 1), added in a later session. Both adapters share
the DocumentParser port contract test (spec §6 step 1) so neither can drift.
"""

from __future__ import annotations

from pathlib import Path

from groundcite.domain.entities import ParsedBlock, ParsedDocument, ParsedPage
from groundcite.ports.protocols import DocumentParser

# PyMuPDF is an optional extra; keep it out of module-level imports so CI (which
# installs no extras) and the unit suite (which uses a fake parser) never need it.
try:  # pragma: no cover - exercised only when the pdf extra is installed
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None


class PyMuPDFParser(DocumentParser):
    """Text-layer PDF extraction via PyMuPDF (spec §6 step 1)."""

    def parse(self, pdf_path: Path) -> ParsedDocument:
        if fitz is None:  # pragma: no cover - guarded by the import above
            raise RuntimeError(
                "PyMuPDF (fitz) is not installed. Install the pdf extra: `uv sync --extra pdf`."
            )
        pages: list[ParsedPage] = []
        with fitz.open(str(pdf_path)) as doc:
            for page_index, page in enumerate(doc):
                page_number = page_index + 1
                blocks: list[ParsedBlock] = []
                # "dict" gives blocks → lines → spans with size + flags, which is
                # how we recover the font-size/bold signals structure detection
                # needs (spec §6 step 1).
                page_dict = page.get_text("dict")
                for block in page_dict.get("blocks", ()):
                    if block.get("type") != 0:  # 0 = text; skip images/etc.
                        continue
                    for line in block.get("lines", ()):
                        spans = line.get("spans", ())
                        if not spans:
                            continue
                        text = "".join(span.get("text", "") for span in spans)
                        text = text.rstrip()
                        if not text:
                            continue
                        # PyMuPDF span flags: bit 2**4 is bold.
                        max_size = round(max(float(s.get("size", 0.0)) for s in spans), 1)
                        is_bold = any(bool(s.get("flags", 0) & (1 << 4)) for s in spans)
                        blocks.append(
                            ParsedBlock(
                                text=text,
                                page_number=page_number,
                                font_size=max_size,
                                is_bold=is_bold,
                            )
                        )
                pages.append(ParsedPage(page_number=page_number, blocks=tuple(blocks)))
        return ParsedDocument(pages=tuple(pages))


def make_pymupdf_parser() -> PyMuPDFParser:
    """Container factory (spec §4 wiring seam)."""
    return PyMuPDFParser()
