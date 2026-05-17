"""Paired comparison + binary verdict.

Runs two compressors against the same corpus and reports per-item +
aggregate deltas. The verdict mirrors the discipline from the design memo:
- Treatment must beat control by a pre-declared margin (default 20% bytes).
- Treatment must fire on at least N items (default 1) — non-firing means
  the mechanism has no contact with this corpus.
- Treatment must not exceed a per-item latency ceiling (default 100ms).
- Structural integrity (message count + role order) must hold on every
  item; the runner already enforces this and would have raised.

Defaults are corpus-testing proxies, not the wall-clock 15% gate that
applies inside luxe; surface them on ComparisonThresholds for tuning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tokeless.compressors import estimate_decode_seconds, estimate_tokens
from tokeless.corpora import Corpus
from tokeless.eval.runner import EvalResult, run_eval


@dataclass
class ComparisonThresholds:
    min_bytes_improvement: float = 0.20
    min_items_fired: int = 1
    max_latency_per_item_s: float = 0.100


@dataclass
class ItemDelta:
    item_id: str
    control_bytes: int
    treatment_bytes: int
    bytes_saved: int
    pct_saved: float
    treatment_fires: int
    treatment_latency_s: float


@dataclass
class ComparisonReport:
    corpus_name: str
    control_id: str
    treatment_id: str
    thresholds: ComparisonThresholds
    control: EvalResult
    treatment: EvalResult
    deltas: list[ItemDelta] = field(default_factory=list)
    verdict: str = "INCONCLUSIVE"
    reasons: list[str] = field(default_factory=list)

    @property
    def total_pct_saved(self) -> float:
        ctl = self.control.totals.bytes_in
        if ctl == 0:
            return 0.0
        return (
            self.control.totals.bytes_out - self.treatment.totals.bytes_out
        ) / ctl

    def format_report(self, tokens_per_second: float = 100.0) -> str:
        lines: list[str] = []
        lines.append(
            f"=== {self.treatment_id} vs {self.control_id} "
            f"on corpus '{self.corpus_name}' ==="
        )
        header = (
            f"{'item':<24} {'ctl_B':>8} {'trt_B':>8} {'saved_B':>8} "
            f"{'pct':>7} {'trt_fires':>9} {'trt_ms':>7}"
        )
        lines.append(header)
        lines.append("-" * len(header))
        for d in self.deltas:
            lines.append(
                f"{d.item_id[:24]:<24} "
                f"{d.control_bytes:>8} {d.treatment_bytes:>8} "
                f"{d.bytes_saved:>8} {d.pct_saved * 100:>6.1f}% "
                f"{d.treatment_fires:>9} "
                f"{d.treatment_latency_s * 1000:>7.2f}"
            )
        lines.append("-" * len(header))
        total_bytes_saved = (
            self.control.totals.bytes_in - self.treatment.totals.bytes_out
        )
        lines.append(
            f"  total bytes saved: {total_bytes_saved} "
            f"({self.total_pct_saved * 100:.1f}%)"
        )
        tokens_saved = estimate_tokens(total_bytes_saved)
        decode_s = estimate_decode_seconds(tokens_saved, tokens_per_second)
        lines.append(
            f"  total tokens saved ≈ {tokens_saved} "
            f"(decode @{tokens_per_second:g} tok/s ≈ {decode_s:.2f}s; "
            f"proxy: bytes/4)"
        )
        lines.append(
            f"  treatment avg savings per fire ≈ "
            f"{self.treatment.totals.bytes_saved_per_fire} B"
        )
        lines.append(
            f"  treatment fired on "
            f"{self.treatment.fired_on}/{len(self.treatment.items)} items "
            f"({self.treatment.firing_rate * 100:.1f}%)"
        )
        lines.append("")
        lines.append(f"VERDICT: {self.verdict}")
        for r in self.reasons:
            lines.append(f"  - {r}")
        return "\n".join(lines)


def compare(
    corpus: Corpus,
    control_id: str,
    treatment_id: str,
    thresholds: ComparisonThresholds | None = None,
) -> ComparisonReport:
    th = thresholds or ComparisonThresholds()
    control = run_eval(corpus, control_id)
    treatment = run_eval(corpus, treatment_id)

    by_id = {it.item_id: it for it in control.items}
    deltas: list[ItemDelta] = []
    for trt in treatment.items:
        ctl = by_id.get(trt.item_id)
        if ctl is None:
            continue
        ctl_bytes = ctl.stats.bytes_out
        trt_bytes = trt.stats.bytes_out
        bytes_saved = ctl_bytes - trt_bytes
        pct = bytes_saved / ctl_bytes if ctl_bytes else 0.0
        deltas.append(
            ItemDelta(
                item_id=trt.item_id,
                control_bytes=ctl_bytes,
                treatment_bytes=trt_bytes,
                bytes_saved=bytes_saved,
                pct_saved=pct,
                treatment_fires=trt.stats.fires,
                treatment_latency_s=trt.stats.latency_s,
            )
        )

    report = ComparisonReport(
        corpus_name=corpus.name,
        control_id=control_id,
        treatment_id=treatment_id,
        thresholds=th,
        control=control,
        treatment=treatment,
        deltas=deltas,
    )

    reasons: list[str] = []
    pct_total = report.total_pct_saved
    if pct_total < th.min_bytes_improvement:
        reasons.append(
            f"bytes-improvement {pct_total * 100:.1f}% < "
            f"threshold {th.min_bytes_improvement * 100:.1f}%"
        )
    if treatment.fired_on < th.min_items_fired:
        reasons.append(
            f"fired on {treatment.fired_on} item(s) < "
            f"threshold {th.min_items_fired}"
        )
    over_latency = [
        d for d in deltas if d.treatment_latency_s > th.max_latency_per_item_s
    ]
    if over_latency:
        reasons.append(
            f"{len(over_latency)} item(s) exceeded "
            f"{th.max_latency_per_item_s * 1000:.0f}ms latency ceiling: "
            + ", ".join(d.item_id for d in over_latency[:3])
        )

    report.reasons = reasons
    report.verdict = "PASS" if not reasons else "FAIL"
    return report
