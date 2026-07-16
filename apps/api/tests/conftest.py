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
from fastapi.testclient import TestClient

from app import main as app_main
from app.deps import get_app_settings, get_services
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


class _EvalsProto(Protocol):
    def list_runs(self) -> list[object]: ...
    def get_report(self, run_id: UUID) -> tuple[object, list[object]] | None: ...


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

    def get_ask(self, ask_id: UUID) -> object | None:
        return self.asks.get(ask_id)

    def get_ask_citations(self, ask_id: UUID) -> list[object]:
        return self.citations.get(ask_id, [])


@dataclass
class StubEvals:
    runs: list[object] = field(default_factory=list)
    reports: dict[UUID, tuple[object, list[object]]] = field(default_factory=dict)

    def list_runs(self) -> list[object]:
        return self.runs

    def get_report(self, run_id: UUID) -> tuple[object, list[object]] | None:
        return self.reports.get(run_id)


@dataclass
class StubServices:
    library: StubLibrary = field(default_factory=StubLibrary)
    ask: StubAsk = field(default_factory=StubAsk)
    evals: StubEvals = field(default_factory=StubEvals)
    # ingestion unused by the read routes.


@dataclass(frozen=True)
class StubSettings:
    tau_retrieval: float = 0.70
    groq_model: str = "openai/gpt-oss-120b"
    llm_provider: str = "groq"
    reranker_enabled: bool = True


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def stub_services() -> StubServices:
    return StubServices()


@pytest.fixture
def make_client() -> Iterator[Callable[[StubServices | None], TestClient]]:
    """Factory building a TestClient wired to a (default or custom) stub. The
    default stub is empty; tests populate it. Overrides are cleaned up after."""
    created: list[TestClient] = []

    def _make(services: StubServices | None = None) -> TestClient:
        svc = services if services is not None else StubServices()
        app = create_app()
        app.dependency_overrides[get_services] = lambda: svc
        app.dependency_overrides[get_app_settings] = lambda: StubSettings()
        app.state.services = svc
        c = TestClient(app)
        created.append(c)
        return c

    yield _make
    for c in created:
        c.app.dependency_overrides.clear()


@pytest.fixture
def client(make_client) -> TestClient:
    """A client on the default (empty) stub."""
    return make_client()


__all__ = [
    "StubAsk",
    "StubEvals",
    "StubLibrary",
    "StubServices",
    "StubSettings",
    "client",
    "stub_services",
]


# Avoid an unused-import lint for the protocol helpers used only for typing.
_ = (_LibraryProto, _AskProto, _EvalsProto, app_main, Sequence)
