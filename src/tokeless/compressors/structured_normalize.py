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

# Matches ruff's CONCISE output format (the default). Ruff's JSON output
# mode (--output-format=json) is a different shape and is explicitly out
# of scope.
#
# POSIX-only: [^:\n]+ stops at the first colon, which breaks Windows
# drive-letter paths like `C:\foo\bar.py`. Such lines fall into the
# "no match → identity" branch (graceful pass-through, not corruption).
#
# Rule-code class [A-Z]{1,5}\d{1,5} is deliberately permissive to cover
# E (pycodestyle), F (pyflakes), UP (pyupgrade), RUF, B (bugbear), S
# (bandit), PT (pytest), and more. Surrounding format constraints
# (path:line:col: preceding, space-message-EOL trailing) keep false
# positives unlikely.
_RUFF_LINE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s+"
    r"(?P<code>[A-Z]{1,5}\d{1,5})\s+(?P<msg>.+)$"
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


def _normalize_ruff(content: str) -> str:
    """Condense ruff concise output to one JSON line per diagnostic.

    Keeps every matching `path:line:col: CODE message` line as a compact
    JSON object. Drops the trailing `Found N error(s)` summary, multi-line
    snippet blocks (lines starting with `  |`), and `help: ...` follow-up
    lines.

    Returns input unchanged on zero matches — same hard rule as
    `_normalize_mypy`. When at least one diagnostic IS captured, all
    non-matching non-summary lines in the message are dropped (a test
    pins this swallow behavior as an explicit contract).
    """
    diagnostics: list[dict[str, str | int]] = []
    matched_any = False

    for raw in content.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("Found ") and "error" in line:
            matched_any = True
            continue
        # Snippet block lines like `  | x = 'a' * 89` and `  | ^^ E501`.
        if line.startswith("  |"):
            continue
        # `help: ...` follow-up lines (after optional leading whitespace).
        if line.lstrip().startswith("help:"):
            continue
        m = _RUFF_LINE.match(line)
        if not m:
            continue
        matched_any = True
        entry: dict[str, str | int] = {
            "tool": "ruff",
            "file": m.group("file"),
            "line": int(m.group("line")),
            "col": int(m.group("col")),
            "code": m.group("code"),
            "msg": m.group("msg").strip(),
        }
        diagnostics.append(entry)

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
        default_factory=lambda: {
            "mypy": _normalize_mypy,
            "ruff": _normalize_ruff,
        }
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
            content = msg.get("content", "") or ""
            # Stub-isolation guard: dedup compressors emit back-reference
            # stubs that share a known prefix. Skip them globally so the
            # behavior does not depend on each normalizer's regex
            # happening to miss the stub shape.
            if content.startswith("[duplicate of msg #"):
                out.append(msg)
                continue
            tool_name = msg.get("name") or ""
            normalizer = self.normalizers.get(tool_name)
            if normalizer is None:
                out.append(msg)
                continue
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
