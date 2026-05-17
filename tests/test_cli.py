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


def test_dev_simulate_luxe_traces_exit_zero(tmp_path, capsys):
    """Smoke test: command runs without error."""
    rc, out, _ = _run(
        ["dev", "simulate-luxe-traces", "--output-dir", str(tmp_path)],
        capsys,
    )
    assert rc == 0
    assert "wrote 4 archetype bundles" in out
    # Anti-conflation footer must be visible in CLI output
    assert "synthetic" in out.lower()


def test_dev_simulate_luxe_traces_creates_bundle(tmp_path, capsys):
    """Output directory has 4 archetype subdirs each with .jsonl + manifest."""
    rc, _out, _err = _run(
        ["dev", "simulate-luxe-traces", "--output-dir", str(tmp_path)],
        capsys,
    )
    assert rc == 0
    subdirs = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert subdirs == [
        "archetype_diff_heavy",
        "archetype_hostile",
        "archetype_lint_heavy",
        "archetype_long_session",
    ]
    for sub in subdirs:
        subdir = tmp_path / sub
        # one .jsonl + manifest.json each
        assert any(p.suffix == ".jsonl" for p in subdir.iterdir())
        assert (subdir / "manifest.json").exists()


def test_dev_simulate_luxe_traces_seed_changes_output(tmp_path, capsys):
    """--seed flag is wired through and affects (at least) hostile."""
    _run(
        ["dev", "simulate-luxe-traces",
         "--output-dir", str(tmp_path / "a"), "--seed", "1"],
        capsys,
    )
    _run(
        ["dev", "simulate-luxe-traces",
         "--output-dir", str(tmp_path / "b"), "--seed", "2"],
        capsys,
    )
    a = (tmp_path / "a" / "archetype_hostile" / "hostile.jsonl").read_bytes()
    b = (tmp_path / "b" / "archetype_hostile" / "hostile.jsonl").read_bytes()
    assert a != b


def test_resolve_corpus_emits_drift_on_stderr(tmp_path, capsys):
    """When --luxe-trace-dir has skip_rate > 0 on any file, the
    schema-drift table prints on stderr. The CLI hook lives in
    _resolve_corpus; verify end-to-end via the eval subcommand."""
    (tmp_path / "drifty.jsonl").write_text(
        '{"event": "telemetry"}\n'
        '{"role": "user", "content": "hi"}\n'
    )
    rc, _out, err = _run(
        ["eval", "noop", "--luxe-trace-dir", str(tmp_path)],
        capsys,
    )
    assert rc == 0
    assert "schema-drift accounting" in err
    assert "drifty.jsonl" in err


def test_resolve_corpus_silent_on_clean_traces(tmp_path, capsys):
    """No drift, no stderr — silence-when-clean policy."""
    (tmp_path / "clean.jsonl").write_text(
        '{"role": "user", "content": "hi"}\n'
        '{"role": "tool", "name": "x", "content": "y"}\n'
    )
    rc, _out, err = _run(
        ["eval", "noop", "--luxe-trace-dir", str(tmp_path)],
        capsys,
    )
    assert rc == 0
    assert "schema-drift accounting" not in err
