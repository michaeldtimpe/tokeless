"""Shared helpers used by runner.py and compare.py.

Underscore-prefixed module name signals package-internal use; nothing
here is part of tokeless's public API. The helpers live here (rather
than inlined into runner.py) because compare.py imports them too and
a shared utility module keeps the import graph one-directional
(_utils <- runner <- compare).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tokeless.corpora.luxe_trace import LoadStats


def format_load_stats_table(stats: list["LoadStats"]) -> str:
    """Render per-file ingestion accounting as a human-readable block.

    Used by the CLI to surface schema drift on stderr before the
    evaluation summary. Caller is responsible for deciding whether to
    emit it at all — the silence-when-clean policy (no drift → no
    output) lives in cli.py, not here.
    """
    if not stats:
        return ""
    lines: list[str] = []
    lines.append("schema-drift accounting:")
    header = (
        f"  {'source':<40} {'lines':>7} {'parsed':>7} "
        f"{'skipped':>7} {'skip%':>6}  shapes"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for s in stats:
        shape_repr = (
            ", ".join("(" + ",".join(t) + ")" for t in s.sample_skipped_shapes)
            if s.sample_skipped_shapes else ""
        )
        lines.append(
            f"  {s.source[:40]:<40} {s.total_lines:>7} "
            f"{s.parsed_messages:>7} {s.total_skipped:>7} "
            f"{s.skip_rate * 100:>5.1f}%  {shape_repr}"
        )
    return "\n".join(lines)
