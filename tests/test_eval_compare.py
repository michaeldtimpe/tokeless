from tokeless.corpora import Corpus, CorpusItem, get as get_corpus
from tokeless.eval.compare import ComparisonThresholds, compare


def test_compare_dedup_vs_noop_on_repeats_passes():
    corpus = get_corpus("git_diff_repeated")
    report = compare(corpus, "noop", "exact_hash_dedup")
    assert report.verdict == "PASS", report.reasons
    assert report.total_pct_saved >= 0.20
    assert report.treatment.fired_on >= 1


def test_compare_noop_vs_noop_fails_no_improvement():
    corpus = get_corpus("git_diff_repeated")
    report = compare(corpus, "noop", "noop")
    assert report.verdict == "FAIL"
    assert any("bytes-improvement" in r for r in report.reasons)


def test_compare_dedup_on_non_redundant_corpus_fails_firing():
    corpus = Corpus(
        name="no_dupes",
        description="",
        items=[
            CorpusItem(
                "alpha",
                [
                    {"role": "tool", "name": "git_diff", "content": "a" * 500},
                    {"role": "tool", "name": "git_diff", "content": "b" * 500},
                ],
            )
        ],
    )
    report = compare(corpus, "noop", "exact_hash_dedup")
    assert report.verdict == "FAIL"
    assert any("bytes-improvement" in r for r in report.reasons)


def test_thresholds_can_be_tuned():
    corpus = get_corpus("git_diff_repeated")
    strict = ComparisonThresholds(min_bytes_improvement=0.99)
    report = compare(corpus, "noop", "exact_hash_dedup", strict)
    assert report.verdict == "FAIL"


def test_latency_ceiling_fail_branch():
    """Pins the latency-ceiling FAIL reason (compare.py:155-163).

    Uses 1e-9 (sub-nanosecond) rather than 0.0 — the strict-greater-than
    check at compare.py:155-156 could theoretically allow a perf_counter
    measurement of exactly 0.0 to slip past `> 0.0` on coarse clocks; a
    1ns threshold cannot be met by any real measurement and makes the
    test's intent explicit.
    """
    corpus = get_corpus("git_diff_repeated")
    thresholds = ComparisonThresholds(max_latency_per_item_s=1e-9)
    report = compare(corpus, "noop", "exact_hash_dedup", thresholds)
    assert report.verdict == "FAIL"
    assert any("latency ceiling" in r for r in report.reasons), report.reasons


def test_format_report_includes_total_tokens_saved():
    """Pins the wall-time proxy footer on the comparison report."""
    corpus = get_corpus("git_diff_repeated")
    report = compare(corpus, "noop", "exact_hash_dedup")
    text = report.format_report(tokens_per_second=200)
    assert "total tokens saved" in text
    assert "@200 tok/s" in text
    assert "proxy: bytes/4" in text


def test_format_report_includes_avg_savings_per_fire():
    """Pins the avg-savings-per-fire footer. The 'avg' prefix is
    load-bearing — 'savings per fire' alone can be misread as
    cumulative."""
    corpus = get_corpus("git_diff_repeated")
    report = compare(corpus, "noop", "exact_hash_dedup")
    text = report.format_report()
    assert "avg savings per fire" in text
    # Numeric value present (not blank) — uses the treatment totals
    expected = report.treatment.totals.bytes_saved_per_fire
    assert f"≈ {expected} B" in text


def test_format_report_includes_latency_p50_p95():
    """Pins the latency-percentile footer in the comparison report.
    Same item-level granularity comment as runner."""
    corpus = get_corpus("git_diff_repeated")
    report = compare(corpus, "noop", "exact_hash_dedup")
    text = report.format_report()
    assert "treatment latency p50 ≈" in text
    assert "p95 ≈" in text
    assert "(computed over corpus items)" in text


def test_format_report_includes_verdict_line():
    corpus = get_corpus("git_diff_repeated")
    report = compare(corpus, "noop", "exact_hash_dedup")
    text = report.format_report()
    assert "VERDICT:" in text
    assert "exact_hash_dedup vs noop" in text
