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


def test_format_report_includes_verdict_line():
    corpus = get_corpus("git_diff_repeated")
    report = compare(corpus, "noop", "exact_hash_dedup")
    text = report.format_report()
    assert "VERDICT:" in text
    assert "exact_hash_dedup vs noop" in text
