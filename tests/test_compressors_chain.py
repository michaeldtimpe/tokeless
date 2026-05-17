import copy

import pytest

from tokeless import corpora
from tokeless.compressors import (
    CompressorStats,
    Message,
    compress_messages,
    messages_bytes,
    register,
)
from tokeless.compressors.chain import ChainCompressor
from tokeless.compressors.structural_dedup import StructuralDedupCompressor
from tokeless.compressors.structured_normalize import StructuredNormalizeCompressor
from tokeless.corpora import Corpus, CorpusItem
from tokeless.eval.runner import run_eval


# ----- Core mechanics ------------------------------------------------------


def test_empty_chain_is_a_passthrough():
    chain = ChainCompressor(name="empty_test", links=[])
    msgs = [
        {"role": "system", "content": "hi"},
        {"role": "tool", "name": "git_diff", "content": "x" * 200},
    ]
    out, stats = chain.apply(msgs)
    assert stats.fires == 0
    assert messages_bytes(out) == messages_bytes(msgs)
    assert out == msgs


def test_single_link_chain_equals_underlying_compressor():
    """Chain of [structural_dedup] is identical to structural_dedup alone."""
    body = "x" * 200
    msgs = [
        {"role": "tool", "name": "git_diff", "content": body},
        {"role": "tool", "name": "git_diff", "content": body},
    ]
    chain = ChainCompressor(
        name="single_link_test", links=[StructuralDedupCompressor()]
    )
    chain_out, chain_stats = chain.apply(msgs)
    direct_out, direct_stats = StructuralDedupCompressor().apply(msgs)
    assert chain_out == direct_out
    assert chain_stats.fires == direct_stats.fires
    assert chain_stats.bytes_out == direct_stats.bytes_out


def test_two_link_bytes_accounting_reflects_chain_boundaries():
    """bytes_in is original; bytes_out is final — NOT per-link sum."""
    chain_id = "dedup_then_normalize"
    corpus = corpora.get("mixed_session")
    item = corpus.items[0]
    out, stats = compress_messages(item.messages, chain_id)
    assert stats.bytes_in == messages_bytes(item.messages)
    assert stats.bytes_out == messages_bytes(out)
    # Sanity: chain saved something on this corpus.
    assert stats.bytes_out < stats.bytes_in


def test_two_link_fires_aggregates_across_links():
    """fires is sum of per-link fires — both dedup and normalize contribute."""
    chain_id = "dedup_then_normalize"
    corpus = corpora.get("mixed_session")
    item = corpus.items[0]
    _, stats = compress_messages(item.messages, chain_id)
    # On mixed_session, dedup fires multiple times AND normalize fires
    # at least once on the canonical mypy turn. Total fires should
    # exceed what either link alone would produce; assert just the
    # combined contribution rather than a specific arithmetic equality.
    _, dedup_stats = StructuralDedupCompressor().apply(item.messages)
    _, normalize_stats = StructuredNormalizeCompressor().apply(item.messages)
    assert stats.fires >= dedup_stats.fires, (
        "chain fires should include all of link 1's contribution"
    )
    # The chain's normalize step sees the deduped output, so it may
    # fire fewer times than normalize alone (duplicates are gone),
    # but at least one normalize fire is expected on mixed_session.
    assert stats.fires > dedup_stats.fires, (
        "normalize link should contribute at least one additional fire"
    )


# ----- Composition correctness --------------------------------------------


def test_stub_passthrough_through_normalize():
    """Dedup stubs reach normalize but are skipped by the stub-isolation guard.

    Two byte-identical mypy messages → dedup catches duplicate at link 1
    → stub message reaches link 2 with name='mypy' → stub guard
    short-circuits before regex. The stub literal survives verbatim.
    """
    mypy_body = (
        "src/foo/bar.py:12:5: error: Bad return [return-value]\n"
        "src/foo/bar.py:48:9: error: Bad arg [arg-type]\n"
    )
    msgs = [
        {"role": "tool", "name": "mypy", "content": mypy_body},
        {"role": "tool", "name": "mypy", "content": mypy_body},
    ]
    out, _ = compress_messages(msgs, "dedup_then_normalize")
    # Second message should be a dedup stub, not a normalized form.
    assert out[1]["content"].startswith("[duplicate of msg #0 tool=mypy"), (
        f"expected dedup stub, got: {out[1]['content']!r}"
    )


def test_chain_does_not_mutate_caller_messages():
    """Input list snapshot must equal post-apply snapshot, byte-for-byte."""
    corpus = corpora.get("mixed_session")
    item = corpus.items[0]
    snapshot = copy.deepcopy(item.messages)
    compress_messages(item.messages, "dedup_then_normalize")
    assert item.messages == snapshot, (
        "chain MUST NOT mutate the caller's messages list"
    )


def test_canonical_chain_is_idempotent_on_mixed_session():
    """chain(chain(x)) == chain(x) — stubs don't re-stub, normalized stays normalized."""
    corpus = corpora.get("mixed_session")
    item = corpus.items[0]
    once_out, _ = compress_messages(item.messages, "dedup_then_normalize")
    twice_out, _ = compress_messages(once_out, "dedup_then_normalize")
    assert once_out == twice_out, (
        "applying the canonical chain twice should yield the same result as once"
    )


# ----- Safety guards -------------------------------------------------------


def test_integrity_error_in_sub_compressor_propagates_through_chain():
    """Chain must not become an exception-swallowing boundary."""

    class BadDrop:
        name = "chain_bad_drop"

        def apply(self, messages):
            return [], CompressorStats(name=self.name)

    register(BadDrop())
    bad_chain = ChainCompressor(
        name="chain_with_bad", links=[BadDrop()]
    )
    register(bad_chain)

    corpus = Corpus(
        name="t",
        description="",
        items=[CorpusItem("i1", [{"role": "user", "content": "a"}])],
    )
    with pytest.raises(RuntimeError, match="message-count drift"):
        run_eval(corpus, "chain_with_bad")
