"""FastAPI dependencies (spec §9).

Bridges the interface layer to the core composition root: settings come from
``groundcite.config`` and services from ``groundcite.container.build_services``.
Used by route handlers via ``Depends`` in Week 4.
"""

from __future__ import annotations

from groundcite.config import Settings, get_settings
from groundcite.container import Services, build_services


def get_app_settings() -> Settings:
    return get_settings()


def get_services() -> Services:
    return build_services(get_settings())
