"""Reciprocal Rank Fusion + the clause fast path — spec §7 step 2.

Pure functions, zero I/O. This module is deliberately OURS: spec §11.1 lists
"hybrid fusion (RRF) + clause fast-path" under Build (always) — it is the
portfolio piece, and no library touches it.

RRF (spec §7 step 2): ``score(c) = Σ_i 1/(rrf_k + rank_i(c))`` over each ranked
candidate list the chunk appears in, ranks 1-based. Why RRF rather than blending
the raw scores: cosine similarity and ts_rank_cd live on incomparable scales
(0-1 vs. an unbounded lexical rank), so any weighted sum of them needs
per-corpus calibration. RRF only reads POSITIONS, so it fuses the two without
that calibration — and a chunk both retrievers agree on outranks one that only
a single retriever found, which is exactly the signal we want.

The clause fast path (spec §7 step 1c/2) is NOT just a third list fed into RRF.
Spec §7 says such a hit is "injected at rank 1", and that is a hard guarantee
here: if the asker names §25.1309(b), that clause IS the top passage. It is a
different KIND of evidence — an exact structural ID match, not a fuzzy
similarity — so it carries its own score (``CLAUSE_FAST_PATH_SCORE``) rather
than being folded into the RRF scale, where a genuine exact match could
otherwise be outranked by two fuzzy near-misses. In a domain where a wrong
citation is worse than no answer (§1), the exact hit wins by construction.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from groundcite.domain.entities import Chunk

# An exact clause-ID hit is maximal confidence, on a different scale from RRF
# (whose scores are tiny: with 2 lists and rrf_k=60, the ceiling is ~0.033).
# Keeping it separate means Gate A (Week 3) cannot abstain on an exact clause
# match just because RRF's numbers are small.
CLAUSE_FAST_PATH_SCORE = 1.0


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[tuple[Chunk, float]]],
    rrf_k: int,
) -> dict[UUID, float]:
    """RRF score per chunk id across ``ranked_lists`` (spec §7 step 2).

    Each input list is already ordered best-first by its own retriever's score;
    RRF reads only the POSITION, never the score, which is the whole point.
    """
    scores: dict[UUID, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (chunk, _score) in enumerate(ranked, start=1):
            scores[chunk.id] += 1.0 / (rrf_k + rank)
    return dict(scores)


def fuse(
    dense: Sequence[tuple[Chunk, float]],
    lexical: Sequence[tuple[Chunk, float]],
    clause_hits: Sequence[Chunk],
    rrf_k: int,
    top_k: int,
) -> list[tuple[Chunk, float]]:
    """Fuse dense + lexical candidates by RRF, with exact clause hits injected at
    rank 1, and return the top ``top_k`` (spec §7 step 2).

    Ordering is fully deterministic (ties broken by clause_path then id) so eval
    runs are reproducible.
    """
    if top_k <= 0:
        return []

    by_id: dict[UUID, Chunk] = {}
    for ranked in (dense, lexical):
        for chunk, _ in ranked:
            by_id.setdefault(chunk.id, chunk)

    scores = reciprocal_rank_fusion([dense, lexical], rrf_k)

    # Exact clause matches lead, in the order the index returned them, and are
    # excluded from the RRF tail so they cannot appear twice.
    fast_path: list[tuple[Chunk, float]] = []
    seen: set[UUID] = set()
    for chunk in clause_hits:
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        by_id.setdefault(chunk.id, chunk)
        fast_path.append((chunk, CLAUSE_FAST_PATH_SCORE))

    tail = [(by_id[chunk_id], score) for chunk_id, score in scores.items() if chunk_id not in seen]
    tail.sort(key=lambda pair: (-pair[1], pair[0].clause_path, str(pair[0].id)))

    return (fast_path + tail)[:top_k]
