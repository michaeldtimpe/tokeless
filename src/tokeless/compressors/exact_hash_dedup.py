"""Phase A stub: exact-hash dedup on tool-role message bodies.

Replaces later occurrences of byte-identical tool results with a short
back-reference stub. Deterministic; runs at temp=0; reversible (you can
reconstruct from the kept canonical copy).

This is the smallest credible Phase-A intervention from the design memo:
"repeated diff-hunk suppression, repeated diagnostic suppression" — exact
hash is the zero-risk floor. Real Phase A would extend with structural
fingerprints (normalized whitespace, hunk-anchor stripping); this stub
gets the harness off the ground.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from tokeless.compressors import (
    Compressor,
    CompressorStats,
    Message,
    _message_bytes,
    register,
)


def _content_sha1(content: str) -> str:
    return hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()


def _stub(name: str, first_index: int, digest: str, bytes_orig: int) -> str:
    return (
        f"[duplicate of msg #{first_index} tool={name} "
        f"hash={digest[:12]} bytes={bytes_orig}]"
    )


@dataclass
class ExactHashDedupCompressor:
    """Replace later duplicate tool-role bodies with back-references.

    Only `role == 'tool'` messages participate. The first occurrence of any
    content hash is kept verbatim; subsequent occurrences are replaced with
    a stub that references the kept index.

    Empty/whitespace-only tool bodies are ignored (no value in deduping noise).
    """

    name: str = "exact_hash_dedup"
    min_bytes: int = 32

    def apply(
        self, messages: list[Message]
    ) -> tuple[list[Message], CompressorStats]:
        t0 = time.perf_counter()
        bytes_in = sum(_message_bytes(m) for m in messages)
        first_seen: dict[str, int] = {}
        items_dropped = 0
        fires = 0
        out: list[Message] = []

        for i, msg in enumerate(messages):
            if msg.get("role") != "tool":
                out.append(msg)
                continue

            content = msg.get("content", "") or ""
            if len(content.encode("utf-8", errors="replace")) < self.min_bytes:
                out.append(msg)
                continue

            digest = _content_sha1(content)
            if digest in first_seen:
                replacement: Message = {
                    **msg,
                    "content": _stub(
                        msg.get("name", "tool"),
                        first_seen[digest],
                        digest,
                        len(content.encode("utf-8", errors="replace")),
                    ),
                }
                out.append(replacement)
                items_dropped += 1
                fires += 1
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
        )


register(ExactHashDedupCompressor())
