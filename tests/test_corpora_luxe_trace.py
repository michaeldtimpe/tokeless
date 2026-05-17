import json
from pathlib import Path

import pytest

from tokeless.corpora.luxe_trace import (
    _MAX_SAMPLE_SHAPES,
    _NON_DICT_SENTINEL,
    LoadStats,
    load_dir,
    load_dir_with_stats,
    load_jsonl,
    load_jsonl_with_stats,
)


def _write(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def _write_raw(path: Path, raw: str) -> None:
    path.write_text(raw)


def test_load_jsonl_extracts_message_events(tmp_path: Path):
    file = tmp_path / "run.jsonl"
    _write(
        file,
        [
            {"event": "start", "ts": 1.0},  # no role — skipped
            {"role": "system", "content": "you are an agent"},
            {"role": "tool", "name": "git_diff", "content": "diff..."},
            {"role": "assistant", "content": "ok"},
        ],
    )
    item = load_jsonl(file)
    assert item.item_id == "run"
    assert [m["role"] for m in item.messages] == ["system", "tool", "assistant"]
    assert item.messages[1]["name"] == "git_diff"


def test_load_jsonl_tolerates_malformed_lines(tmp_path: Path):
    file = tmp_path / "run.jsonl"
    file.write_text(
        '{"role": "user", "content": "hi"}\n'
        "this is not json at all\n"
        "\n"
        '{"role": "tool", "name": "x", "content": "y"}\n'
    )
    item = load_jsonl(file)
    assert len(item.messages) == 2


def test_load_jsonl_fills_missing_content(tmp_path: Path):
    file = tmp_path / "run.jsonl"
    _write(file, [{"role": "assistant", "tool_calls": [{"id": "1"}]}])
    item = load_jsonl(file)
    assert item.messages[0]["content"] == ""
    assert item.messages[0]["tool_calls"] == [{"id": "1"}]


def test_load_dir_aggregates_files(tmp_path: Path):
    _write(tmp_path / "a.jsonl", [{"role": "user", "content": "a"}])
    _write(tmp_path / "b.jsonl", [{"role": "user", "content": "b"}])
    corpus = load_dir(tmp_path)
    assert len(corpus) == 2
    assert {it.item_id for it in corpus} == {"a", "b"}


def test_load_dir_empty_directory(tmp_path: Path):
    corpus = load_dir(tmp_path)
    assert len(corpus) == 0


# ---------------------------------------------------------------------------
# LoadStats / load_*_with_stats — Item 1 (schema-drift accounting).
# ---------------------------------------------------------------------------


def test_load_jsonl_with_stats_counts_blank_json_notdict_norole(tmp_path: Path):
    """Each skip category is counted into its own bucket; parsed events
    into parsed_messages. total_lines includes blank lines."""
    file = tmp_path / "mixed.jsonl"
    _write_raw(
        file,
        '\n'                                            # blank
        '\n'                                            # blank
        'not parseable as json\n'                       # json_error
        '"a top-level string"\n'                        # not_dict
        '[1, 2, 3]\n'                                   # not_dict (list)
        '{"event": "start", "ts": 1}\n'                 # no_role
        '{"role": "user", "content": "hi"}\n'           # parsed
        '{"role": "tool", "name": "x", "content": "y"}\n'  # parsed
    )
    item, stats = load_jsonl_with_stats(file)
    assert stats.total_lines == 8
    assert stats.skipped_blank == 2
    assert stats.skipped_json_error == 1
    assert stats.skipped_not_dict == 2
    assert stats.skipped_no_role == 1
    assert stats.parsed_messages == 2
    assert stats.total_skipped == 6
    # skip_rate uses physical lines as denominator
    assert stats.skip_rate == pytest.approx(6 / 8)
    assert stats.parsed_rate == pytest.approx(2 / 8)
    assert len(item.messages) == 2


def test_load_jsonl_with_stats_records_distinct_shapes_only(tmp_path: Path):
    """10 identical no-role events produce sample of length 1, not 3."""
    file = tmp_path / "dups.jsonl"
    _write(
        file,
        [{"event": "tick", "ts": i} for i in range(10)],
    )
    _item, stats = load_jsonl_with_stats(file)
    assert stats.skipped_no_role == 10
    assert stats.sample_skipped_shapes == [("event", "ts")]


def test_load_jsonl_with_stats_caps_distinct_shapes_at_three(tmp_path: Path):
    """5 distinct shapes → only the first 3 retained (in observed order)."""
    file = tmp_path / "shapes.jsonl"
    _write(
        file,
        [
            {"a": 1, "b": 2},
            {"c": 3, "d": 4},
            {"e": 5, "f": 6},
            {"g": 7, "h": 8},   # over cap — must NOT appear
            {"i": 9, "j": 0},   # over cap — must NOT appear
        ],
    )
    _item, stats = load_jsonl_with_stats(file)
    assert len(stats.sample_skipped_shapes) == _MAX_SAMPLE_SHAPES == 3
    assert stats.sample_skipped_shapes == [
        ("a", "b"), ("c", "d"), ("e", "f"),
    ]


def test_load_jsonl_with_stats_sample_shapes_are_sorted_tuples(tmp_path: Path):
    """Emitter that produces keys in non-alpha order yields sorted tuples."""
    file = tmp_path / "sorted.jsonl"
    # json.dumps with default sort_keys=False preserves dict order. We
    # control the dict iteration order to verify the sort happens
    # inside _record_skipped_shape, not at JSON serialization.
    file.write_text(json.dumps({"c": 1, "a": 2, "b": 3}) + "\n")
    _item, stats = load_jsonl_with_stats(file)
    assert stats.sample_skipped_shapes == [("a", "b", "c")]
    # tuple, not list — pinned by dataclass type contract
    assert isinstance(stats.sample_skipped_shapes[0], tuple)


def test_load_jsonl_with_stats_zero_message_contract(tmp_path: Path):
    """File of only blank lines → empty CorpusItem + skip_rate from
    blanks (which counts toward total_lines). load_jsonl returns the
    same empty messages list."""
    file = tmp_path / "blanks.jsonl"
    _write_raw(file, "\n\n\n\n")
    item, stats = load_jsonl_with_stats(file)
    assert item.messages == []
    assert stats.total_lines == 4
    assert stats.skipped_blank == 4
    assert stats.skip_rate == 1.0
    # Confirm load_jsonl mirrors the empty-messages outcome
    assert load_jsonl(file).messages == []


def test_load_jsonl_with_stats_all_no_role_skip_rate_one(tmp_path: Path):
    """File where every non-blank line is no_role → skip_rate == 1.0
    (since there are no parsed events to dilute the count)."""
    file = tmp_path / "no_role.jsonl"
    _write(file, [{"ts": i} for i in range(5)])
    _item, stats = load_jsonl_with_stats(file)
    assert stats.skipped_no_role == 5
    assert stats.parsed_messages == 0
    assert stats.skip_rate == 1.0


def test_load_jsonl_with_stats_not_dict_sentinel(tmp_path: Path):
    """Non-dict events (strings, lists, numbers) are bucketed into
    skipped_not_dict and produce the <non-dict> sentinel shape."""
    file = tmp_path / "scalars.jsonl"
    _write_raw(file, '"string"\n[1, 2]\n42\n')
    _item, stats = load_jsonl_with_stats(file)
    assert stats.skipped_not_dict == 3
    assert stats.sample_skipped_shapes == [_NON_DICT_SENTINEL]


def test_load_dir_with_stats_returns_per_file(tmp_path: Path):
    """One LoadStats per matching file, in the same order as Corpus.items."""
    _write(tmp_path / "a.jsonl", [{"role": "user", "content": "a"}])
    _write(tmp_path / "b.jsonl", [{"role": "user", "content": "b"}])
    _write(tmp_path / "c.jsonl", [{"event": "skip"}])  # no_role
    corpus, stats_list = load_dir_with_stats(tmp_path)
    assert len(corpus) == 3
    assert len(stats_list) == 3
    # alpha order matches sorted glob
    assert [s.source for s in stats_list] == ["a.jsonl", "b.jsonl", "c.jsonl"]
    assert stats_list[2].skipped_no_role == 1


def test_load_dir_with_stats_empty_directory(tmp_path: Path):
    """Empty directory → empty corpus + empty stats list."""
    corpus, stats = load_dir_with_stats(tmp_path)
    assert len(corpus) == 0
    assert stats == []


def test_legacy_load_jsonl_byte_identical_against_v020_baseline(tmp_path: Path):
    """Snapshot test: load_jsonl behavior is byte-identical to v0.2.0
    semantics on a representative mixed input. Locks backward-compat
    against accidental drift while LoadStats observability is added.

    The expected output below was captured against the v0.2.0 baseline
    (commit a776932). If any test_load_jsonl_* test changes the expected
    parse outcome on this input, that's the signal to update this
    snapshot intentionally — not just rubber-stamp.
    """
    file = tmp_path / "baseline.jsonl"
    _write_raw(
        file,
        '\n'
        '{"event": "telemetry", "ts": 1.0}\n'
        '{"role": "system", "content": "you are an agent"}\n'
        'this line is not json at all\n'
        '{"role": "tool", "name": "git_diff", "content": "diff..."}\n'
        '{"role": "assistant", "tool_calls": [{"id": "1"}]}\n'
    )
    item = load_jsonl(file)
    assert item.item_id == "baseline"
    assert len(item.messages) == 3
    assert item.messages[0] == {"role": "system", "content": "you are an agent"}
    assert item.messages[1] == {
        "role": "tool", "name": "git_diff", "content": "diff...",
    }
    assert item.messages[2] == {
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "1"}],
    }
