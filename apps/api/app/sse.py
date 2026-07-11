"""Server-Sent Events helpers for the ask stream (spec §7).

The event types are NOT redefined here — they are re-exported from the core
domain so API and web share one source of truth (spec §7: "API and web must
share this enum"). The web parser in ``apps/web/lib/sse.ts`` mirrors these.
"""

from __future__ import annotations

import json

from groundcite.domain import AskEvent, AskEventType, Stage

__all__ = ["AskEvent", "AskEventType", "Stage", "format_sse"]


def format_sse(event: AskEvent) -> str:
    """Serialize an ``AskEvent`` to an SSE wire frame (``event:``/``data:``)."""
    payload = json.dumps(event.data, separators=(",", ":"))
    return f"event: {event.type.value}\ndata: {payload}\n\n"
