from tokeless import compressors as cmod
from tokeless.compressors import (
    BYTES_PER_TOKEN_PROXY,
    CompressorStats,
    NoOpCompressor,
    compress_messages,
    estimate_decode_seconds,
    estimate_tokens,
    messages_bytes,
)


def test_registry_has_noop_and_stubs():
    names = cmod.names()
    assert "noop" in names
    assert "exact_hash_dedup" in names
    assert "structured_normalize" in names


def test_noop_returns_input_unchanged():
    msgs = [
        {"role": "system", "content": "you are a coding agent"},
        {"role": "tool", "name": "git_diff", "content": "diff --git ..."},
    ]
    out, stats = compress_messages(msgs, "noop")
    assert out == msgs
    assert stats.fires == 0
    assert stats.bytes_in == stats.bytes_out


def test_compress_messages_empty_id_is_passthrough():
    msgs = [{"role": "user", "content": "hi"}]
    out, stats = compress_messages(msgs, None)
    assert out == msgs
    assert stats.name == "noop"


def test_compress_messages_unknown_id_raises():
    try:
        compress_messages([], "does_not_exist")
    except KeyError as e:
        assert "does_not_exist" in str(e)
    else:
        raise AssertionError("expected KeyError")


def test_messages_bytes_handles_missing_content():
    assert messages_bytes([{"role": "assistant"}]) == 0
    assert messages_bytes([{"role": "tool", "content": "abc"}]) == 3


def test_compressor_stats_merge_accumulates():
    a = CompressorStats(name="x", fires=1, bytes_in=100, bytes_out=80, latency_s=0.01)
    b = CompressorStats(name="x", fires=2, bytes_in=200, bytes_out=150, latency_s=0.02)
    a.merge(b)
    assert a.fires == 3
    assert a.bytes_in == 300
    assert a.bytes_out == 230
    assert abs(a.latency_s - 0.03) < 1e-9
    assert a.bytes_saved == 70


def test_tokens_estimate_uses_bytes_per_token_proxy():
    assert BYTES_PER_TOKEN_PROXY == 4
    assert estimate_tokens(100) == 25
    assert estimate_tokens(0) == 0
    assert estimate_tokens(3) == 0  # integer floor


def test_compressor_stats_tokens_properties():
    s = CompressorStats(name="x", bytes_in=400, bytes_out=200)
    assert s.tokens_in_estimate == 100
    assert s.tokens_out_estimate == 50
    assert s.tokens_saved_estimate == 50


def test_decode_seconds_handles_zero_or_negative_rate():
    """Guard against division by zero / nonsense rates."""
    assert estimate_decode_seconds(100, 0) == 0.0
    assert estimate_decode_seconds(100, -1.0) == 0.0
    assert estimate_decode_seconds(100, 100.0) == 1.0
    assert estimate_decode_seconds(50, 100.0) == 0.5


def test_double_registration_rejected():
    try:
        cmod.register(NoOpCompressor())
    except ValueError as e:
        assert "noop" in str(e)
    else:
        raise AssertionError("expected ValueError on duplicate registration")
