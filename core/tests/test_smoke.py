"""Trivial smoke test — proves the package imports and the test setup works.

Real unit tests (services with fake ports, spec §17 rule 3) arrive with the
features they cover. This one only exercises the skeleton wiring.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from groundcite import __version__
from groundcite.config import Settings
from groundcite.container import Services, build_services
from groundcite.domain import AskStatus, Citation


def test_skeleton_wires_together() -> None:
    assert __version__ == "0.1.0"

    # Domain models are frozen (spec §17 rule 5): mutation must fail.
    citation = Citation(chunk_id=uuid4(), rank=1, score=0.9)
    with pytest.raises(ValidationError):
        citation.rank = 2  # type: ignore[misc]

    # StrEnum domain values match the spec §5 vocabulary.
    assert AskStatus.GROUNDED == "grounded"

    # The composition root returns the four services (spec §4), no adapters yet.
    services = build_services(Settings())
    assert isinstance(services, Services)
    assert all(
        obj is not None
        for obj in (services.ingestion, services.ask, services.evals, services.library)
    )
