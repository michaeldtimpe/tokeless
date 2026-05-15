"""Phase B stub: per-tool structured normalization.

Demonstrates the per-tool normalizer plug-in shape. Ships a mypy-style
normalizer that condenses verbose mypy output to a compact JSON-ish line
per diagnostic, preserving every actionable signal (file, line, column,
error code, message) while dropping the multi-line "note:"/"help:" prose
that re-states what's already structurally present.

Real Phase B would ship normalizers for ruff, eslint, git_log, git_show,
OSV-CVE responses, etc. — each in this file or a sibling, registered into
the same per-tool registry.

Hard exclusion (per design memo): never normalize code/diff content where
silent omission is catastrophic. Normalizers must be schema-preserving
text transformations, not generative summarization.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from tokeless.compressors import (
    Compressor,
    CompressorStats,
    Message,
    _message_bytes,
    register,
)


# A Normalizer takes the tool-output content string and returns a
# normalized string. Returning the input unchanged signals "this output
# isn't in the format I expect; pass it through."
Normalizer = Callable[[str], str]


_MYPY_LINE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?P<level>error|note|warning):\s*(?P<msg>.+?)"
    r"(?:\s+\[(?P<code>[a-z][a-z0-9-]*)\])?$"
)


def _normalize_mypy(content: str) -> str:
    """Condense mypy verbose output to one JSON line per diagnostic.

    Keeps every `error:` line; drops standalone `note:`/`help:` follow-ups
    unless they introduce a new file:line not already present in the kept
    set. Drops the trailing summary line ("Found N errors in M files").

    If the content doesn't look like mypy output (zero matches), returns
    the input unchanged — never silently drops data we don't recognize.
    """
    diagnostics: list[dict[str, str | int]] = []
    seen_loc: set[tuple[str, int]] = set()
    matched_any = False

    for raw in content.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("Found ") and "error" in line and "file" in line:
            matched_any = True
            continue
        m = _MYPY_LINE.match(line)
        if not m:
            continue
        matched_any = True
        level = m.group("level")
        file_ = m.group("file")
        lno = int(m.group("line"))
        loc = (file_, lno)
        if level != "error" and loc in seen_loc:
            continue
        entry: dict[str, str | int] = {
            "tool": "mypy",
            "level": level,
            "file": file_,
            "line": lno,
            "msg": m.group("msg").strip(),
        }
        if m.group("col"):
            entry["col"] = int(m.group("col"))
        if m.group("code"):
            entry["code"] = m.group("code")
        diagnostics.append(entry)
        seen_loc.add(loc)

    if not matched_any or not diagnostics:
        return content
    return "\n".join(json.dumps(d, separators=(",", ":")) for d in diagnostics)


@dataclass
class StructuredNormalizeCompressor:
    """Dispatch per-tool normalizers based on the tool-role message's `name`.

    Defaults to a stub that only handles `mypy`. Extend by passing a custom
    `normalizers` dict, or by registering a new instance with additional
    keys for ruff/eslint/etc.
    """

    name: str = "structured_normalize"
    normalizers: dict[str, Normalizer] = field(
        default_factory=lambda: {"mypy": _normalize_mypy}
    )

    def apply(
        self, messages: list[Message]
    ) -> tuple[list[Message], CompressorStats]:
        t0 = time.perf_counter()
        bytes_in = sum(_message_bytes(m) for m in messages)
        items_normalized = 0
        fires = 0
        out: list[Message] = []

        for msg in messages:
            if msg.get("role") != "tool":
                out.append(msg)
                continue
            tool_name = msg.get("name") or ""
            normalizer = self.normalizers.get(tool_name)
            if normalizer is None:
                out.append(msg)
                continue
            content = msg.get("content", "") or ""
            normalized = normalizer(content)
            if normalized is content or normalized == content:
                out.append(msg)
                continue
            out.append({**msg, "content": normalized})
            items_normalized += 1
            fires += 1

        bytes_out = sum(_message_bytes(m) for m in out)
        return out, CompressorStats(
            name=self.name,
            fires=fires,
            messages_in=len(messages),
            messages_out=len(out),
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            items_normalized=items_normalized,
            latency_s=time.perf_counter() - t0,
        )


register(StructuredNormalizeCompressor())
