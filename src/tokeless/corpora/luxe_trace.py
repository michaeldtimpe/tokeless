"""Read-only adapter for luxe-trace JSONL files.

Luxe writes per-event JSONL during a run (see luxe's run_state.append_event).
This module loads such files *without importing luxe* — purely by detecting
the JSON shape — and produces a Corpus of message sequences. Useful when a
real run is available on disk and you want to score compressors against it.

Schema expectations (permissive):
- One JSON object per line.
- Each event has at least a `role` key. `name`, `content`, `tool_call_id`,
  `tool_calls` are passed through if present.
- Events without a `role` field are skipped (telemetry, separators).
- One CorpusItem per file; the item_id is the file stem.

Observability: load_jsonl_with_stats / load_dir_with_stats mirror the
permissive semantics and return per-file LoadStats. The original
load_jsonl / load_dir signatures and return shapes are unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tokeless.compressors import Message
from tokeless.corpora import Corpus, CorpusItem


_KEEP_KEYS = ("role", "name", "content", "tool_call_id", "tool_calls")

_MAX_SAMPLE_SHAPES = 3
_NON_DICT_SENTINEL: tuple[str, ...] = ("<non-dict>",)


@dataclass
class LoadStats:
    """Per-file ingestion accounting for a luxe-trace JSONL.

    skip_rate is computed against PHYSICAL LINES encountered, including
    blank lines. (Not "events attempted" — pinning the semantics so
    two readers cannot interpret the same 8% number differently.)

    sample_skipped_shapes records the KEY-SET (never values) of up to
    _MAX_SAMPLE_SHAPES DISTINCT skipped events. Distinct = different
    sorted key-tuple. This prevents a 10k-line file of identically
    malformed events from filling the cap with three copies of the
    same shape.

    PII contract: NEVER record values. Key-sets only, sorted for
    determinism. Inline-pinned here so a future contributor cannot
    accidentally violate the "never values" promise.
    """
    source: str
    total_lines: int = 0
    parsed_messages: int = 0
    skipped_blank: int = 0
    skipped_json_error: int = 0
    skipped_not_dict: int = 0
    skipped_no_role: int = 0
    skipped_unknown: int = 0
    sample_skipped_shapes: list[tuple[str, ...]] = field(default_factory=list)

    @property
    def total_skipped(self) -> int:
        return (
            self.skipped_blank
            + self.skipped_json_error
            + self.skipped_not_dict
            + self.skipped_no_role
            + self.skipped_unknown
        )

    @property
    def skip_rate(self) -> float:
        return self.total_skipped / self.total_lines if self.total_lines else 0.0

    @property
    def parsed_rate(self) -> float:
        return self.parsed_messages / self.total_lines if self.total_lines else 0.0


def _coerce_message(event: dict) -> Message | None:
    if "role" not in event:
        return None
    msg: Message = {}
    for k in _KEEP_KEYS:
        if k in event and event[k] is not None:
            msg[k] = event[k]  # type: ignore[literal-required]
    if "content" not in msg:
        msg["content"] = ""
    return msg


def _record_skipped_shape(
    stats: LoadStats, shape: tuple[str, ...]
) -> None:
    """Append to sample_skipped_shapes only if it's a NEW distinct shape
    and we haven't hit the cap. No-op otherwise.
    """
    if len(stats.sample_skipped_shapes) >= _MAX_SAMPLE_SHAPES:
        return
    if shape in stats.sample_skipped_shapes:
        return
    stats.sample_skipped_shapes.append(shape)


def load_jsonl(path: Path) -> CorpusItem:
    """Load one trace file as a CorpusItem. Permissive — skips events that
    cannot be parsed or lack `role`. Existing callers rely on this shape;
    DO NOT change semantics without a deprecation cycle.
    """
    item, _stats = load_jsonl_with_stats(path)
    return item


def load_dir(directory: Path, pattern: str = "*.jsonl") -> Corpus:
    """Aggregate every matching JSONL file under `directory`. Existing
    behavior preserved — see load_dir_with_stats for the observable
    variant.
    """
    corpus, _stats = load_dir_with_stats(directory, pattern)
    return corpus


def load_jsonl_with_stats(path: Path) -> tuple[CorpusItem, LoadStats]:
    """Same permissive semantics as load_jsonl, plus observability.

    Zero-message contract: a file where every line is skipped returns
    a CorpusItem with empty messages list AND a LoadStats with
    skip_rate == 1.0 (when there is at least one non-blank skipped
    line; or 0.0 for a completely empty file). Matches load_jsonl's
    existing behavior on all-skipped input.
    """
    stats = LoadStats(source=str(path.name))
    messages: list[Message] = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        stats.total_lines += 1
        stripped = line.strip()
        if not stripped:
            stats.skipped_blank += 1
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            stats.skipped_json_error += 1
            continue
        if not isinstance(event, dict):
            stats.skipped_not_dict += 1
            _record_skipped_shape(stats, _NON_DICT_SENTINEL)
            continue
        msg = _coerce_message(event)
        if msg is None:
            stats.skipped_no_role += 1
            _record_skipped_shape(stats, tuple(sorted(event.keys())))
            continue
        messages.append(msg)
        stats.parsed_messages += 1
    item = CorpusItem(
        item_id=path.stem,
        messages=messages,
        description=f"Loaded from {path} ({len(messages)} message events).",
    )
    return item, stats


def load_dir_with_stats(
    directory: Path, pattern: str = "*.jsonl"
) -> tuple[Corpus, list[LoadStats]]:
    """Aggregate version. Returns one LoadStats per file (not summed)
    so the verdict table can show per-file accounting. LoadStats list is
    in the same order as Corpus.items.
    """
    paths = sorted(directory.glob(pattern))
    items: list[CorpusItem] = []
    all_stats: list[LoadStats] = []
    for p in paths:
        item, stats = load_jsonl_with_stats(p)
        items.append(item)
        all_stats.append(stats)
    corpus = Corpus(
        name=f"luxe_trace:{directory.name}",
        description=(
            f"Loaded {len(items)} luxe trace file(s) from {directory} "
            f"matching {pattern!r}."
        ),
        items=items,
    )
    return corpus, all_stats
