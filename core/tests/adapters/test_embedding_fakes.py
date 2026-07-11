"""Unit tests for the embedding/token-count fakes and the dry-run ZeroEmbedder
(spec §17 rule 3, task 2e). The real bge-m3 adapters require the heavy embed
extra and are exercised end-to-end at ingestion time; here we cover the
deterministic fakes and the SKIP_EMBEDDINGS zero-vector path that must work in
CI (no extras installed).
"""

from __future__ import annotations

from collections.abc import Callable

from groundcite.adapters.embedding.bge_m3_embed import ZeroEmbedder
from tests.fakes import FakeEmbedder, FakeTokenCounter


def test_fake_embedder_returns_1024d_zero_vectors() -> None:
    emb = FakeEmbedder()
    assert emb.dimension == 1024
    vecs = emb.embed(["a", "b", "c"])
    assert len(vecs) == 3
    for v in vecs:
        assert len(v) == 1024
        assert all(x == 0.0 for x in v)


def test_zero_embedder_matches_dimension_and_is_deterministic() -> None:
    emb = ZeroEmbedder()
    assert emb.dimension == 1024
    a = emb.embed(["x", "y"])
    b = emb.embed(["x", "y"])
    assert len(a) == 2 and a == b
    assert all(v == tuple(0.0 for _ in range(1024)) for v in a)


def test_fake_token_counter_is_whitespace_split() -> None:
    counter: Callable[[str], int] = FakeTokenCounter().count
    assert counter("") == 0
    assert counter("one two three") == 3
    assert counter("grounded citations §25.1309") == 3


def test_fake_token_counter_signature_matches_injected_callable() -> None:
    # The Chunker port injects count_tokens as Callable[[str], int]; the fake
    # bound method must be usable as such.
    count: Callable[[str], int] = FakeTokenCounter().count
    assert count("a b c") == 3
