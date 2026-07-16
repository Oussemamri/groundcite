"""API unit-test harness (spec §9, AD-7).

A tiny ``StubServices`` mirrors only the methods the routes touch (AD-7: do NOT
import core's ``tests.fakes`` — it is not installed with the package; duplicate
the stubs at the ``Services`` seam). Routes are tested through Starlette's
``TestClient`` (requires httpx, AD-7 dev dep) with ``app.dependency_overrides``
so no network, no DB, no model loads run (CLAUDE rule 3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_starlette.sse import AppStatus

from app import main as app_main
from app.deps import get_app_settings, get_services
from app.jobs import JobRegistry
from app.main import create_app

# --- stubs at the Services seam ----------------------------------------------


class _LibraryProto(Protocol):
    def list_documents(self) -> list[object]: ...
    def get_document(self, slug: str) -> object | None: ...
    def get_section_tree(self, document_id: UUID) -> list[object]: ...
    def list_chunks(self, document_id: UUID) -> list[object]: ...
    def get_chunk(self, chunk_id: UUID) -> object | None: ...


class _AskProto(Protocol):
    def get_ask(self, ask_id: UUID) -> object | None: ...
    def get_ask_citations(self, ask_id: UUID) -> list[object]: ...
    def ask(
        self, question: str, document_slugs: Sequence[str] | None = None
    ) -> Iterator[object]: ...


class _EvalsProto(Protocol):
    def list_runs(self) -> list[object]: ...
    def get_report(self, run_id: UUID) -> tuple[object, list[object]] | None: ...
    def run_full(
        self,
        suite: str,
        git_sha: str = "unknown",
        document_slugs: Sequence[str] | None = None,
        config: dict[str, object] | None = None,
        judge: bool = False,
    ) -> tuple[object, UUID]: ...
    def run_retrieval(
        self,
        suite: str,
        git_sha: str = "unknown",
        document_slugs: Sequence[str] | None = None,
        config: dict[str, object] | None = None,
    ) -> object: ...


class _IngestionProto(Protocol):
    def ingest(self, pdf_path: object, doc_meta: object) -> object: ...


@dataclass
class StubLibrary:
    documents: list[object] = field(default_factory=list)
    by_slug: dict[str, object] = field(default_factory=dict)
    section_tree: list[object] = field(default_factory=list)
    chunks: list[object] = field(default_factory=list)
    chunk_by_id: dict[UUID, object] = field(default_factory=dict)
    list_documents_error: Exception | None = None

    def list_documents(self) -> list[object]:
        if self.list_documents_error is not None:
            raise self.list_documents_error
        return self.documents

    def get_document(self, slug: str) -> object | None:
        return self.by_slug.get(slug)

    def get_section_tree(self, document_id: UUID) -> list[object]:
        return self.section_tree

    def list_chunks(self, document_id: UUID) -> list[object]:
        return self.chunks

    def get_chunk(self, chunk_id: UUID) -> object | None:
        return self.chunk_by_id.get(chunk_id)


@dataclass
class StubAsk:
    asks: dict[UUID, object] = field(default_factory=dict)
    citations: dict[UUID, list[object]] = field(default_factory=dict)
    # Scripted event stream for POST /asks (AD-2); a callable so each request
    # can get a FRESH iterator (a plain list would be exhausted after test 1).
    events_factory: Callable[[], Iterator[object]] | None = None

    def get_ask(self, ask_id: UUID) -> object | None:
        return self.asks.get(ask_id)

    def get_ask_citations(self, ask_id: UUID) -> list[object]:
        return self.citations.get(ask_id, [])

    def ask(self, question: str, document_slugs: Sequence[str] | None = None) -> Iterator[object]:
        if self.events_factory is None:
            return iter(())
        return self.events_factory()


@dataclass
class StubEvals:
    runs: list[object] = field(default_factory=list)
    reports: dict[UUID, tuple[object, list[object]]] = field(default_factory=dict)
    # POST /eval/runs (AD-5): what run_full/run_retrieval return, or an
    # exception to raise (the "eval_run_failed" job path).
    full_result: tuple[object, UUID] | None = None
    retrieval_result: object | None = None
    run_error: Exception | None = None

    def list_runs(self) -> list[object]:
        return self.runs

    def get_report(self, run_id: UUID) -> tuple[object, list[object]] | None:
        return self.reports.get(run_id)

    def run_full(
        self,
        suite: str,
        git_sha: str = "unknown",
        document_slugs: Sequence[str] | None = None,
        config: dict[str, object] | None = None,
        judge: bool = False,
    ) -> tuple[object, UUID]:
        if self.run_error is not None:
            raise self.run_error
        assert self.full_result is not None, "StubEvals.full_result not set"
        return self.full_result

    def run_retrieval(
        self,
        suite: str,
        git_sha: str = "unknown",
        document_slugs: Sequence[str] | None = None,
        config: dict[str, object] | None = None,
    ) -> object:
        if self.run_error is not None:
            raise self.run_error
        assert self.retrieval_result is not None, "StubEvals.retrieval_result not set"
        return self.retrieval_result


@dataclass
class StubIngestion:
    # POST /documents (AD-5): what ingest() returns, or an exception to raise.
    report: object | None = None
    error: Exception | None = None
    calls: list[tuple[object, object]] = field(default_factory=list)

    def ingest(self, pdf_path: object, doc_meta: object) -> object:
        self.calls.append((pdf_path, doc_meta))
        if self.error is not None:
            raise self.error
        assert self.report is not None, "StubIngestion.report not set"
        return self.report


@dataclass
class StubServices:
    library: StubLibrary = field(default_factory=StubLibrary)
    ask: StubAsk = field(default_factory=StubAsk)
    evals: StubEvals = field(default_factory=StubEvals)
    ingestion: StubIngestion = field(default_factory=StubIngestion)


@dataclass(frozen=True)
class StubSettings:
    tau_retrieval: float = 0.70
    groq_model: str = "openai/gpt-oss-120b"
    llm_provider: str = "groq"
    reranker_enabled: bool = True
    # Retrieval/fusion config (POST /eval/runs' config_snapshot, AD-5 mirrors
    # the CLI's eval_run command exactly -- see WEEK4_INSTRUCTIONS.md AD-5).
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rrf_k: int = 60
    candidates_dense: int = 30
    candidates_lexical: int = 30
    fused_k: int = 20
    context_k: int = 6


# --- fixtures ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_sse_starlette_app_status() -> None:
    """sse-starlette caches a process-global exit event on first use, bound to
    whichever event loop was active THEN (``AppStatus.should_exit_event`` in
    ``sse_starlette/sse.py``). Each pytest test spins up its own TestClient on
    its own event loop, so without this reset the SECOND test to hit an SSE
    route fails with "Event object is bound to a different event loop" --
    real, reproduced while writing test_asks_stream.py. Not a bug in our
    route; sse-starlette's own test suite resets this the same way."""
    AppStatus.should_exit_event = None


@pytest.fixture
def stub_services() -> StubServices:
    return StubServices()


@pytest.fixture
def make_client() -> Iterator[Callable[[StubServices | None], TestClient]]:
    """Factory building a TestClient wired to a (default or custom) stub. The
    default stub is empty; tests populate it. Overrides are cleaned up after."""
    created: list[FastAPI] = []

    def _make(services: StubServices | None = None) -> TestClient:
        svc = services if services is not None else StubServices()
        app = create_app()
        app.dependency_overrides[get_services] = lambda: svc
        app.dependency_overrides[get_app_settings] = lambda: StubSettings()
        app.state.services = svc
        # get_jobs is NOT overridden -- JobRegistry is real, dependency-free
        # (in-memory only, AD-5), so tests use it directly rather than a stub.
        # Set here (not via the lifespan) because bare TestClient(app) -- no
        # `with` block -- does not reliably run lifespan in this version.
        app.state.jobs = JobRegistry()
        created.append(app)
        return TestClient(app)

    yield _make
    for app in created:
        app.dependency_overrides.clear()


@pytest.fixture
def client(make_client: Callable[[StubServices | None], TestClient]) -> TestClient:
    """A client on the default (empty) stub."""
    return make_client(None)


__all__ = [
    "StubAsk",
    "StubEvals",
    "StubIngestion",
    "StubLibrary",
    "StubServices",
    "StubSettings",
    "client",
    "stub_services",
]


# Avoid an unused-import lint for the protocol helpers used only for typing.
_ = (_LibraryProto, _AskProto, _EvalsProto, _IngestionProto, app_main, Sequence)
