"""Run one compressor over one corpus and aggregate stats."""

from __future__ import annotations

from dataclasses import dataclass, field

from tokeless.compressors import (
    CompressorStats,
    Message,
    compress_messages,
    estimate_decode_seconds,
    messages_bytes,
)
from tokeless.corpora import Corpus, CorpusItem


@dataclass
class ItemResult:
    item_id: str
    description: str
    stats: CompressorStats
    out_messages: list[Message]

    @property
    def bytes_saved(self) -> int:
        return self.stats.bytes_saved

    @property
    def compression_ratio(self) -> float:
        return self.stats.compression_ratio


@dataclass
class EvalResult:
    corpus_name: str
    compressor_id: str
    items: list[ItemResult] = field(default_factory=list)
    totals: CompressorStats = field(default_factory=CompressorStats)

    @property
    def fired_on(self) -> int:
        return sum(1 for it in self.items if it.stats.fires > 0)

    @property
    def firing_rate(self) -> float:
        if not self.items:
            return 0.0
        return self.fired_on / len(self.items)

    def format_table(self, tokens_per_second: float = 100.0) -> str:
        lines: list[str] = []
        header = (
            f"{'item':<24} {'fires':>6} {'in_B':>8} {'out_B':>8} "
            f"{'saved_B':>8} {'saved_T':>8} {'avg_B/fire':>10} "
            f"{'ratio':>6} {'lat_ms':>7}"
        )
        lines.append(header)
        lines.append("-" * len(header))
        for it in self.items:
            s = it.stats
            lines.append(
                f"{it.item_id[:24]:<24} {s.fires:>6} "
                f"{s.bytes_in:>8} {s.bytes_out:>8} {s.bytes_saved:>8} "
                f"{s.tokens_saved_estimate:>8} {s.bytes_saved_per_fire:>10} "
                f"{s.compression_ratio:>6.2f} {s.latency_s * 1000:>7.2f}"
            )
        t = self.totals
        lines.append("-" * len(header))
        lines.append(
            f"{'TOTAL':<24} {t.fires:>6} {t.bytes_in:>8} {t.bytes_out:>8} "
            f"{t.bytes_saved:>8} {t.tokens_saved_estimate:>8} "
            f"{t.bytes_saved_per_fire:>10} "
            f"{t.compression_ratio:>6.2f} "
            f"{t.latency_s * 1000:>7.2f}"
        )
        lines.append(
            f"  fired on {self.fired_on}/{len(self.items)} item(s) "
            f"({self.firing_rate * 100:.1f}%)"
        )
        decode_s = estimate_decode_seconds(
            t.tokens_saved_estimate, tokens_per_second
        )
        lines.append(
            f"  tokens saved ≈ {t.tokens_saved_estimate} "
            f"(decode @{tokens_per_second:g} tok/s ≈ {decode_s:.2f}s; "
            f"proxy: bytes/4)"
        )
        return "\n".join(lines)


def _validate_integrity(
    item: CorpusItem, out: list[Message]
) -> list[str]:
    """Cheap structural invariants — compressors must not silently drop roles."""
    issues: list[str] = []
    if len(out) != len(item.messages):
        issues.append(
            f"message-count drift: in={len(item.messages)} out={len(out)}"
        )
    in_roles = [m.get("role") for m in item.messages]
    out_roles = [m.get("role") for m in out]
    if in_roles != out_roles:
        issues.append(
            f"role-order drift: in={in_roles} out={out_roles}"
        )
    return issues


def run_eval(
    corpus: Corpus, compressor_id: str, *, raise_on_drift: bool = True
) -> EvalResult:
    result = EvalResult(corpus_name=corpus.name, compressor_id=compressor_id)
    result.totals.name = compressor_id
    for item in corpus.items:
        out, stats = compress_messages(item.messages, compressor_id)
        issues = _validate_integrity(item, out)
        if issues:
            stats.notes.extend(issues)
            if raise_on_drift:
                raise RuntimeError(
                    f"Integrity check failed for {compressor_id} on "
                    f"{corpus.name}/{item.item_id}: {'; '.join(issues)}"
                )
        result.items.append(
            ItemResult(
                item_id=item.item_id,
                description=item.description,
                stats=stats,
                out_messages=out,
            )
        )
        result.totals.merge(stats)
    # Recompute bytes_in/out cleanly so totals.compression_ratio is accurate
    # even when individual stats include latency overhead from time_apply.
    result.totals.messages_in = sum(len(it.out_messages) for it in result.items)
    result.totals.messages_out = sum(len(it.out_messages) for it in result.items)
    result.totals.bytes_in = sum(
        messages_bytes(item.messages) for item in corpus.items
    )
    result.totals.bytes_out = sum(
        messages_bytes(it.out_messages) for it in result.items
    )
    return result
