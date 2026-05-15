from tokeless import corpora


def test_all_synthetic_corpora_register():
    expected = {
        "mypy_verbose",
        "git_diff_repeated",
        "bm25_overlap",
        "read_file_dup",
        "mixed_session",
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


def test_unknown_corpus_raises():
    try:
        corpora.get("nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError")
