"""Synthetic luxe-trace JSONL generator.

This is NOT real data. All numbers measured against the output of this
generator are guaranteed to be cheerful because every redundancy
pattern was put there on purpose. Real-trace verdicts supersede
anything measured here. Synthetic = harness-validation only.

The generator exercises:
- the loader (`load_jsonl` / `load_jsonl_with_stats`)
- the measurement loop plumbing
- compressor invocation paths

It does NOT simulate timestamps, streaming chunks, partial tool
calls, nested envelopes, or any structure beyond what
`_coerce_message` (`luxe_trace.py:_coerce_message`) actually reads:
`role`, `name`, `content`, `tool_call_id`, `tool_calls`. Adding
realism beyond that would invite future-readers to mistake synthetic
output for evidence about real luxe traffic.

Determinism is a hard contract: same archetype + seed → byte-identical
JSONL across runs. This turns the simulator into a regression fixture
generator, not just demo tooling.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from tokeless.corpora.synthetic import (
    _FILE_CONTENT,
    _MYPY_BLOCK,
    _RECALL_UUID,
    _RUFF_BLOCK,
    _SHIFTED_DIFF_BODY,
)

_GENERATOR_VERSION = "tokeless-0.2.1"
# Pinned constant — NOT a real timestamp. Determinism is the contract;
# `generated_at` would otherwise vary by run and defeat byte-identical
# regeneration.
_GENERATED_AT_FROZEN = "synthetic-deterministic"
_HOSTILE_BODY_BYTES = 1024
ARCHETYPES: tuple[str, ...] = (
    "lint_heavy",
    "diff_heavy",
    "long_session",
    "hostile",
)
_EXPECTED_COMPRESSION: dict[str, str] = {
    "lint_heavy": "high",
    "diff_heavy": "high",
    "long_session": "moderate",
    "hostile": "zero",
}
_DIFF_ANCHORS = (
    "@@ -10,7 +10,7 @@",
    "@@ -42,7 +42,7 @@",
    "@@ -8 +8 @@",
    "@@ -100,7 +100,7 @@",
)


def _event(
    role: str,
    content: str,
    name: str | None = None,
) -> dict[str, Any]:
    e: dict[str, Any] = {"role": role, "content": content}
    if name is not None:
        e["name"] = name
    return e


def _shifted_diff(anchor: str) -> str:
    return (
        "diff --git a/src/foo/bar.py b/src/foo/bar.py\n"
        "index 1a2b3c4..5d6e7f8 100644\n"
        "--- a/src/foo/bar.py\n"
        "+++ b/src/foo/bar.py\n"
        f"{anchor} class Bar:\n"
        f"{_SHIFTED_DIFF_BODY}"
    )


def _events_lint_heavy(_seed: int) -> list[dict[str, Any]]:
    """20 events: 1 system, 1 user, 12 mypy, 4 ruff, 2 assistant.
    Exercises `structured_normalize`. Repeated mypy bodies exercise
    dedup."""
    events: list[dict[str, Any]] = [
        _event("system", "You are a coding agent."),
        _event("user", "Iterate on lint errors until clean."),
    ]
    for _ in range(12):
        events.append(_event("tool", _MYPY_BLOCK, name="mypy"))
    for _ in range(4):
        events.append(_event("tool", _RUFF_BLOCK, name="ruff"))
    events.append(_event("assistant", "Fixing the line-length issue."))
    events.append(_event("assistant", "And the unused-variable error."))
    return events


def _events_diff_heavy(_seed: int) -> list[dict[str, Any]]:
    """20 events: 1 system, 1 user, 12 git_diff (shifted anchors),
    4 read_file, 2 assistant. Exercises `structural_dedup`."""
    events: list[dict[str, Any]] = [
        _event("system", "You are a coding agent."),
        _event("user", "Refactor and verify."),
    ]
    for i in range(12):
        events.append(_event(
            "tool", _shifted_diff(_DIFF_ANCHORS[i % 4]), name="git_diff",
        ))
    for _ in range(4):
        events.append(_event("tool", _FILE_CONTENT, name="read_file"))
    events.append(_event("assistant", "Applied refactor; checking result."))
    events.append(_event("assistant", "All clean."))
    return events


def _events_long_session(_seed: int) -> list[dict[str, Any]]:
    """30 events. A task UUID emitted in turn 3 is referenced again
    in turns 15, 22, and 28 — exercises long-range recall preservation.
    Middle: heterogeneous mypy / git_diff / read_file / assistant mix.
    """
    task_create = (
        f'{{"task_id": "{_RECALL_UUID}", '
        f'"title": "Fix lint", "status": "open"}}'
    )
    task_list = (
        f'[{{"task_id": "{_RECALL_UUID}", "status": "in_progress"}}]'
    )
    task_update = (
        f'{{"task_id": "{_RECALL_UUID}", "status": "in_review"}}'
    )
    task_complete = (
        f'{{"task_id": "{_RECALL_UUID}", "status": "done"}}'
    )

    events: list[dict[str, Any]] = []
    events.append(_event("system", "You are a coding agent."))         # 1
    events.append(_event("user", "Track and fix the lint task."))      # 2
    events.append(_event("tool", task_create, name="task_tracker"))    # 3 (UUID)
    events.append(_event("assistant", "Task created."))                # 4
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 5
    events.append(_event("assistant", "Found errors."))                # 6
    events.append(_event("tool", _FILE_CONTENT, name="read_file"))     # 7
    events.append(_event("assistant", "Reading bar.py."))              # 8
    events.append(_event("tool", _shifted_diff(_DIFF_ANCHORS[0]),
                         name="git_diff"))                              # 9
    events.append(_event("assistant", "Patch applied."))               # 10
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 11
    events.append(_event("assistant", "Re-checking."))                 # 12
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 13
    events.append(_event("tool", _FILE_CONTENT, name="read_file"))     # 14
    events.append(_event("tool", task_list, name="task_tracker"))      # 15 (UUID)
    events.append(_event("assistant", "Status in_progress."))          # 16
    events.append(_event("tool", _shifted_diff(_DIFF_ANCHORS[1]),
                         name="git_diff"))                              # 17
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 18
    events.append(_event("assistant", "Second pass."))                 # 19
    events.append(_event("tool", _shifted_diff(_DIFF_ANCHORS[2]),
                         name="git_diff"))                              # 20
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 21
    events.append(_event("tool", task_update, name="task_tracker"))    # 22 (UUID)
    events.append(_event("assistant", "Marked in_review."))            # 23
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 24
    events.append(_event("tool", _shifted_diff(_DIFF_ANCHORS[3]),
                         name="git_diff"))                              # 25
    events.append(_event("tool", _FILE_CONTENT, name="read_file"))     # 26
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 27
    events.append(_event("tool", task_complete, name="task_tracker"))  # 28 (UUID)
    events.append(_event("assistant", "Task done."))                   # 29
    events.append(_event("tool", _MYPY_BLOCK, name="mypy"))            # 30
    return events


def _events_hostile(seed: int) -> list[dict[str, Any]]:
    """20 events: 1 system, 1 user, 18 high-entropy unique random_blob
    tool events.

    Mechanism: each tool body is 1KB of seeded-random bytes hex-encoded
    (2048 hex chars), tool name `random_blob` (NOT in
    structured_normalize's registry → dispatcher misses → no normalize),
    each body seeded with `seed * 1000 + turn_idx` so each body is
    unique within and across seeds. Bodies share no substring ≥32
    bytes — defeats structural_dedup's min_bytes threshold. Every
    compressor should fire 0 times. Establishes the realistic floor.
    """
    events: list[dict[str, Any]] = [
        _event("system", "You are a coding agent."),
        _event("user", "Inspect the random blobs."),
    ]
    for i in range(18):
        rng = random.Random(seed * 1000 + i)
        body = rng.randbytes(_HOSTILE_BODY_BYTES).hex()
        events.append(_event("tool", body, name="random_blob"))
    return events


_ARCHETYPE_BUILDERS = {
    "lint_heavy": _events_lint_heavy,
    "diff_heavy": _events_diff_heavy,
    "long_session": _events_long_session,
    "hostile": _events_hostile,
}


def simulate_archetype(
    archetype: str,
    output_dir: Path,
    *,
    seed: int = 0,
) -> Path:
    """Write one synthetic <archetype>.jsonl to output_dir.

    Returns the path. Byte-identical for same (archetype, seed).
    """
    if archetype not in _ARCHETYPE_BUILDERS:
        raise ValueError(
            f"Unknown archetype: {archetype!r}. "
            f"Known: {sorted(_ARCHETYPE_BUILDERS)}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{archetype}.jsonl"
    events = _ARCHETYPE_BUILDERS[archetype](seed)
    # json.dumps with sort_keys=True locks key order so the bytes are
    # stable regardless of dict insertion order in the event builders.
    lines = "\n".join(json.dumps(e, sort_keys=True) for e in events) + "\n"
    path.write_text(lines, encoding="utf-8")
    return path


def _manifest(archetype: str, seed: int, turns: int) -> dict[str, Any]:
    return {
        "archetype": archetype,
        "synthetic": True,
        "seed": seed,
        "turns": turns,
        "generator_version": _GENERATOR_VERSION,
        "generated_at": _GENERATED_AT_FROZEN,
        "jsonl": f"{archetype}.jsonl",
        "expected_compression": _EXPECTED_COMPRESSION[archetype],
    }


def write_archetype_bundle(
    root: Path, *, seed: int = 0
) -> dict[str, Path]:
    """Write all four archetypes (each in its own archetype_<name>/
    subdirectory) plus per-archetype manifest.json files. Returns
    {archetype_name: jsonl_path}. Byte-identical for same seed.
    """
    root.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for archetype in ARCHETYPES:
        subdir = root / f"archetype_{archetype}"
        jsonl = simulate_archetype(archetype, subdir, seed=seed)
        events = _ARCHETYPE_BUILDERS[archetype](seed)
        manifest = _manifest(archetype, seed, len(events))
        (subdir / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        out[archetype] = jsonl
    return out
