from tokeless.compressors import compress_messages
from tokeless.compressors.exact_hash_dedup import ExactHashDedupCompressor


def _diff_msg(body: str = "diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n") -> dict:
    return {"role": "tool", "name": "git_diff", "content": body}


def test_duplicate_tool_bodies_are_replaced_with_stub():
    body = "x" * 200  # well above min_bytes
    msgs = [
        {"role": "user", "content": "go"},
        {"role": "tool", "name": "git_diff", "content": body},
        {"role": "assistant", "content": "looks good"},
        {"role": "tool", "name": "git_diff", "content": body},
    ]
    out, stats = compress_messages(msgs, "exact_hash_dedup")
    assert len(out) == len(msgs)
    assert out[1]["content"] == body
    assert out[3]["content"].startswith("[duplicate of msg #1 tool=git_diff")
    assert stats.fires == 1
    assert stats.items_dropped == 1
    assert stats.bytes_in > stats.bytes_out


def test_distinct_bodies_kept_verbatim():
    msgs = [
        {"role": "tool", "name": "git_diff", "content": "x" * 200},
        {"role": "tool", "name": "git_diff", "content": "y" * 200},
    ]
    out, stats = compress_messages(msgs, "exact_hash_dedup")
    assert stats.fires == 0
    assert out == msgs


def test_below_min_bytes_not_deduped():
    c = ExactHashDedupCompressor(min_bytes=128)
    msgs = [
        {"role": "tool", "name": "x", "content": "short"},
        {"role": "tool", "name": "x", "content": "short"},
    ]
    out, stats = c.apply(msgs)
    assert stats.fires == 0
    assert out == msgs


def test_non_tool_roles_untouched():
    body = "a" * 200
    msgs = [
        {"role": "user", "content": body},
        {"role": "user", "content": body},
    ]
    out, stats = compress_messages(msgs, "exact_hash_dedup")
    assert stats.fires == 0
    assert out == msgs


def test_three_repeats_dedupes_two():
    body = "z" * 300
    msgs = [_diff_msg(body) for _ in range(3)]
    out, stats = compress_messages(msgs, "exact_hash_dedup")
    assert stats.fires == 2
    assert out[0]["content"] == body
    assert out[1]["content"].startswith("[duplicate of msg #0")
    assert out[2]["content"].startswith("[duplicate of msg #0")


def test_stub_records_original_bytes():
    body = "q" * 500
    msgs = [_diff_msg(body), _diff_msg(body)]
    out, _ = compress_messages(msgs, "exact_hash_dedup")
    assert f"bytes={len(body)}" in out[1]["content"]
