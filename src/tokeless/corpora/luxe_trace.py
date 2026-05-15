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
"""

from __future__ import annotations

import json
from pathlib import Path

from tokeless.compressors import Message
from tokeless.corpora import Corpus, CorpusItem


_KEEP_KEYS = ("role", "name", "content", "tool_call_id", "tool_calls")


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


def load_jsonl(path: Path) -> CorpusItem:
    """Load one trace file as a CorpusItem."""
    messages: list[Message] = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    for ln, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        msg = _coerce_message(event)
        if msg is None:
            continue
        messages.append(msg)
    return CorpusItem(
        item_id=path.stem,
        messages=messages,
        description=f"Loaded from {path} ({len(messages)} message events).",
    )


def load_dir(directory: Path, pattern: str = "*.jsonl") -> Corpus:
    """Load every matching JSONL file under `directory` as one Corpus."""
    paths = sorted(directory.glob(pattern))
    items = [load_jsonl(p) for p in paths]
    return Corpus(
        name=f"luxe_trace:{directory.name}",
        description=(
            f"Loaded {len(items)} luxe trace file(s) from {directory} "
            f"matching {pattern!r}."
        ),
        items=items,
    )
