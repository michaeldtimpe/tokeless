"""Compressor protocol + registry.

A Compressor transforms a list of conversation messages and returns the
transformed list together with per-application stats. Compressors must be
deterministic for a given input (the design memo's binary keep/revert gate
relies on stable measurement).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypedDict


class Message(TypedDict, total=False):
    role: str
    name: str
    content: str
    tool_call_id: str
    tool_calls: list[dict[str, Any]]


@dataclass
class CompressorStats:
    name: str = ""
    fires: int = 0
    messages_in: int = 0
    messages_out: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    items_dropped: int = 0
    items_normalized: int = 0
    latency_s: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def bytes_saved(self) -> int:
        return self.bytes_in - self.bytes_out

    @property
    def compression_ratio(self) -> float:
        if self.bytes_in == 0:
            return 1.0
        return self.bytes_out / self.bytes_in

    @property
    def tokens_in_estimate(self) -> int:
        return estimate_tokens(self.bytes_in)

    @property
    def tokens_out_estimate(self) -> int:
        return estimate_tokens(self.bytes_out)

    @property
    def tokens_saved_estimate(self) -> int:
        return self.tokens_in_estimate - self.tokens_out_estimate

    def merge(self, other: "CompressorStats") -> None:
        self.fires += other.fires
        self.messages_in += other.messages_in
        self.messages_out += other.messages_out
        self.bytes_in += other.bytes_in
        self.bytes_out += other.bytes_out
        self.items_dropped += other.items_dropped
        self.items_normalized += other.items_normalized
        self.latency_s += other.latency_s
        self.notes.extend(other.notes)


class Compressor(Protocol):
    name: str

    def apply(
        self, messages: list[Message]
    ) -> tuple[list[Message], CompressorStats]: ...


# Conservative bytes-to-tokens proxy. Matches the rule-of-thumb cited in
# RESUME.md item #4: ~4 bytes/token for typical English-ish tool output.
# Real ratios vary by content shape (hex blobs ≈ 2:1; dense JSON ≈ 3:1;
# English prose ≈ 4:1; code is mixed). The proxy is intentionally a
# single value so the number is deterministic and dependency-free; a
# real tokenizer (tiktoken / sentence-transformers) would be
# model-specific and is deferred.
BYTES_PER_TOKEN_PROXY = 4


def estimate_tokens(byte_count: int) -> int:
    """Bytes → token-count proxy. Deterministic, no dependencies."""
    return byte_count // BYTES_PER_TOKEN_PROXY


def estimate_decode_seconds(tokens: int, tokens_per_second: float) -> float:
    """Tokens → wall-clock decode estimate at a given tok/s rate.

    Guards against zero or negative rate by returning 0.0 — the caller
    is expected to surface "no estimate available" in that case rather
    than propagate nonsense.
    """
    if tokens_per_second <= 0:
        return 0.0
    return tokens / tokens_per_second


_REGISTRY: dict[str, Compressor] = {}


def register(compressor: Compressor) -> Compressor:
    if not compressor.name:
        raise ValueError("Compressor must have a non-empty name")
    if compressor.name in _REGISTRY:
        raise ValueError(f"Compressor already registered: {compressor.name}")
    _REGISTRY[compressor.name] = compressor
    return compressor


def get(name: str) -> Compressor:
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown compressor: {name!r}. Registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def names() -> list[str]:
    return sorted(_REGISTRY)


def _message_bytes(msg: Message) -> int:
    content = msg.get("content", "") or ""
    return len(content.encode("utf-8", errors="replace"))


def messages_bytes(messages: list[Message]) -> int:
    return sum(_message_bytes(m) for m in messages)


@dataclass
class NoOpCompressor:
    name: str = "noop"

    def apply(
        self, messages: list[Message]
    ) -> tuple[list[Message], CompressorStats]:
        t0 = time.perf_counter()
        stats = CompressorStats(
            name=self.name,
            fires=0,
            messages_in=len(messages),
            messages_out=len(messages),
            bytes_in=messages_bytes(messages),
            bytes_out=messages_bytes(messages),
            latency_s=time.perf_counter() - t0,
        )
        return messages, stats


def compress_messages(
    messages: list[Message], compressor_id: str | None
) -> tuple[list[Message], CompressorStats]:
    """Apply the named compressor; missing/empty/'noop' is a passthrough.

    Public entry point. Mirrors the shape we'd wire into luxe's loop, just
    above the existing last-resort elision step.
    """
    if not compressor_id or compressor_id == "noop":
        return _REGISTRY["noop"].apply(messages)
    return get(compressor_id).apply(messages)


def time_apply(
    fn: Callable[[list[Message]], tuple[list[Message], CompressorStats]],
    messages: list[Message],
) -> tuple[list[Message], CompressorStats]:
    """Wrap an apply() call to attribute end-to-end latency on the stats.

    Compressors may set latency themselves; this is a fallback for stubs.
    """
    t0 = time.perf_counter()
    out, stats = fn(messages)
    if stats.latency_s == 0.0:
        stats.latency_s = time.perf_counter() - t0
    return out, stats


register(NoOpCompressor())

# Side-effect registrations of bundled compressors.
from tokeless.compressors import exact_hash_dedup as _exact_hash_dedup  # noqa: E402,F401
from tokeless.compressors import structured_normalize as _structured_normalize  # noqa: E402,F401
from tokeless.compressors import structural_dedup as _structural_dedup  # noqa: E402,F401
from tokeless.compressors import chain as _chain  # noqa: E402,F401
