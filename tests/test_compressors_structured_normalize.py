import json

from tokeless.compressors import compress_messages
from tokeless.compressors.structured_normalize import (
    StructuredNormalizeCompressor,
    _normalize_mypy,
)


MYPY_SAMPLE = """\
src/foo/bar.py:12:5: error: Bad return type [return-value]
src/foo/bar.py:12:5: note: Consider returning str(x) instead
src/foo/bar.py:48:9: error: Bad arg type [arg-type]
src/foo/baz.py:7:1: error: Missing module [import-not-found]
src/foo/baz.py:7:1: help: pip install types-x
Found 3 errors in 2 files (checked 47 source files)
"""


def test_mypy_normalizer_emits_one_json_per_error():
    out = _normalize_mypy(MYPY_SAMPLE)
    lines = out.splitlines()
    assert len(lines) == 3
    for ln in lines:
        d = json.loads(ln)
        assert d["tool"] == "mypy"
        assert d["level"] == "error"
        assert "file" in d and "line" in d and "msg" in d


def test_mypy_normalizer_carries_error_codes():
    out = _normalize_mypy(MYPY_SAMPLE)
    codes = {json.loads(ln).get("code") for ln in out.splitlines()}
    assert codes == {"return-value", "arg-type", "import-not-found"}


def test_mypy_normalizer_drops_summary_and_help_notes():
    out = _normalize_mypy(MYPY_SAMPLE)
    assert "Found 3 errors" not in out
    assert "Consider returning" not in out
    assert "pip install types-x" not in out


def test_mypy_normalizer_passes_unknown_format_through_unchanged():
    content = "this is not mypy output at all\njust some prose\n"
    assert _normalize_mypy(content) == content


def test_compressor_only_normalizes_matching_tool_name():
    msgs = [
        {"role": "tool", "name": "mypy", "content": MYPY_SAMPLE},
        {"role": "tool", "name": "ruff", "content": MYPY_SAMPLE},
    ]
    out, stats = compress_messages(msgs, "structured_normalize")
    assert stats.fires == 1
    assert stats.items_normalized == 1
    assert out[0]["content"] != MYPY_SAMPLE
    assert out[1]["content"] == MYPY_SAMPLE


def test_custom_normalizer_registration_via_subclass():
    def upper_normalizer(content: str) -> str:
        return content.upper()

    c = StructuredNormalizeCompressor(
        name="upper_test", normalizers={"shout": upper_normalizer}
    )
    msgs = [{"role": "tool", "name": "shout", "content": "hello"}]
    out, stats = c.apply(msgs)
    assert out[0]["content"] == "HELLO"
    assert stats.fires == 1
