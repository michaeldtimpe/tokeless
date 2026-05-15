# tokeless — session resume document

## Project framing

**tokeless** is a standalone harness for evaluating LLM-context compression
mechanisms against luxe-shaped tool-output corpora. It is parallel to the
[luxe](../luxe/) agentic-coding harness — luxe is **not modified** by any
of this work. Compressor candidates that prove their value in tokeless
under a tunable binary verdict gate may later be folded into luxe as a
feature set, under luxe's own grader-sensitive 15%/zero-regression
discipline.

The architecture decision behind the standalone split: luxe's acceptance
bench is grader-sensitive, its SDD contracts are strict, and its prompt
registry has strong invariants. Iterating on compressor candidates inside
luxe would either gate every experiment behind those guardrails (slow) or
risk perturbing the bench (unsafe). Standalone iteration lets the
compression space be explored quickly; promotion is gated separately.

## Current state — 2026-05-15

v0.1.0 scaffolded. 46 tests passing. CLI working. Two stub compressors
fire end-to-end against synthetic corpora and produce sensible numbers:
- `exact_hash_dedup` vs `noop` on `git_diff_repeated` → PASS, **47.9% bytes saved**
- `structured_normalize` vs `noop` on `mypy_verbose` → PASS, **29.6% bytes saved**

No remote yet (this `RESUME.md` written before push); see "Git" below.

## What's built

### Package skeleton
- `pyproject.toml` — Python ≥3.11, stdlib-only runtime deps, pytest dev extra
- `src/tokeless/` — layered package (compressors / corpora / eval / cli)
- `tests/` — 46 tests, pure pytest

### Compressors (`src/tokeless/compressors/`)
- `__init__.py` — `Message` TypedDict, `CompressorStats` dataclass with
  `merge()`, `Compressor` protocol, registry (`register/get/names`),
  `NoOpCompressor` baseline, `compress_messages()` public API,
  `messages_bytes()` helper.
- `exact_hash_dedup.py` — **Phase A stub**: replaces byte-identical
  later occurrences of `role=='tool'` message bodies with a back-reference
  stub `[duplicate of msg #N tool=X hash=... bytes=...]`. Deterministic.
  Skips bodies under `min_bytes=32`.
- `structured_normalize.py` — **Phase B stub**: per-tool normalizer
  registry. Ships one normalizer (`mypy`) that condenses verbose mypy
  output to one JSON line per diagnostic, preserving `tool / level /
  file / line / col / code / msg`. Unknown formats pass through
  unchanged (no silent drops).

### Corpora (`src/tokeless/corpora/`)
- `__init__.py` — `CorpusItem`, `Corpus`, registry (`register/get/names`).
- `synthetic.py` — 5 synthetic corpora targeting the redundancy shapes
  identified in the design memo:
  - `mypy_verbose` — verbose mypy diagnostics (Phase B target)
  - `git_diff_repeated` — same diff re-emitted across turns (Phase A target)
  - `bm25_overlap` — overlapping retrieval hits (Phase A target)
  - `read_file_dup` — duplicate file reads (Phase A target)
  - `mixed_session` — interleaved roles with multiple redundancy patterns
- `luxe_trace.py` — read-only JSONL adapter. **No luxe import** — purely
  shape-based. Tolerates malformed lines. `load_jsonl(path)` returns one
  `CorpusItem`; `load_dir(directory)` aggregates as one `Corpus`.

### Eval (`src/tokeless/eval/`)
- `runner.py` — `run_eval(corpus, compressor_id)` applies the compressor
  to every item, aggregates per-item + total stats, enforces structural
  integrity (message count + role order — raises on drift by default).
  `EvalResult.format_table()` prints a per-item + total table with
  bytes_in/bytes_out/saved/ratio/latency.
- `compare.py` — `compare(corpus, control_id, treatment_id, thresholds)`
  runs both compressors against the same corpus and produces a
  `ComparisonReport` with per-item deltas and a binary `PASS`/`FAIL`
  verdict. Default `ComparisonThresholds`:
  - `min_bytes_improvement: 0.20` (treatment must beat control by ≥20%)
  - `min_items_fired: 1`
  - `max_latency_per_item_s: 0.100`

### CLI (`src/tokeless/cli.py`)
- `tokeless compressor list`
- `tokeless corpus list`
- `tokeless eval <compressor> <corpus>`
- `tokeless eval <compressor> --luxe-trace-dir <path>`
- `tokeless compare <control> <treatment> <corpus>`
- `tokeless compare <control> <treatment> --luxe-trace-dir <path>`
- Compare-mode threshold tuning via `--min-bytes-improvement`,
  `--min-items-fired`, `--max-latency-per-item-s`.
- Compare returns exit code 0 on PASS, 1 on FAIL (CI-friendly).

### Tests (`tests/`)
46 tests across 7 files. Stdlib-only — no luxe import.
- `test_compressors_protocol.py` — registry, noop identity, stats math
- `test_compressors_exact_hash_dedup.py` — dedup correctness, min_bytes
  threshold, non-tool-role passthrough, three-repeat case, stub fields
- `test_compressors_structured_normalize.py` — mypy normalizer
  correctness, error-code preservation, summary-line dropping, unknown-
  format passthrough, custom-normalizer registration
- `test_corpora_synthetic.py` — corpora register, are deterministic, have
  items, redundancy is actually present
- `test_corpora_luxe_trace.py` — JSONL parsing, malformed-line
  tolerance, missing-content fill, multi-file aggregation, empty-dir
- `test_eval_runner.py` — runner math, integrity check raises on
  drift (and can be disabled), `format_table` output
- `test_eval_compare.py` — verdict logic (passes when justified, fails
  on no-improvement, fails when nothing fires, threshold tuning)
- `test_cli.py` — every subcommand, luxe-trace-dir flow, exit codes

## How to run it

```sh
# Setup (if .venv missing or fresh checkout)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Tests
.venv/bin/python -m pytest -q

# Stubs end-to-end
.venv/bin/python -m tokeless compare noop exact_hash_dedup git_diff_repeated
.venv/bin/python -m tokeless compare noop structured_normalize mypy_verbose

# Against a real luxe run directory (read-only)
.venv/bin/python -m tokeless eval exact_hash_dedup --luxe-trace-dir ~/.luxe/runs/<id>/stages
```

## What's next (sequencing follows the design memo's Phase A → F)

### Near-term, code-only — extends what's already there
1. **Structural Phase A dedup** (whitespace-normalized hash, hunk-anchor
   stripping). Current `exact_hash_dedup` only catches byte-identical
   duplicates. Real diffs often re-emit with shifted line numbers but
   identical hunks; structural fingerprinting captures that without
   adding generative risk. Hook: add a second compressor
   (`structural_dedup`) alongside `exact_hash_dedup`; do not modify the
   existing exact-hash stub (it's the zero-risk floor).
2. **More Phase B normalizers** (ruff, eslint, git_log, git_show,
   OSV CVE). Same plug-in shape as the mypy normalizer; each is a
   `Normalizer = Callable[[str], str]` registered into a fresh
   `StructuredNormalizeCompressor` instance or merged into the default.
3. **Adversarial corpora** — content shapes designed to *not* compress
   (random hex, unique-per-message tokens). Verifies stubs don't drop
   things they shouldn't. The integrity check in `run_eval` already
   catches role/message-count drift; adversarial corpora exercise the
   "no firing when nothing redundant" branch.
4. **Wall-time proxy metric** in `EvalResult`. Today the harness measures
   bytes-saved + latency-per-item. To approximate the wall-clock gate
   that gates luxe rollouts, add a tokens-saved estimate
   (`bytes_in / 4` or a real tokenizer pass) and a synthetic
   "decode time saved at N tok/s" line. Useful for translating
   tokeless verdicts into luxe-relevant talking points.

### Medium-term, harness-level
5. **Real luxe-trace corpus seeding**. Run a few `luxe maintain` fixtures
   with `LUXE_LOG_TOOL_CALLS=1`, point `--luxe-trace-dir` at the output,
   measure savings against real content shape. This is the most
   important sanity check before considering any luxe-side fold-in.
6. **Compressor chaining**. Phase A + Phase B together: dedup first
   (lossless), then normalize what survives. Will need a small
   composition utility — e.g. `ChainCompressor([dedup, normalize])` —
   that accumulates stats from each link.
7. **Confidence-interval reporting**. The memo's measurement section
   asks for variance bounds. Run the comparison N times against a
   bootstrapped corpus; report median + naive 95% CI. The
   per-item determinism of stubs means CI will be near-zero today —
   the infra is what matters, so chained/learned compressors
   that introduce variance can be measured cleanly.

### Long-term, requires research
8. **Embedding-based Phase C clustering**. Only after deterministic
   Phase A+B plateau. Requires an embedding model (oMLX or local
   sentence-transformer); careful guardrails on code/diff content
   per the memo's hard exclusion.
9. **Learned token pruning probe (Phase E)**. Only if A–D plateau.
   Memo positions this as last-resort; the harness should support it
   for completeness, but expect a negative result.

### Bridge to luxe
10. **Promotion checklist.** When a candidate clears tokeless's tunable
    bar AND a luxe-trace corpus shows ≥20% bytes saved AND latency stays
    under a luxe-relevant ceiling, draft a luxe-side wiring proposal:
    add `compressor_id` to `RoleConfig`, invoke `compress_messages()`
    in `agents/loop.py` just before the existing `elide_old_tool_results`
    call, route through variants YAML. Do not implement inside luxe
    until the user explicitly authorizes — see `~/.claude/plans/
    optimized-weaving-koala.md` for the original evaluation memo and
    `lessons.md:397-419` in luxe for the gating precedent.

## Design rationale (so future-you doesn't relitigate)

- **Why standalone instead of inside luxe.** Iterating compressor stubs
  inside luxe would either gate every experiment behind SDD contracts +
  acceptance bench (slow) or risk perturbing grader-sensitive behavior
  (unsafe). The 47.9% bytes-saved result on `git_diff_repeated` is
  cheap data; the same probe inside luxe would have required a full
  `benchmarks/maintain_suite` run.
- **Why deterministic stubs first, learned methods later.** Memo
  conclusion: under luxe's constraints (frozen model, grader-sensitive
  workload, prefix-cache already absorbing easy wins), deterministic
  redundancy elimination outranks learned compression. Stubs first means
  the harness is provably correct and the bar is set for any learned
  candidate to beat.
- **Why `Compressor` protocol shape mirrors what luxe would need.**
  `apply(messages) -> (messages, stats)` is exactly what would slot into
  `agents/loop.py:255–329` (between `context_pressure()` and
  `elide_old_tool_results()`). When promotion happens, the wiring is
  trivial: luxe imports `tokeless.compressors.compress_messages` (or
  vendors the equivalent) and calls it before the existing elision step.
- **Why integrity checks raise by default.** A compressor that silently
  drops messages corrupts grader-sensitive workloads. Default-raise
  ensures any structural regression is caught before it can be measured
  as a "win."
- **Why bytes-saved, not tokens-saved, is the primary metric.**
  Bytes are deterministic, language-agnostic, dependency-free. A real
  tokenizer pass is a fine secondary metric (see "What's next" #4)
  but should not gate the harness's correctness story.

## Gotchas / things to remember

- **Don't import luxe.** Ever. The standalone split is the value here.
  The luxe-trace adapter detects JSONL shape, not luxe types.
- **`compress_messages(messages, None)` is a noop passthrough.** This
  matches the planned luxe wiring (empty `compressor_id` = no behavior
  change). Tests rely on this; don't change it without updating callers.
- **Integrity check default is raise.** When testing a deliberately
  bad compressor, pass `raise_on_drift=False`.
- **Compressors register on module import.** `tokeless.compressors`
  re-imports `exact_hash_dedup` and `structured_normalize` at the
  bottom of its `__init__.py` to trigger registration. Don't move
  those re-imports without checking that registration still happens.
- **Verdict thresholds are corpus-test proxies, not luxe-grade gates.**
  20% bytes-saved on a synthetic corpus is not equivalent to luxe's
  15% wall-clock gate. The promotion checklist (item 10 above) is
  the bridge.

## Reference index

- `~/.claude/plans/optimized-weaving-koala.md` — the evaluation memo
  that scoped this work. Bucket-by-bucket fit assessment, recommended
  phasing A → F, measurement discipline, central conclusion. **Read
  this first** if you're picking up cold.
- `~/Downloads/luxe/lessons.md:397-419` — the speculative-decoding
  probe precedent (binary 15%/revert gate). The model for how any
  luxe-side fold-in should be measured.
- `~/Downloads/luxe/lessons.md:417` — future-oMLX watch list (parked
  items: gist tokens, block diffusion, native compaction). Update
  here when promoting a tokeless candidate into luxe.
- `~/Downloads/luxe/RESUME.md` — luxe production-state document.
  Reference for "what content shape does luxe actually accumulate"
  questions.

## Git

Local repo initialized 2026-05-15. Private GitHub remote
`michaeldtimpe/tokeless` (see push step in the conversation that set
this up).
