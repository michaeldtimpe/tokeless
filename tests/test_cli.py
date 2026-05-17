import io
import sys

import pytest

from tokeless.cli import main


def _run(argv, capsys):
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_compressor_list(capsys):
    rc, out, _ = _run(["compressor", "list"], capsys)
    assert rc == 0
    assert "noop" in out
    assert "exact_hash_dedup" in out
    assert "structured_normalize" in out


def test_corpus_list(capsys):
    rc, out, _ = _run(["corpus", "list"], capsys)
    assert rc == 0
    assert "mixed_session" in out
    assert "git_diff_repeated" in out


def test_eval_runs_and_prints_table(capsys):
    rc, out, _ = _run(["eval", "exact_hash_dedup", "git_diff_repeated"], capsys)
    assert rc == 0
    assert "fired on" in out
    assert "TOTAL" in out


def test_compare_pass_returns_zero(capsys):
    rc, out, _ = _run(
        ["compare", "noop", "exact_hash_dedup", "git_diff_repeated"], capsys
    )
    assert rc == 0
    assert "VERDICT: PASS" in out


def test_compare_fail_returns_nonzero(capsys):
    rc, out, _ = _run(
        ["compare", "noop", "noop", "git_diff_repeated"], capsys
    )
    assert rc == 1
    assert "VERDICT: FAIL" in out


def test_eval_with_luxe_trace_dir(tmp_path, capsys):
    (tmp_path / "a.jsonl").write_text(
        '{"role": "user", "content": "hi"}\n'
        '{"role": "tool", "name": "x", "content": "%s"}\n' % ("z" * 200)
    )
    rc, out, _ = _run(
        ["eval", "noop", "--luxe-trace-dir", str(tmp_path)], capsys
    )
    assert rc == 0
    assert "luxe_trace:" in out


def test_missing_corpus_errors(capsys):
    with pytest.raises(SystemExit):
        main(["eval", "noop"])


def test_eval_accepts_tokens_per_second_flag(capsys):
    rc, out, _ = _run(
        ["eval", "noop", "git_diff_repeated", "--tokens-per-second", "50"],
        capsys,
    )
    assert rc == 0
    assert "@50 tok/s" in out
    assert "tokens saved" in out


def test_compare_accepts_tokens_per_second_flag(capsys):
    rc, out, _ = _run(
        [
            "compare", "noop", "exact_hash_dedup", "git_diff_repeated",
            "--tokens-per-second", "75",
        ],
        capsys,
    )
    assert rc == 0
    assert "@75 tok/s" in out
    assert "total tokens saved" in out


def test_compare_threshold_flag_changes_verdict(capsys):
    """Pins the argparse → ComparisonThresholds wiring at cli.py:60-64.

    The threshold *logic* at min_bytes_improvement=0.99 is already covered
    by test_thresholds_can_be_tuned in test_eval_compare.py. The unique
    value of this test is end-to-end CLI plumbing — that argparse parses
    the float and threads it through to compare() — which has no other
    coverage.
    """
    default_rc, default_out, _ = _run(
        ["compare", "noop", "exact_hash_dedup", "git_diff_repeated"], capsys
    )
    assert default_rc == 0
    assert "VERDICT: PASS" in default_out

    strict_rc, strict_out, _ = _run(
        [
            "compare", "noop", "exact_hash_dedup", "git_diff_repeated",
            "--min-bytes-improvement", "0.99",
        ],
        capsys,
    )
    assert strict_rc == 1
    assert "VERDICT: FAIL" in strict_out
