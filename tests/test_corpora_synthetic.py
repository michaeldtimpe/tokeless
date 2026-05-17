from tokeless import corpora


def test_all_synthetic_corpora_register():
    expected = {
        "mypy_verbose",
        "git_diff_repeated",
        "bm25_overlap",
        "read_file_dup",
        "mixed_session",
        "long_session_recall",
        "adversarial_random_hex",
        "adversarial_unique_tokens",
        "adversarial_mypy_lookalike",
        "git_diff_repeated_shifted",
        "ruff_verbose",
        "adversarial_ruff_lookalike",
    }
    assert expected.issubset(set(corpora.names()))


def test_corpora_are_deterministic():
    a = corpora.get("mixed_session")
    b = corpora.get("mixed_session")
    assert [it.item_id for it in a] == [it.item_id for it in b]
    for ia, ib in zip(a, b):
        assert ia.messages == ib.messages


def test_corpora_have_items():
    for name in corpora.names():
        c = corpora.get(name)
        assert len(c) >= 1, f"{name} has no items"
        for item in c:
            assert item.item_id
            assert isinstance(item.messages, list)
            assert len(item.messages) > 0


def test_git_diff_repeated_actually_repeats():
    c = corpora.get("git_diff_repeated")
    item = c.items[0]
    diff_bodies = [
        m["content"] for m in item.messages
        if m.get("role") == "tool" and m.get("name") == "git_diff"
    ]
    assert len(diff_bodies) >= 2
    assert len(set(diff_bodies)) == 1


def test_long_session_recall_actually_has_recall_artifact():
    from tokeless.eval.runner import run_eval

    c = corpora.get("long_session_recall")
    item = c.items[0]
    artifact = "7c3b1f4e-2a8d-4e9f-b1c2-5d4e3f2a1b9c"

    tool_contents = [
        m["content"] for m in item.messages if m.get("role") == "tool"
    ]
    occurrences = [
        i for i, body in enumerate(tool_contents) if artifact in body
    ]
    assert occurrences, "recall artifact missing from corpus tool messages"
    assert occurrences[0] < len(tool_contents) // 3, (
        "artifact must appear in early turns"
    )
    assert occurrences[-1] >= 2 * len(tool_contents) // 3, (
        "artifact must also be referenced in late turns"
    )

    for compressor_id in (
        "noop",
        "exact_hash_dedup",
        "structured_normalize",
        "structural_dedup",
        "dedup_then_normalize",
    ):
        result = run_eval(c, compressor_id)
        all_content = "\n".join(
            m.get("content", "")
            for it in result.items
            for m in it.out_messages
        )
        assert artifact in all_content, (
            f"{compressor_id} dropped or rewrote the recall artifact"
        )


def test_adversarial_corpora_do_not_trigger_compression():
    """Dual of test_long_session_recall_actually_has_recall_artifact.

    `stats.fires == 0` MUST imply byte-identical output across the entire
    message sequence (the load-bearing contract clarification in
    ~/.claude/plans/jiggly-squishing-hopcroft.md). This test pins that
    invariant for every adversarial corpus × every non-noop compressor.
    """
    from tokeless.compressors import messages_bytes
    from tokeless.eval.runner import run_eval

    adversarial_names = (
        "adversarial_random_hex",
        "adversarial_unique_tokens",
        "adversarial_mypy_lookalike",
    )
    non_noop_compressors = (
        "exact_hash_dedup",
        "structured_normalize",
        "structural_dedup",
        "dedup_then_normalize",
    )

    for corpus_name in adversarial_names:
        c = corpora.get(corpus_name)
        in_bytes = sum(messages_bytes(item.messages) for item in c.items)
        for compressor_id in non_noop_compressors:
            result = run_eval(c, compressor_id)
            assert result.totals.fires == 0, (
                f"{compressor_id} fired on {corpus_name} "
                f"(fires={result.totals.fires})"
            )
            out_bytes = sum(
                messages_bytes(it.out_messages) for it in result.items
            )
            assert in_bytes == out_bytes, (
                f"{compressor_id} on {corpus_name}: bytes drifted "
                f"in={in_bytes} out={out_bytes} (no-fire must be byte-identical)"
            )


def test_git_diff_repeated_shifted_actually_repeats_structurally():
    """Mirror of test_git_diff_repeated_actually_repeats for the new corpus.

    Focus on corpus shape (anchor headers differ, body content identical,
    at least one turn has trailing-ws drift) rather than internal compressor
    mechanics. This way a future refactor of normalization logic doesn't
    force test churn here.
    """
    c = corpora.get("git_diff_repeated_shifted")
    item = c.items[0]
    tool_bodies = [
        m["content"] for m in item.messages if m.get("role") == "tool"
    ]
    assert len(tool_bodies) >= 3, "need at least three tool turns to demonstrate the win"

    headers = []
    for body in tool_bodies:
        for line in body.splitlines():
            if line.startswith("@@ "):
                headers.append(line)
                break
    assert len(set(headers)) == len(headers), (
        "all hunk headers must differ — that's the whole point of this corpus"
    )

    # At least one turn carries trailing-whitespace drift beyond what the
    # baseline body has.
    any_trailing_ws = any(
        any(line.endswith(" ") or line.endswith("\t") for line in body.splitlines())
        for body in tool_bodies
    )
    assert any_trailing_ws, "at least one turn should exercise trailing-ws drift"


def test_ruff_verbose_actually_has_ruff_diagnostics():
    """Mirror of test_git_diff_repeated_actually_repeats for the new corpus."""
    import re
    from tokeless.compressors.structured_normalize import _RUFF_LINE

    c = corpora.get("ruff_verbose")
    for item in c.items:
        ruff_msgs = [
            m for m in item.messages
            if m.get("role") == "tool" and m.get("name") == "ruff"
        ]
        assert ruff_msgs, f"{item.item_id} has no ruff tool messages"
        for m in ruff_msgs:
            matches = [
                line for line in m["content"].splitlines()
                if _RUFF_LINE.match(line)
            ]
            assert matches, (
                f"{item.item_id} ruff message has no _RUFF_LINE-matching "
                f"lines — corpus does not exercise the normalizer"
            )


def test_unknown_corpus_raises():
    try:
        corpora.get("nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError")
