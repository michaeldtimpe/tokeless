from tokeless.compressors import compress_messages
from tokeless.compressors.structural_dedup import StructuralDedupCompressor


def _hunk(header: str, body: str | None = None) -> str:
    """Build a unified-diff message with the given hunk header and body."""
    default_body = (
        "     def compute(self, x: int) -> str:\n"
        "-        return x\n"
        "+        return str(x)\n"
        "\n"
        "     def send(self, msg) -> None:\n"
        "         self._queue.append(msg)\n"
    )
    return (
        "diff --git a/src/foo/bar.py b/src/foo/bar.py\n"
        "index 1a2b3c4..5d6e7f8 100644\n"
        "--- a/src/foo/bar.py\n"
        "+++ b/src/foo/bar.py\n"
        f"{header} class Bar:\n"
        f"{body if body is not None else default_body}"
    )


def _tool(content: str, name: str = "git_diff") -> dict:
    return {"role": "tool", "name": name, "content": content}


# ----- Win cases -----------------------------------------------------------


def test_byte_identical_duplicates_still_dedup():
    """exact_hash behavior preserved as a strict subset."""
    body = "x" * 200
    msgs = [_tool(body), _tool(body)]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1
    assert out[1]["content"].startswith("[duplicate of msg #0 tool=git_diff")


def test_shifted_anchors_with_counts_dedup():
    msgs = [
        _tool(_hunk("@@ -10,7 +10,7 @@")),
        _tool(_hunk("@@ -42,7 +42,7 @@")),
    ]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1
    assert out[1]["content"].startswith("[duplicate of msg #0 tool=git_diff")
    assert any("anchor-canon" in n for n in stats.notes)


def test_shifted_anchors_with_omitted_counts_dedup():
    """`@@ -10 +10 @@` shape (no comma-count) — regex variant coverage."""
    msgs = [
        _tool(_hunk("@@ -10,7 +10,7 @@")),
        _tool(_hunk("@@ -8 +8 @@")),
    ]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1
    assert any("anchor-canon" in n for n in stats.notes)


def test_shifted_anchors_with_zero_counts_dedup():
    """`@@ -10,0 +10,4 @@` shape — pure-insertion / pure-deletion hunks."""
    msgs = [
        _tool(_hunk("@@ -10,0 +10,4 @@")),
        _tool(_hunk("@@ -50,0 +50,4 @@")),
    ]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1


def test_trailing_whitespace_only_difference_dedups():
    """Cosmetic trailing-ws drift on body lines should not defeat dedup."""
    body = "     def f():\n         return 1\n"
    body_ws = "     def f():   \n         return 1  \t\n"
    msgs = [_tool(_hunk("@@ -1,2 +1,2 @@", body)), _tool(_hunk("@@ -1,2 +1,2 @@", body_ws))]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1
    assert any("trailing-ws" in n for n in stats.notes)


def test_combined_anchor_and_trailing_ws_drift_dedups():
    body = "     def f():\n         return 1\n"
    body_ws = "     def f():   \n         return 1  \n"
    msgs = [
        _tool(_hunk("@@ -1,2 +1,2 @@", body)),
        _tool(_hunk("@@ -99,2 +99,2 @@", body_ws)),
    ]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1
    note = " ".join(stats.notes)
    assert "anchor-canon" in note and "trailing-ws" in note


# ----- False-positive guards (load-bearing) --------------------------------


def test_minimally_different_context_does_not_dedup():
    """Same hunk body, identical anchors after canon, but distinct context lines."""
    # Hand-build to guarantee context-line difference is the ONLY semantic diff.
    msg_a = (
        "diff --git a/src/x.py b/src/x.py\n"
        "--- a/src/x.py\n"
        "+++ b/src/x.py\n"
        "@@ -10,3 +10,3 @@ class Bar:\n"
        "     def f(self):\n"
        "-        return 1\n"
        "+        return 2\n"
    )
    msg_b = (
        "diff --git a/src/x.py b/src/x.py\n"
        "--- a/src/x.py\n"
        "+++ b/src/x.py\n"
        "@@ -42,3 +42,3 @@ class Baz:\n"  # ← Baz, not Bar
        "     def f(self):\n"
        "-        return 1\n"
        "+        return 2\n"
    )
    msgs = [_tool(msg_a), _tool(msg_b)]
    _, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 0, (
        "minimally different context line MUST defeat dedup — guard against "
        "over-broadening of the equivalence class"
    )


def test_anonymous_context_across_different_files_does_not_dedup():
    """Bare `{` or empty context shouldn't allow cross-file collapse."""
    body = "     handler();\n     break;\n"
    msg_a = (
        "diff --git a/src/foo.py b/src/foo.py\n"
        "--- a/src/foo.py\n"
        "+++ b/src/foo.py\n"
        "@@ -10,2 +10,2 @@ \n"  # empty context
        f"{body}"
    )
    msg_b = (
        "diff --git a/src/bar.py b/src/bar.py\n"  # ← different file
        "--- a/src/bar.py\n"
        "+++ b/src/bar.py\n"
        "@@ -10,2 +10,2 @@ \n"  # empty context (identical to msg_a's)
        f"{body}"
    )
    msgs = [_tool(msg_a), _tool(msg_b)]
    _, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 0, (
        "file headers MUST contribute to the dedup key — anonymous context "
        "must not allow cross-file collapse"
    )


def test_internal_whitespace_difference_does_not_dedup():
    """Indentation is semantic; 4-space vs 8-space must remain distinct."""
    body_4 = "    return 1\n"
    body_8 = "        return 1\n"
    msgs = [_tool(_hunk("@@ -1,1 +1,1 @@", body_4)), _tool(_hunk("@@ -1,1 +1,1 @@", body_8))]
    _, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 0


def test_different_line_endings_do_not_dedup():
    """Defensive: naked rstrip() would conflate \\n and \\r\\n."""
    body_lf = "     return 1\n     return 2\n"
    body_crlf = "     return 1\r\n     return 2\r\n"
    msgs = [
        _tool(_hunk("@@ -1,2 +1,2 @@", body_lf)),
        _tool(_hunk("@@ -1,2 +1,2 @@", body_crlf)),
    ]
    _, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 0


def test_markdown_trailing_ws_pins_current_lossy_behavior():
    """Markdown line-break syntax (two trailing spaces) currently dedups.

    This is a v1 trade-off acknowledged in the plan's risk table; the test
    pins the current behavior so a future refinement is deliberate. If
    real luxe-trace seeding shows markdown content matters for tokeless's
    target shape, revisit with a per-content-type policy.
    """
    body_with_md_break = "line one  \nline two\n"  # two trailing spaces = <br>
    body_without = "line one\nline two\n"
    # Make bodies long enough to clear min_bytes via padding the header preamble.
    pad = "x" * 200 + "\n"
    msgs = [
        _tool(pad + body_with_md_break),
        _tool(pad + body_without),
    ]
    _, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1, (
        "current v1 behavior: trailing-ws strip treats markdown line breaks "
        "as cosmetic. Test pins this so future refinement is deliberate."
    )


# ----- Threshold / scope tests ---------------------------------------------


def test_below_min_bytes_not_deduped():
    c = StructuralDedupCompressor(min_bytes=128)
    msgs = [_tool("short"), _tool("short")]
    out, stats = c.apply(msgs)
    assert stats.fires == 0
    assert out == msgs


def test_non_tool_roles_untouched():
    body = "a" * 200
    msgs = [
        {"role": "user", "content": body},
        {"role": "user", "content": body},
    ]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 0
    assert out == msgs


# ----- Stub format / observability -----------------------------------------


def test_stub_records_original_pre_normalization_bytes():
    """Stub's `bytes=` is the original message length, not the normalized one."""
    body = _hunk("@@ -10,7 +10,7 @@") + ("   " * 50)  # add trailing ws padding
    canonical = _hunk("@@ -10,7 +10,7 @@")
    msgs = [_tool(canonical), _tool(body)]
    out, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1
    original_byte_len = len(body.encode("utf-8"))
    assert f"bytes={original_byte_len}" in out[1]["content"]


def test_stats_notes_record_byte_identical_dedup_silently():
    """No transform fired → no note (byte-identical equiv class doesn't need one)."""
    body = "x" * 200
    msgs = [_tool(body), _tool(body)]
    _, stats = compress_messages(msgs, "structural_dedup")
    assert stats.fires == 1
    assert stats.notes == [], (
        "byte-identical dedups should not generate transform notes — keeps "
        "the diagnostic signal focused on cases where structural normalization "
        "actually contributed"
    )
