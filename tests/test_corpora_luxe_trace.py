import json
from pathlib import Path

import pytest

from tokeless.corpora.luxe_trace import load_dir, load_jsonl


def _write(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


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
