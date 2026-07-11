"""LibraryService — document library + clause-tree reads (spec §9, §10).

Implements the read side behind ``GET /documents`` / ``GET /documents/{slug}``
and the reader's clause tree (spec §9, §10). Not yet implemented (Week 4).
Depends on the Repository port.
"""

from __future__ import annotations


class LibraryService:
    """List Documents and resolve their Section trees (spec §9, §10)."""
