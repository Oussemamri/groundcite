"""structlog configuration for the API layer (spec §12, AD-9).

JSON to stdout, API-layer only — core stays logfree (it returns plain results and
the API logs them). Processors bind a request id (middleware) and, for an ask, the
``ask_id`` as soon as the FINAL/ERROR event carries it (bound in the asks route,
not per-token — spec §12: "log line per stage transition, not per token").
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging() -> None:
    """Configure structlog JSON output to stdout (idempotent)."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """A bound structlog logger (request id / ask_id merged via contextvars)."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
