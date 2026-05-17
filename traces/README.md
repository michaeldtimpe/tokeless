# `traces/` — real luxe-trace fixtures for Phase 2 validation

This directory holds captured luxe-trace JSONL files used to validate
tokeless compressors against real (non-synthetic) workloads. See
`~/.claude/plans/drifting-waddling-scott.md` for the full phase plan.

## Directory contract

```
traces/
├── README.md                              # this file (committed)
├── archetype_lint_heavy/
│   ├── manifest.json                      # committed
│   └── *.jsonl                            # gitignored
├── archetype_diff_heavy/
│   ├── manifest.json
│   └── *.jsonl
├── archetype_long_session/
│   ├── manifest.json
│   └── *.jsonl
├── archetype_hostile/
│   ├── manifest.json
│   └── *.jsonl
└── archetype_diff_heavy_pre_elision/      # optional: elision-disabled variant
    ├── manifest.json
    └── *.jsonl
```

`.gitignore` ignores `traces/` by default. Only `traces/README.md` and
`traces/*/manifest.json` are explicitly un-ignored — JSONL never enters
git history.

## Naming discipline (PII)

Fixture subdirectories use **archetype names only**, never internal
project / repo / customer names. `traces/billing-app-v4/` would leak
internal architecture via the committed `manifest.json` path even
though the JSONL itself is gitignored. Rename to
`archetype_diff_heavy/` (or similar) at copy time.

The four archetypes are:

1. **`archetype_lint_heavy`** — mypy / ruff-dominant agent session.
   Exercises `structured_normalize`.
2. **`archetype_diff_heavy`** — refactor / diff-dominant session.
   Exercises `structural_dedup`.
3. **`archetype_long_session`** — one logical ≥15-turn agent run
   (NOT multiple shorter runs concatenated — that would inflate
   `exact_hash_dedup` via repeated session preamble, a false win).
4. **`archetype_hostile`** — deliberately heterogeneous / low-redundancy
   workload (web-heavy research, broad repo exploration, debugging with
   rapidly-changing outputs, API inspection, stack traces). Establishes
   the realistic floor and prevents favorable-selection bias.

## Capture procedure

On a machine with luxe checked out:

```sh
LUXE_LOG_TOOL_CALLS=1 luxe maintain <fixture-name>
# locate the resulting JSONL under ~/.luxe/runs/<id>/stages/
```

Copy each fixture's `*.jsonl` to `tokeless/traces/<archetype>/`.

**Optional pre-elision variant.** If luxe configuration permits, capture
`archetype_diff_heavy` a second time with `elide_old_tool_results`
disabled and save as `archetype_diff_heavy_pre_elision/`. This is the
control for the pre-elision paradox — it separates "compressors have
no value" from "value already captured upstream by elision."

## Per-fixture manifest

Each `traces/<archetype>/manifest.json` (committed) records:

```json
{
  "captured_at": "2026-MM-DD",
  "luxe_version": "<commit SHA or tag>",
  "description": "<archetype-only one-line description; no project names>",
  "approx_turns": 0,
  "elision_active": true,
  "log_tool_calls_env": true
}
```

The manifest makes the "Real-trace baseline" RESUME section
reproducible later.

## Size budget

≤50MB aggregate across all fixtures. `load_jsonl`
(`src/tokeless/corpora/luxe_trace.py:40`) does `read_text` on the
whole file; fine at that scale. A 40MB JSONL takes several seconds to
parse — not a hang, just slow IO.

## Running measurements

Once fixtures are populated, from the repo root:

```sh
for f in traces/archetype_*/; do
  for c in exact_hash_dedup structural_dedup structured_normalize dedup_then_normalize; do
    .venv/bin/python -m tokeless compare noop "$c" --luxe-trace-dir "$f" \
      | tee "traces/_runs/$(basename $f)__$c.txt"
  done
done
```

`traces/_runs/` is also gitignored (`_` prefix flags it as runtime
output, not a captured fixture).

## PII safety reminder

**Do NOT** run `tokeless corpus inspect` (or any command that prints
raw corpus content) against fixtures in this directory. That pipes
captured content to terminal history where it may persist and outlive
the gitignore. Aggregate numbers only when reporting results.
