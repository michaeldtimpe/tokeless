import json

from tokeless.compressors import compress_messages
from tokeless.compressors.structured_normalize import (
    StructuredNormalizeCompressor,
    _normalize_mypy,
    _normalize_ruff,
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


RUFF_SAMPLE = """\
src/foo/bar.py:12:5: E501 Line too long (89 > 79)
   |
12 |     x = "a" * 90
   |     ^^^^^^^^^^^^ E501
   |
   help: Consider breaking the line.

src/foo/bar.py:48:9: F841 Local variable `x` is assigned to but never used
   |
48 |         x = compute()
   |         ^ F841
   |

src/foo/baz.py:7:1: F401 `os.path` imported but unused

src/foo/qux.py:30:1: UP006 Use `list` instead of `List`

src/foo/zed.py:5:5: RUF013 PEP 484 prohibits implicit Optional

Found 5 errors.
"""


def test_ruff_normalizer_emits_one_json_per_diagnostic():
    out = _normalize_ruff(RUFF_SAMPLE)
    lines = out.splitlines()
    assert len(lines) == 5
    for ln in lines:
        d = json.loads(ln)
        assert d["tool"] == "ruff"
        assert "file" in d and "line" in d and "col" in d
        assert "code" in d and "msg" in d


def test_ruff_normalizer_carries_rule_codes():
    out = _normalize_ruff(RUFF_SAMPLE)
    codes = {json.loads(ln)["code"] for ln in out.splitlines()}
    assert codes == {"E501", "F841", "F401", "UP006", "RUF013"}


def test_ruff_normalizer_drops_summary_and_snippets():
    out = _normalize_ruff(RUFF_SAMPLE)
    assert "Found 5 errors" not in out
    assert "Consider breaking" not in out
    assert "compute()" not in out
    assert "^^^^" not in out


def test_ruff_normalizer_passes_unknown_format_through_unchanged():
    content = "this is not ruff output at all\njust some prose\n"
    assert _normalize_ruff(content) == content


def test_ruff_normalizer_drops_unmatched_lines_when_diagnostics_present():
    """Explicit pin of the 'swallow' contract: prose mixed with diagnostics is dropped."""
    mixed = (
        "Some prose at the top of the message.\n"
        "src/foo/bar.py:12:5: E501 Line too long\n"
        "More unrelated prose in the middle.\n"
        "src/foo/baz.py:7:1: F401 Unused import\n"
        "Closing remarks that ruff would never emit.\n"
    )
    out = _normalize_ruff(mixed)
    lines = out.splitlines()
    assert len(lines) == 2
    assert all("prose" not in ln and "remarks" not in ln for ln in lines)
    # JSON lines for the two real diagnostics:
    assert json.loads(lines[0])["code"] == "E501"
    assert json.loads(lines[1])["code"] == "F401"


def test_ruff_normalizer_is_idempotent():
    """normalize(normalize(x)) == normalize(x) — future-proofs multi-pass orchestration.

    JSON output should fail _RUFF_LINE on the second pass and trigger the
    "no match → identity" branch.
    """
    once = _normalize_ruff(RUFF_SAMPLE)
    twice = _normalize_ruff(once)
    assert once == twice


def test_dispatcher_skips_dedup_stubs():
    """Pins the stub-isolation guard.

    A dedup back-reference stub on a tool message named "mypy" must NOT
    be parsed by the mypy normalizer. The dispatcher short-circuits
    before regex evaluation. Defensive against future loose-regex
    normalizers that might happen to match stub strings.
    """
    stub = "[duplicate of msg #0 tool=mypy hash=deadbeef1234 bytes=100]"
    msgs = [{"role": "tool", "name": "mypy", "content": stub}]
    out, stats = compress_messages(msgs, "structured_normalize")
    assert stats.fires == 0
    assert out == msgs


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
