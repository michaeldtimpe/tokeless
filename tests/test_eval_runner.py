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


def test_integrity_check_raises_on_role_order_drift():
    """Pins the role-order branch of _validate_integrity (runner.py:89)."""

    class BadRoleSwap:
        name = "bad_role_swap"

        def apply(self, messages):
            if len(messages) >= 2:
                swapped = [messages[1], messages[0]] + list(messages[2:])
            else:
                swapped = list(messages)
            return swapped, CompressorStats(name=self.name)

    register(BadRoleSwap())
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem(
                "i1",
                [
                    {"role": "user", "content": "a"},
                    {"role": "tool", "name": "x", "content": "b"},
                ],
            )
        ],
    )
    with pytest.raises(RuntimeError, match="role-order drift"):
        run_eval(corpus, "bad_role_swap")


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


def test_format_table_includes_tokens_and_decode_seconds():
    """Pins the wall-time proxy columns and footer."""
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem(
                "alpha",
                [{"role": "tool", "name": "x", "content": "y" * 400}] * 2,
            )
        ],
    )
    result = run_eval(corpus, "exact_hash_dedup")
    table = result.format_table(tokens_per_second=50)
    assert "saved_T" in table
    assert "tokens saved ≈" in table
    assert "@50 tok/s" in table
    assert "proxy: bytes/4" in table


def test_format_table_includes_avg_bytes_per_fire_column():
    """Pins the avg_B/fire column placement (between saved_T and ratio)."""
    corpus = Corpus(
        name="t",
        description="",
        items=[
            CorpusItem(
                "alpha",
                [{"role": "tool", "name": "x", "content": "y" * 400}] * 2,
            )
        ],
    )
    result = run_eval(corpus, "exact_hash_dedup")
    table = result.format_table()
    assert "avg_B/fire" in table
    # Placement: avg_B/fire appears AFTER saved_T and BEFORE ratio
    header_line = table.splitlines()[0]
    assert header_line.index("saved_T") < header_line.index("avg_B/fire")
    assert header_line.index("avg_B/fire") < header_line.index("ratio")


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
