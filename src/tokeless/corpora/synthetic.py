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


_RUFF_BLOCK = """\
src/foo/bar.py:12:5: E501 Line too long (89 > 79)
   |
12 |     x = "this is an artificially long string that the lint catches" * 3
   |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ E501
   |
   help: Consider breaking the line or using a shorter constant.

src/foo/bar.py:48:9: F841 Local variable `unused_result` is assigned to but never used
   |
48 |         unused_result = compute_something_expensive()
   |         ^^^^^^^^^^^^^ F841
   |
   help: Remove the assignment if the value is truly unused.

src/foo/baz.py:7:1: F401 `os.path` imported but unused
   |
 7 | from os import path
   | ^^^^^^^^^^^^^^^^^^^ F401
   |
   help: Remove unused import.

Found 3 errors.
"""


@register("ruff_verbose")
def _ruff_verbose() -> Corpus:
    items = [
        CorpusItem(
            item_id="single_block",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Run ruff and fix the errors."),
                _msg("tool", _RUFF_BLOCK, name="ruff"),
            ],
            description="One ruff run with 3 errors + verbose snippets/help/summary.",
        ),
        CorpusItem(
            item_id="repeated_runs",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Iterate on ruff until clean."),
                _msg("tool", _RUFF_BLOCK, name="ruff"),
                _msg("assistant", "I'll fix the line-length issue first."),
                _msg("tool", _RUFF_BLOCK, name="ruff"),
                _msg("assistant", "And now the unused-variable error."),
                _msg("tool", _RUFF_BLOCK, name="ruff"),
            ],
            description="Same ruff errors re-emitted across iterations.",
        ),
    ]
    return Corpus(
        name="ruff_verbose",
        description="Verbose ruff outputs targeting Phase B normalization.",
        items=items,
    )


_RUFF_LOOKALIKE_BLOCKS = [
    # Lowercase code
    "src/foo/bar.py:12:5: e501 Line too long (89 > 79)\n"
    "src/foo/bar.py:48:9: f841 Unused local variable\n",
    # Missing colon between col and code
    "src/foo/bar.py:12:5 E501 Line too long (89 > 79)\n"
    "src/foo/baz.py:7:1 F401 Unused import\n",
    # Transposed code shape (digits before letters)
    "src/foo/qux.py:30:1: 501E Some message\n"
    "src/foo/qux.py:31:1: 401F Another message\n",
    # Numeric-only "codes"
    "src/foo/zed.py:5:5: 123 unused import\n"
    "src/foo/zed.py:6:5: 456 unused variable\n",
    # Prose-only lookalike
    "Ruff initialized for project root.\n"
    "Scanning 47 source files...\n"
    "Analysis complete in 0.42s.\n",
]


@register("adversarial_ruff_lookalike")
def _adversarial_ruff_lookalike() -> Corpus:
    """Content that LOOKS like ruff output but matches no _RUFF_LINE.

    name="mypy" is non-negotiable for `adversarial_mypy_lookalike`; the
    same holds here for ruff. Without name="ruff", the dispatcher
    short-circuits before invoking the normalizer, and fires == 0 is
    satisfied vacuously rather than testing the regex-miss branch.

    Pre-flight verified: each line in each block fails _RUFF_LINE
    matching (scratchpad-tested before locking the corpus).
    """
    items = [
        CorpusItem(
            item_id="lookalike_blocks",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Run ruff and review the output."),
                *[_msg("tool", body, name="ruff") for body in _RUFF_LOOKALIKE_BLOCKS],
            ],
            description=(
                "Five ruff-shaped outputs containing only near-miss lines. "
                "Dispatcher invokes the ruff normalizer (name='ruff') but "
                "the regex matches zero lines — tests the no-match return-"
                "unchanged branch."
            ),
        ),
    ]
    return Corpus(
        name="adversarial_ruff_lookalike",
        description=(
            "Ruff-shaped but unparseable content; structured_normalize must "
            "dispatch but return unchanged."
        ),
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


_SHIFTED_DIFF_BODY = """\
     def compute(self, x: int) -> str:
-        return x
+        return str(x)

     def send(self, msg: Message) -> None:
         self._queue.append(msg)
         self._notify()
"""


def _shifted_hunk(header: str, body: str = _SHIFTED_DIFF_BODY) -> str:
    return (
        "diff --git a/src/foo/bar.py b/src/foo/bar.py\n"
        "index 1a2b3c4..5d6e7f8 100644\n"
        "--- a/src/foo/bar.py\n"
        "+++ b/src/foo/bar.py\n"
        f"{header} class Bar:\n"
        f"{body}"
    )


# Turn 4: same body but with trailing whitespace appended to two body lines.
# Cheapest way to verify both transforms compose on a single corpus item.
_SHIFTED_DIFF_BODY_WS_DRIFT = (
    _SHIFTED_DIFF_BODY
    .replace("        return str(x)", "        return str(x)   ")
    .replace("         self._notify()", "         self._notify()  \t")
)


@register("git_diff_repeated_shifted")
def _git_diff_repeated_shifted() -> Corpus:
    items = [
        CorpusItem(
            item_id="four_shifted",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Apply the patch and verify."),
                _msg(
                    "tool",
                    _shifted_hunk("@@ -10,7 +10,7 @@"),
                    name="git_diff",
                ),
                _msg("assistant", "Looks good — re-checking after unrelated edits."),
                _msg(
                    "tool",
                    _shifted_hunk("@@ -42,7 +42,7 @@"),
                    name="git_diff",
                ),
                _msg("assistant", "And again with the omitted-count anchor shape."),
                _msg(
                    "tool",
                    _shifted_hunk("@@ -8 +8 @@"),
                    name="git_diff",
                ),
                _msg("assistant", "Final verification after another file-size shift."),
                _msg(
                    "tool",
                    _shifted_hunk(
                        "@@ -100,7 +100,7 @@", body=_SHIFTED_DIFF_BODY_WS_DRIFT
                    ),
                    name="git_diff",
                ),
            ],
            description=(
                "Same diff hunk re-emitted four times with shifted anchors. "
                "Turn 4 also carries trailing-whitespace drift on body lines. "
                "exact_hash_dedup catches none; structural_dedup catches three."
            ),
        ),
    ]
    return Corpus(
        name="git_diff_repeated_shifted",
        description=(
            "Same diff body re-emitted with shifted unified-diff anchors "
            "(and trailing-ws drift on one turn). Demonstrates the "
            "structural_dedup win over exact_hash_dedup."
        ),
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


_RECALL_UUID = "7c3b1f4e-2a8d-4e9f-b1c2-5d4e3f2a1b9c"

_TASK_CREATE = (
    f'{{"task_id": "{_RECALL_UUID}", '
    f'"title": "Fix mypy errors in bar.py", "status": "open"}}'
)
_TASK_LIST = (
    f'[{{"task_id": "{_RECALL_UUID}", '
    f'"title": "Fix mypy errors in bar.py", "status": "in_progress"}}]'
)
_TASK_UPDATE = f'{{"task_id": "{_RECALL_UUID}", "status": "in_review"}}'
_TASK_COMPLETE = f'{{"task_id": "{_RECALL_UUID}", "status": "done"}}'

# Distinct per-turn content so exact-hash dedup does NOT trivially fire on
# bulk turns; the corpus's job is to exercise long-range recall of the
# UUID artifact, not redundancy that other corpora already cover.
_MYPY_TURN_5 = _MYPY_BLOCK
_MYPY_TURN_11 = """\
src/foo/bar.py:48:9: error: Argument 1 to "send" has incompatible type "None"; expected "Message"  [arg-type]
src/foo/bar.py:48:9: note: "send" defined at src/foo/bar.py:30
src/foo/baz.py:7:1: error: Cannot find implementation or library stub for module named "missing_dep"  [import-not-found]
Found 2 errors in 2 files (checked 47 source files)
"""
_MYPY_TURN_19 = "Success: no issues found in 47 source files\n"

_DIFF_TURN_9 = _DIFF_HUNK
_DIFF_TURN_17 = """\
diff --git a/src/foo/bar.py b/src/foo/bar.py
index 5d6e7f8..9a0b1c2 100644
--- a/src/foo/bar.py
+++ b/src/foo/bar.py
@@ -46,7 +46,7 @@ class Bar:
     def send(self, msg: Message) -> None:
-        self._queue.append(msg)
+        if msg is None:
+            return
+        self._queue.append(msg)
"""

_FILE_TURN_7 = _FILE_CONTENT
_FILE_TURN_15 = """\
class Bar:
    def __init__(self, queue: list[Message]):
        self._queue = queue

    def compute(self, x: int) -> str:
        return str(x)

    def send(self, msg: Message) -> None:
        self._queue.append(msg)

    # patched return type — first fix applied
"""


@register("long_session_recall")
def _long_session_recall() -> Corpus:
    messages: list[Message] = [
        _msg("system", "You are a coding agent operating on a Python repo."),
        _msg("user", "Track a task to fix the mypy errors in bar.py, then iterate until clean."),
        _msg("tool", _TASK_CREATE, name="task_tracker"),
        _msg("assistant", "Task created. Starting with the mypy run."),
        _msg("tool", _MYPY_TURN_5, name="mypy"),
        _msg("assistant", "Found three errors. Reading bar.py."),
        _msg("tool", _FILE_TURN_7, name="read_file"),
        _msg("assistant", "Now applying the return-type fix."),
        _msg("tool", _DIFF_TURN_9, name="git_diff"),
        _msg("assistant", "Re-running mypy."),
        _msg("tool", _MYPY_TURN_11, name="mypy"),
        _msg("assistant", "Checking task status."),
        _msg("tool", _TASK_LIST, name="task_tracker"),
        _msg("assistant", "Still in progress. Moving on to arg-type fix."),
        _msg("tool", _FILE_TURN_15, name="read_file"),
        _msg("assistant", "Applying second patch."),
        _msg("tool", _DIFF_TURN_17, name="git_diff"),
        _msg("tool", _TASK_UPDATE, name="task_tracker"),
        _msg("assistant", "Final mypy run."),
        _msg("tool", _MYPY_TURN_19, name="mypy"),
        _msg("assistant", "Clean. Marking task done."),
        _msg("tool", _TASK_COMPLETE, name="task_tracker"),
    ]
    items = [
        CorpusItem(
            item_id="task_thread",
            messages=messages,
            description=(
                "22-turn agent session where a task UUID emitted in turn 3 "
                "is referenced again in turns 13, 17, and 21. Exercises "
                "long-range recall over interleaved mypy / diff / read_file "
                "traffic with a deterministic, exact-match-recoverable artifact."
            ),
        ),
    ]
    return Corpus(
        name="long_session_recall",
        description=(
            "Long agent session with a deterministic recall-critical artifact "
            "(UUID) that must survive every compressor in the roadmap."
        ),
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


# ---------------------------------------------------------------------------
# Adversarial corpora — content shapes designed NOT to compress.
#
# These exercise the "no fire" branch of the integrity contract:
# `stats.fires == 0` MUST imply byte-identical output. Together with
# `long_session_recall` (preservation-under-firing), this is the inverse
# property that closes the contract.
#
# Hex literals are pre-generated from /dev/urandom and pasted as string
# literals — no `random` import, no patterns. See plan
# jiggly-squishing-hopcroft.md for the rationale.
# ---------------------------------------------------------------------------

_HEX_BLOB_1 = (
    "cf399cd4d6af609e8d84f90de7ec00ef7981d4e14f13c74fb7a9e4f9d6ccbc36"
    "83a1fb1acb1d0bb81f3d450e333c6bd98e7240bfe47055384c6fba6c82c39c64"
    "296320c88b556f9ed05c7d7c2f7f2f1bbff9794de854f7bdfd55af62f46abd0e"
    "457998d6faf7082abd7bb429b17531ffe5e1cb2faa0c14798db33f7dcd9dae31"
)
_HEX_BLOB_2 = (
    "dc64ca649dfd343290a23a837c5a5911bf5cc8ffcfeb6825b381f65c535ca272"
    "7a886aba3db18c3d056fe4cc22dde9e61ca85d00fdfa7eddc2855f0f163da780"
    "17f1d991a8224d4ad5057217b98424ca9254b953d0139f70401038405352ba9b"
    "c9f34e38274afce6bf8783d82f1c6855a82c863045f35b74aa4d598ed9cdae34"
)
_HEX_BLOB_3 = (
    "710d2beb29cf71d99923b583768440fcf27f7e72de32d71b5f25cb10121fa9c8"
    "cb229ec7bd8de47b2fd406f8aa88d1477ad6470eaea034c5a2781104e3ba5dae"
    "0e921fe4b70e678c3a3d0aca67f00f1e2ca874e955e09edafa87bbf7dfeb5901"
    "418e2a4531e0186591c6757f7aa02f961920bbbf461ecac16c431af717bef386"
)
_HEX_BLOB_4 = (
    "3ed2bacaf01b4f047240c626fa768ca46b38642e2c5d79c583299e075023451c"
    "a040d93da99bb9f9fcd0c0a7c8942305c870c546589911cef1b1dd25761d832d"
    "80ccc8f460d538e1ee33cc5b192bfbfabd3383535cd550ef2decbe5a5f330816"
    "9b21daa6aec733be0e26ee19a828ceb3dc28b72f861278f8b36b842e992b60ae"
)
_HEX_BLOB_5 = (
    "2b9f0068012f15725a6fd9974c46f689850201d2fa4140b1f608f5a483219669"
    "c68eca37d17307fb10a8cabdcc2a5263a785627f9c4f709247614b3a6a92217a"
    "362c964609febeda15058c88cfd53ba0e138dc224417793e9f814ae1bf635773"
    "06de75a20d5c2315be3f9ae044833f7af44d9c5fb3e0b0b77087a89f183ce5be"
)


@register("adversarial_random_hex")
def _adversarial_random_hex() -> Corpus:
    """High-entropy hex bodies — every message unique, no normalizer dispatch.

    Tool name is deliberately NOT in structured_normalize's registry, so
    that compressor passes through via the dispatcher tool-name miss
    (structured_normalize.py:126-129). The valuable signal is
    exact_hash_dedup's no-fire branch: per-message uniqueness + high
    entropy defeats both hash dedup and any future fuzzy-hash compressor.
    """
    bodies = [_HEX_BLOB_1, _HEX_BLOB_2, _HEX_BLOB_3, _HEX_BLOB_4, _HEX_BLOB_5]
    items = [
        CorpusItem(
            item_id="random_hex",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Inspect the blob outputs."),
                *[_msg("tool", body, name="random_blob") for body in bodies],
            ],
            description=(
                "Five high-entropy hex blobs, one per turn. Tests that "
                "exact_hash_dedup does NOT fire on unique content."
            ),
        ),
    ]
    return Corpus(
        name="adversarial_random_hex",
        description="High-entropy non-redundant content; no compressor should fire.",
        items=items,
    )


@register("adversarial_unique_tokens")
def _adversarial_unique_tokens() -> Corpus:
    """Plausible-looking but per-message-unique structured tool output.

    Complement to adversarial_random_hex: same no-fire target for
    exact_hash_dedup, but under realistic low-entropy content shape rather
    than entropy-heavy hex. A future near-duplicate detector might dismiss
    high-entropy hex as obviously novel but still mistakenly fire on
    structured content that "looks" repetitive across messages. This
    corpus guards against that.

    Tool name is deliberately NOT in structured_normalize's registry —
    same dispatcher-miss caveat as adversarial_random_hex. If a future
    review finds this corpus collapsing into adversarial_random_hex's
    coverage axis, one can be dropped as an explicit decision.
    """
    bodies = [
        '{"event_id": "evt-a1c2", "ts": "2026-05-01T09:15:23Z", "path": "src/foo/alpha.py", "size": 1024}',
        '{"event_id": "evt-b3d4", "ts": "2026-05-02T14:42:11Z", "path": "src/foo/bravo.py", "size": 2048}',
        '{"event_id": "evt-c5e6", "ts": "2026-05-03T08:07:55Z", "path": "src/foo/charlie.py", "size": 512}',
        '{"event_id": "evt-d7f8", "ts": "2026-05-04T22:33:09Z", "path": "src/foo/delta.py", "size": 4096}',
        '{"event_id": "evt-e9a0", "ts": "2026-05-05T11:18:47Z", "path": "src/foo/echo.py", "size": 768}',
    ]
    items = [
        CorpusItem(
            item_id="event_stream",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Process the event log entries."),
                *[_msg("tool", body, name="event_log") for body in bodies],
            ],
            description=(
                "Five structurally similar but per-message-unique JSON event "
                "lines. Tests that exact_hash_dedup does NOT fire on novel "
                "structured content."
            ),
        ),
    ]
    return Corpus(
        name="adversarial_unique_tokens",
        description="Realistic-shape non-redundant content; no compressor should fire.",
        items=items,
    )


_MYPY_LOOKALIKE_BLOCK_1 = """\
Type checking source files...
src/foo/bar.py:12:5: fatal: Wrong severity token
src/foo/bar.py:48:9: INFO: Lookalike severity that mypy does not emit
Building dependency graph...
"""

_MYPY_LOOKALIKE_BLOCK_2 = """\
src/foo/baz.py:abc:5: error: Non-numeric line number
src/foo/baz.py:-12:5: error: Negative line number
Skipped 0 files; nothing to report.
"""

_MYPY_LOOKALIKE_BLOCK_3 = """\
src/foo/qux.py:12:5 error: Missing colon between col and level
src/foo/qux.py: error: Missing line and column entirely
Static analysis complete in 0.42s.
"""

_MYPY_LOOKALIKE_BLOCK_4 = """\
src/foo/zed.py:12:5: Error: Capital-E severity (mypy uses lowercase)
src/foo/zed.py:30:1: Warning: Capital-W severity (mypy uses lowercase)
No issues to report at this time.
"""

_MYPY_LOOKALIKE_BLOCK_5 = """\
Type checker initialized.
Reading config from pyproject.toml.
Walking source tree (47 files)...
Done.
"""


@register("adversarial_mypy_lookalike")
def _adversarial_mypy_lookalike() -> Corpus:
    """Content that LOOKS like mypy output but matches no _MYPY_LINE.

    `name="mypy"` is non-negotiable: without it, the dispatcher at
    structured_normalize.py:126 short-circuits before invoking the
    normalizer, and fires == 0 is satisfied vacuously rather than testing
    the regex-miss branch at structured_normalize.py:93-94.

    Each block includes at least one near-miss line that almost matches
    _MYPY_LINE except for one invalid token (wrong severity, non-numeric
    or negative line number, missing colon, capitalized level). Verified
    against _MYPY_LINE before locking in — no line in this corpus matches.
    """
    bodies = [
        _MYPY_LOOKALIKE_BLOCK_1,
        _MYPY_LOOKALIKE_BLOCK_2,
        _MYPY_LOOKALIKE_BLOCK_3,
        _MYPY_LOOKALIKE_BLOCK_4,
        _MYPY_LOOKALIKE_BLOCK_5,
    ]
    items = [
        CorpusItem(
            item_id="lookalike_blocks",
            messages=[
                _msg("system", "You are a coding agent."),
                _msg("user", "Run mypy and review the output."),
                *[_msg("tool", body, name="mypy") for body in bodies],
            ],
            description=(
                "Five mypy-shaped outputs containing only near-miss lines. "
                "Dispatcher invokes the mypy normalizer (name='mypy') but "
                "the regex matches zero lines — tests the no-match return-"
                "unchanged branch."
            ),
        ),
    ]
    return Corpus(
        name="adversarial_mypy_lookalike",
        description=(
            "Mypy-shaped but unparseable content; structured_normalize must "
            "dispatch but return unchanged."
        ),
        items=items,
    )
