"""Sequential composition of compressors.

`ChainCompressor` applies a list of compressors in order. The first
link sees the raw input; each subsequent link sees the previous link's
output. The chain's flat `CompressorStats` reflects the original input
to the final output, with per-link transformation events summed into
`fires` and per-link diagnostics flattened into `notes` with a
link-name prefix.

**Stats semantics differ subtly from individual compressors and are
documented in the plan jiggly-squishing-hopcroft.md:**

- `bytes_in` / `bytes_out` reflect the chain boundaries (original
  input vs final output), NOT the per-link slices.
- `fires` is the sum of per-link `fires` — it counts *transformation
  events* across the whole chain, not unique messages transformed. The
  invariant `fires <= messages_in` that holds for individual
  compressors does NOT hold for chains, because a single message may
  be touched by multiple links.
- `latency_s` is the wall-clock duration of the whole chain. Per-link
  `latency_s` is also captured in `stats.notes` for debugging, but the
  headline timing is the single end-to-end number.
- `notes` is non-normative: tests must not assert specific note
  strings beyond the link-name prefix shape. Note text may evolve;
  behavioral contracts must not depend on it.

**Composition invariant (why dedup-first is canonical):** dedup
preserves raw provenance uniqueness; normalize intentionally erases
distinctions. Composing them as `[dedup, normalize]` keeps
equivalence classes intact. The reverse — `[normalize, dedup]` —
risks dedup over-firing on two semantically distinct tool runs that
happen to normalize to the same shape. The `ChainCompressor` class
is order-agnostic, but the canonical pre-registered chain ships in
dedup-first order.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from tokeless.compressors import (
    Compressor,
    CompressorStats,
    Message,
    _message_bytes,
    register,
)
from tokeless.compressors.exact_hash_dedup import ExactHashDedupCompressor  # noqa: F401
from tokeless.compressors.structural_dedup import StructuralDedupCompressor
from tokeless.compressors.structured_normalize import StructuredNormalizeCompressor


@dataclass
class ChainCompressor:
    name: str = "chain"
    links: list[Compressor] = field(default_factory=list)

    def apply(
        self, messages: list[Message]
    ) -> tuple[list[Message], CompressorStats]:
        t0 = time.perf_counter()
        bytes_in = sum(_message_bytes(m) for m in messages)
        current: list[Message] = list(messages)  # shallow copy of the list itself;
        # links return new lists/messages and do not mutate the input.

        total_fires = 0
        total_items_dropped = 0
        total_items_normalized = 0
        notes: list[str] = []

        for link in self.links:
            out, link_stats = link.apply(current)
            total_fires += link_stats.fires
            total_items_dropped += link_stats.items_dropped
            total_items_normalized += link_stats.items_normalized
            # Per-link latency goes into notes as a debugging signal.
            # Format intentionally non-normative — tests must not assert
            # specific text here.
            notes.append(
                f"{link_stats.name}: latency_s={link_stats.latency_s:.6f}"
            )
            for n in link_stats.notes:
                notes.append(f"{link_stats.name}: {n}")
            current = out

        bytes_out = sum(_message_bytes(m) for m in current)
        return current, CompressorStats(
            name=self.name,
            fires=total_fires,
            messages_in=len(messages),
            messages_out=len(current),
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            items_dropped=total_items_dropped,
            items_normalized=total_items_normalized,
            latency_s=time.perf_counter() - t0,
            notes=notes,
        )


# Canonical chain: dedup-first, then per-tool normalize what survives.
# Fresh instances (not registry globals) so the chain owns its links
# and doesn't depend on mutable registry state.
register(
    ChainCompressor(
        name="dedup_then_normalize",
        links=[StructuralDedupCompressor(), StructuredNormalizeCompressor()],
    )
)
