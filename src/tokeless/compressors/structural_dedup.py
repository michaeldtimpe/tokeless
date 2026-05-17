"""Phase A — structural dedup over a canonicalized comparison view.

Conservative extension of `exact_hash_dedup`: preserves every exact-hash
win (byte-identical inputs still dedup) and adds two specific equivalence
classes:

1. **Unified-diff hunk anchor canonicalization.** Headers like
   `@@ -10,7 +10,7 @@ class Bar:` are re-emitted across turns with the
   byte-offset numbers shifted when unrelated edits earlier in the same
   file change all subsequent anchor positions. The trailing context line
   (` class Bar:`) is preserved so semantically distinct hunks remain
   distinct.

2. **Trailing whitespace per line.** Cosmetic capture differences
   (terminal vs file, indent-cleanup hooks) defeat byte-equality without
   changing semantics for the vast majority of tool-output content.

Hard non-goals (each one is a future-broadening guard):
- No internal-whitespace collapse (indentation is semantic in code).
- No blank-line collapse (consecutive blanks may be meaningful).
- No case folding, no Unicode normalization.
- File headers (`--- a/...`, `+++ b/...`) are NOT normalized — they
  contribute to the dedup key in full, so two diffs in different files
  remain distinct.
- Newlines are NEVER touched (`\\n` vs `\\r\\n` remain distinct).

Stub format is byte-for-byte identical to `exact_hash_dedup`'s; the
`hash=` digest is the SHA-1 of the *normalized* view, and `bytes=`
records the *original* byte length of the duplicate (pre-normalization).
The original message bytes are visible in the canonical first-occurrence
copy that the stub back-references.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass

from tokeless.compressors import (
    CompressorStats,
    Message,
    _message_bytes,
    register,
)

# `^` requires re.MULTILINE so it matches the start of each line, not just
# the start of the entire message text. Without the flag, this regex would
# only fire on hunks at message position 0 — virtually never useful because
# real diffs are preceded by file-header lines.
_HUNK_ANCHOR = re.compile(
    r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@",
    flags=re.MULTILINE,
)

# Strip spaces and tabs only at end of line; leave \n / \r\n alone.
# Naked .rstrip() would consume newlines and conflate line-ending shapes —
# an equivalence class v1 explicitly does NOT sign up for.
_TRAILING_WS = re.compile(r"[ \t]+$", flags=re.MULTILINE)


def _normalize(content: str) -> tuple[str, set[str]]:
    """Apply structural transforms; return normalized view + transform IDs fired."""
    transforms: set[str] = []
    new = _HUNK_ANCHOR.sub("@@ ANCHOR @@", content)
    if new != content:
        transforms.append("anchor-canon")
    after_ws = _TRAILING_WS.sub("", new)
    if after_ws != new:
        transforms.append("trailing-ws")
    return after_ws, set(transforms)


def _content_sha1(content: str) -> str:
    return hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()


def _stub(name: str, first_index: int, digest: str, bytes_orig: int) -> str:
    return (
        f"[duplicate of msg #{first_index} tool={name} "
        f"hash={digest[:12]} bytes={bytes_orig}]"
    )


@dataclass
class StructuralDedupCompressor:
    """Dedup tool-role bodies under a structurally normalized comparison view."""

    name: str = "structural_dedup"
    min_bytes: int = 32

    def apply(
        self, messages: list[Message]
    ) -> tuple[list[Message], CompressorStats]:
        t0 = time.perf_counter()
        bytes_in = sum(_message_bytes(m) for m in messages)
        first_seen: dict[str, int] = {}
        notes: list[str] = []
        items_dropped = 0
        fires = 0
        out: list[Message] = []

        for i, msg in enumerate(messages):
            if msg.get("role") != "tool":
                out.append(msg)
                continue

            content = msg.get("content", "") or ""
            content_bytes = len(content.encode("utf-8", errors="replace"))
            if content_bytes < self.min_bytes:
                out.append(msg)
                continue

            normalized, applied = _normalize(content)
            digest = _content_sha1(normalized)

            if digest in first_seen:
                canonical_idx = first_seen[digest]
                replacement: Message = {
                    **msg,
                    "content": _stub(
                        msg.get("name", "tool"),
                        canonical_idx,
                        digest,
                        content_bytes,
                    ),
                }
                out.append(replacement)
                items_dropped += 1
                fires += 1
                # Only annotate when a structural transform actually
                # contributed to the equivalence decision — byte-identical
                # dedups behave exactly like exact_hash_dedup and don't
                # need a note.
                if applied:
                    notes.append(
                        f"structural_dedup: {','.join(sorted(applied))} "
                        f"fired on msg #{i} (canonical #{canonical_idx})"
                    )
            else:
                first_seen[digest] = i
                out.append(msg)

        bytes_out = sum(_message_bytes(m) for m in out)
        return out, CompressorStats(
            name=self.name,
            fires=fires,
            messages_in=len(messages),
            messages_out=len(out),
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            items_dropped=items_dropped,
            latency_s=time.perf_counter() - t0,
            notes=notes,
        )


register(StructuralDedupCompressor())
