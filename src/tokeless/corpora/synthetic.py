"""Synthetic luxe-shaped corpora.

Each generator produces a deterministic corpus that targets a specific
compressor archetype from the design memo:

- mypy_verbose       — verbose mypy diagnostics → Phase B normalizer wins
- git_diff_repeated  — same diff re-emitted across turns → Phase A dedup wins
- bm25_overlap       — overlapping search hits → Phase A dedup wins
- read_file_dup      — re-reads of the same file → Phase A dedup wins
- mixed_session      — interleaved roles + multiple redundancy patterns

Content shapes mimic real tool output formats (mypy line layout, unified
diff hunks, etc.) so normalizers can pattern-match in tests without
depending on a live luxe run.
"""

from __future__ import annotations

from tokeless.compressors import Message
from tokeless.corpora import Corpus, CorpusItem, register


_MYPY_BLOCK = """\
src/foo/bar.py:12:5: error: Incompatible return type "int", expected "str"  [return-value]
src/foo/bar.py:12:5: note: Consider returning str(x) instead
src/foo/bar.py:12:5: help: See https://mypy.readthedocs.io/en/stable/return-types.html
src/foo/bar.py:48:9: error: Argument 1 to "send" has incompatible type "None"; expected "Message"  [arg-type]
src/foo/bar.py:48:9: note: "send" defined at src/foo/bar.py:30
src/foo/baz.py:7:1: error: Cannot find implementation or library stub for module named "missing_dep"  [import-not-found]
src/foo/baz.py:7:1: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html
src/foo/baz.py:7:1: help: Hint: "python3 -m pip install types-missing_dep"
Found 3 errors in 2 files (checked 47 source files)
"""


_DIFF_HUNK = """\
diff --git a/src/foo/bar.py b/src/foo/bar.py
index 1a2b3c4..5d6e7f8 100644
--- a/src/foo/bar.py
+++ b/src/foo/bar.py
@@ -10,7 +10,7 @@ class Bar:
     def compute(self, x: int) -> str:
-        return x
+        return str(x)

     def send(self, msg: Message) -> None:
         self._queue.append(msg)
"""


_FILE_CONTENT = """\
class Bar:
    def __init__(self, queue: list[Message]):
        self._queue = queue

    def compute(self, x: int) -> str:
        return str(x)

    def send(self, msg: Message) -> None:
        self._queue.append(msg)
"""


def _msg(role: str, content: str, name: str = "") -> Message:
    m: Message = {"role": role, "content": content}
    if name:
        m["name"] = name
    return m


@register("mypy_verbose")
def _mypy_verbose() -> Corpus:
    items = [
        CorpusItem(
            item_id="single_block",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Run mypy and fix the errors."),
                _msg("tool", _MYPY_BLOCK, name="mypy"),
            ],
            description="One mypy run with 3 errors + verbose notes/help lines.",
        ),
        CorpusItem(
            item_id="repeated_runs",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Iterate on mypy until clean."),
                _msg("tool", _MYPY_BLOCK, name="mypy"),
                _msg("assistant", "I'll fix the return type first."),
                _msg("tool", _MYPY_BLOCK, name="mypy"),
                _msg("assistant", "And now the arg-type error."),
                _msg("tool", _MYPY_BLOCK, name="mypy"),
            ],
            description="Same mypy errors re-emitted across iterations.",
        ),
    ]
    return Corpus(
        name="mypy_verbose",
        description="Verbose mypy outputs targeting Phase B normalization.",
        items=items,
    )


@register("git_diff_repeated")
def _git_diff_repeated() -> Corpus:
    items = [
        CorpusItem(
            item_id="three_repeats",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Apply the patch and verify."),
                _msg("tool", _DIFF_HUNK, name="git_diff"),
                _msg("assistant", "Looks good, re-checking."),
                _msg("tool", _DIFF_HUNK, name="git_diff"),
                _msg("assistant", "Final verification."),
                _msg("tool", _DIFF_HUNK, name="git_diff"),
            ],
            description="Same git_diff hunk emitted three times in one session.",
        ),
    ]
    return Corpus(
        name="git_diff_repeated",
        description="Repeated diff hunks targeting Phase A exact-hash dedup.",
        items=items,
    )


@register("bm25_overlap")
def _bm25_overlap() -> Corpus:
    hit_a = "src/foo/bar.py:1-12\n" + _FILE_CONTENT
    hit_b = "src/foo/bar.py:1-12\n" + _FILE_CONTENT  # identical hit
    hit_c = "src/foo/baz.py:5-20\nclass Baz:\n    pass\n"
    items = [
        CorpusItem(
            item_id="duplicate_hits",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Find the Bar class."),
                _msg("tool", hit_a, name="bm25_search"),
                _msg("assistant", "Trying a related query."),
                _msg("tool", hit_b, name="bm25_search"),
                _msg("assistant", "And another."),
                _msg("tool", hit_c, name="bm25_search"),
            ],
            description="Three BM25 hits, two of which are byte-identical.",
        ),
    ]
    return Corpus(
        name="bm25_overlap",
        description="Overlapping retrieval hits targeting Phase A dedup.",
        items=items,
    )


@register("read_file_dup")
def _read_file_dup() -> Corpus:
    items = [
        CorpusItem(
            item_id="reread",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Inspect src/foo/bar.py."),
                _msg("tool", _FILE_CONTENT, name="read_file"),
                _msg("assistant", "Need to look again after editing."),
                _msg("tool", _FILE_CONTENT, name="read_file"),
            ],
            description="Same file content read twice without changes.",
        ),
    ]
    return Corpus(
        name="read_file_dup",
        description="Duplicate read_file outputs targeting Phase A dedup.",
        items=items,
    )


@register("mixed_session")
def _mixed_session() -> Corpus:
    messages: list[Message] = [
        _msg("system", "You are a coding agent operating on a Python repo."),
        _msg("user", "Make mypy clean."),
        _msg("tool", _MYPY_BLOCK, name="mypy"),
        _msg("assistant", "I'll fix the return type."),
        _msg("tool", _FILE_CONTENT, name="read_file"),
        _msg("assistant", "Applying patch."),
        _msg("tool", _DIFF_HUNK, name="git_diff"),
        _msg("tool", _MYPY_BLOCK, name="mypy"),
        _msg("assistant", "Re-running diff to confirm."),
        _msg("tool", _DIFF_HUNK, name="git_diff"),
        _msg("tool", _FILE_CONTENT, name="read_file"),
    ]
    items = [
        CorpusItem(
            item_id="full_loop",
            messages=messages,
            description=(
                "Interleaved roles with redundancy across mypy/diff/read_file. "
                "Exercises both Phase A (dedup) and Phase B (normalize)."
            ),
        ),
    ]
    return Corpus(
        name="mixed_session",
        description="Full agentic-loop shape with overlapping redundancy patterns.",
        items=items,
    )
