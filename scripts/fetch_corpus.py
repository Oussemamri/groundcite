"""Download the demo corpus from official sources (spec §13, task 2a).

PDFs never enter git (size + license, spec §13). This script fetches from an
official source into a git-ignored ``corpus/`` directory. Default corpus:
14 CFR Part 25 (US public domain) from govinfo.gov — the annual CFR is published
by VOLUME, so we download Title 14 Vol 1 (the redistributable unit that contains
Part 25) then crop to Part 25's pages to ingest only that part honestly.

``documents.license_note`` ("US public domain") is set at INGEST time (doc_meta),
not here — fetch only downloads. Run from the ``core/`` package:

    uv run python ../scripts/fetch_corpus.py            # default: FAR Part 25

Requires the optional ``pdf`` extra (PyMuPDF) for the crop step.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

# Official redistributable CFR volume containing Part 25 (spec §13).
# govinfo publishes the annual CFR by volume; Title 14 Vol 1 holds Parts 1-59.
_DEFAULT_URL = (
    "https://www.govinfo.gov/content/pkg/CFR-2024-title14-vol1/pdf/CFR-2024-title14-vol1.pdf"
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VOL_PATH = _REPO_ROOT / "corpus" / "14cfr_vol1.pdf"
_PART25_PATH = _REPO_ROOT / "corpus" / "far-25.pdf"

_PART_HEADING_RE = re.compile(r"^PART\s+(\d+)\b")


def main() -> int:
    volume_path = _download(_DEFAULT_URL, _VOL_PATH)
    part_path = _crop_part25(volume_path, _PART25_PATH)
    print(f"\nOK: 14 CFR Part 25 PDF ready at: {part_path}")
    print("License: US public domain (FAA). Set documents.license_note at ingest.")
    return 0


def _download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"skip download (cached): {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url} -> {dest} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "groundcite/fetch_corpus"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
    print(f"downloaded {dest.stat().st_size} bytes")
    return dest


def _crop_part25(volume_path: Path, dest: Path) -> Path:
    """Crop the CFR volume to Part 25's pages [start_25, start_next_part)."""
    try:
        import fitz  # type: ignore
    except ImportError:
        print(
            "ERROR: PyMuPDF (fitz) is required to crop Part 25. "
            "Run `uv sync --extra pdf` and retry.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    doc = fitz.open(str(volume_path))
    start_25: int | None = None
    next_part_start: int | None = None
    for page_index in range(doc.page_count):
        spans = [
            span.get("text", "")
            for block in doc[page_index].get_text("dict").get("blocks", [])
            if block.get("type") == 0
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ]
        for text in spans:
            m = _PART_HEADING_RE.match(text.strip())
            if m is None:
                continue
            part_no = int(m.group(1))
            if part_no == 25 and start_25 is None:
                start_25 = page_index
            elif start_25 is not None and next_part_start is None and part_no > 25:
                next_part_start = page_index
                break
        if next_part_start is not None:
            break

    if start_25 is None:
        print("ERROR: could not locate 'PART 25' heading in the volume PDF.", file=sys.stderr)
        raise SystemExit(3)
    end = next_part_start if next_part_start is not None else doc.page_count

    cropped = fitz.open()
    cropped.insert_pdf(doc, from_page=start_25, to_page=end - 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(str(dest))
    cropped.close()
    doc.close()
    cropped_pages = end - start_25
    print(f"cropped pages {start_25}..{end - 1} ({cropped_pages} pages) -> {dest}")
    return dest


if __name__ == "__main__":
    raise SystemExit(main())
