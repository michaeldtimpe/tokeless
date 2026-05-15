import pytest

from tokeless.compressors import Message
from tokeless.compressors.exact_hash_dedup import ExactHashDedupCompressor
from tokeless.compressors import register, CompressorStats
from tokeless.corpora import Corpus, CorpusItem
from tokeless.eval.runner import run_eval


def test_run_eval_on_noop_gives_zero_savings():
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem(
                "i1",
                [
                    {"role": "user", "content": "hi"},
                    {"role": "tool", "name": "x", "content": "y" * 100},
                ],
            )
        ],
    )
    result = run_eval(corpus, "noop")
    assert result.totals.fires == 0
    assert result.totals.bytes_in == result.totals.bytes_out
    assert result.firing_rate == 0.0


def test_run_eval_on_dedup_records_savings():
    body = "z" * 500
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem(
                "i1",
                [
                    {"role": "tool", "name": "x", "content": body},
                    {"role": "tool", "name": "x", "content": body},
                ],
            )
        ],
    )
    result = run_eval(corpus, "exact_hash_dedup")
    assert result.fired_on == 1
    assert result.firing_rate == 1.0
    assert result.totals.bytes_in > result.totals.bytes_out
    assert result.totals.items_dropped == 1


def test_integrity_check_raises_when_compressor_drops_messages():
    class BadCompressor:
        name = "bad_drop"

        def apply(self, messages):
            return [], CompressorStats(name=self.name)

    register(BadCompressor())
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem("i1", [{"role": "user", "content": "a"}])
        ],
    )
    with pytest.raises(RuntimeError, match="message-count drift"):
        run_eval(corpus, "bad_drop")


def test_integrity_check_skipped_when_disabled():
    class StillBad:
        name = "bad_drop_skipped"

        def apply(self, messages):
            return [], CompressorStats(name=self.name)

    register(StillBad())
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem("i1", [{"role": "user", "content": "a"}])
        ],
    )
    result = run_eval(corpus, "bad_drop_skipped", raise_on_drift=False)
    assert result.items[0].stats.notes  # drift recorded but not raised


def test_format_table_includes_per_item_and_total_rows():
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem(
                "alpha",
                [{"role": "tool", "name": "x", "content": "y" * 200}] * 2,
            )
        ],
    )
    result = run_eval(corpus, "exact_hash_dedup")
    table = result.format_table()
    assert "alpha" in table
    assert "TOTAL" in table
    assert "fired on 1/1 item(s)" in table
