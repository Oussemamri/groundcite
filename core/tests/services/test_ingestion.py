"""Unit tests for IngestionService (spec §6, §17 rule 3: fake ports, no DB/network).

Wires the service with a fake parser (synthetic ParsedDocument), the real
cfr_structure detector + clause_chunker (pure, no I/O), FakeEmbedder + FakeTokenCounter,
and a FakeRepository. Covers the full orchestration and idempotent re-ingest
(same slug → replace_sections_and_chunks called again, row counts unchanged).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from groundcite.adapters.chunker.clause_chunker import ClauseChunker
from groundcite.adapters.structure.cfr_structure import CfrStructureDetector
from groundcite.domain.entities import DocumentMeta, ParsedBlock, ParsedDocument, ParsedPage
from groundcite.services.ingestion import IngestionService
from tests.fakes import FakeEmbedder, FakeRepository, FakeTokenCounter


class _FakeParser:
    """A fake DocumentParser that returns a canned CFR-style ParsedDocument."""

    def __init__(self, pages: list[ParsedPage], document_id: UUID | None = None) -> None:
        self._pages = pages
        self._document_id = document_id

    def parse(self, pdf_path: Path) -> ParsedDocument:
        return ParsedDocument(pages=tuple(self._pages), document_id=self._document_id)


def _meta() -> DocumentMeta:
    return DocumentMeta(
        slug="far-25",
        standard_code="14 CFR Part 25",
        title="Airworthiness standards: Transport category airplanes",
        organization="FAA",
        license_note="US public domain",
        source_url="https://www.govinfo.gov/...",
    )


def _sample_pages() -> list[ParsedPage]:
    return [
        ParsedPage(
            page_number=1,
            blocks=(
                ParsedBlock(text="Subpart B—Flight", page_number=1),
                ParsedBlock(text="§ 25.1309 Equipment, systems, and installations.", page_number=1),
                ParsedBlock(
                    text="The applicant must show that the equipment is designed to function.",
                    page_number=1,
                ),
                ParsedBlock(
                    text="(a) Each item must independently perform its function.",
                    page_number=1,
                ),
                ParsedBlock(
                    text="(a)(1) For catastrophic conditions a very low probability is required.",
                    page_number=1,
                ),
                ParsedBlock(
                    text="(b) Each item must be installed in a safe manner under all conditions.",
                    page_number=1,
                ),
            ),
        ),
    ]


def _service(repo: FakeRepository) -> IngestionService:
    return IngestionService(
        parser=_FakeParser(_sample_pages()),
        detector=CfrStructureDetector(),
        chunker=ClauseChunker(min_leaf_tokens=64),
        embedder=FakeEmbedder(),
        token_counter=FakeTokenCounter(),
        repository=repo,
    )


def test_ingest_creates_report_and_persists() -> None:
    repo = FakeRepository()
    report = _service(repo).ingest(Path("x.pdf"), _meta())

    assert report.slug == "far-25"
    assert report.standard_code == "14 CFR Part 25"
    assert report.sections_found >= 4  # subpart + section + (a) + (a)(1) + (b)
    assert report.chunks_created >= 1
    assert report.orphan_pct <= 0.10, f"orphan {report.orphan_pct:.1%} exceeds 10%"
    assert sum(report.token_histogram.values()) == report.chunks_created
    # persisted
    assert "far-25" in repo.documents
    assert len(repo.sections["far-25"]) == report.sections_found
    assert len(repo.chunks["far-25"]) == report.chunks_created


def test_re_ingest_is_idempotent() -> None:
    repo = FakeRepository()
    svc = _service(repo)
    r1 = svc.ingest(Path("x.pdf"), _meta())
    first_sections = report_count_sections(repo)
    first_chunks = report_count_chunks(repo)
    document_id_after_first = repo.documents["far-25"].id

    r2 = svc.ingest(Path("x.pdf"), _meta())

    # Row counts unchanged (spec §6 idempotency / Week-1 DoD).
    assert first_sections == report_count_sections(repo)
    assert first_chunks == report_count_chunks(repo)
    # The document id is preserved on slug re-upsert.
    assert repo.documents["far-25"].id == document_id_after_first
    # replace_sections_and_chunks ran again (one logical transaction per ingest).
    assert repo.replace_calls == 2
    # Reports are structurally identical for a deterministic ingest.
    assert r1.sections_found == r2.sections_found
    assert r1.chunks_created == r2.chunks_created


def test_chunks_carry_1024d_embeddings() -> None:
    repo = FakeRepository()
    _service(repo).ingest(Path("x.pdf"), _meta())
    for chunk in repo.chunks["far-25"]:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 1024


def report_count_sections(repo: FakeRepository) -> int:
    return len(repo.sections["far-25"])


def report_count_chunks(repo: FakeRepository) -> int:
    return len(repo.chunks["far-25"])
