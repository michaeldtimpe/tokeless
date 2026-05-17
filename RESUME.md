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

## Archive state — 2026-05-17 (v0.2.1)

> **All current measurements are harness-validation metrics, not
> model-behavior conclusions.** Every bytes-saved number in this
> repository (47.9%, 29.6%, 52.8%, 84.8%, etc.) is measured against
> corpora that were authored to exhibit the redundancy the compressors
> target — i.e., a tautology. They prove the harness's measurement
> pipeline works end-to-end. They are NOT evidence that any compressor
> will save those amounts on real luxe traffic. Until Phase 2
> (real-trace validation) runs against live `LUXE_LOG_TOOL_CALLS=1`
> JSONL, treat every synthetic number as harness diagnostic only.

This repository is **archived** pending luxe feature-completeness.
138 tests passing. Five compressors, twelve registered corpora plus
a four-archetype synthetic-trace generator. Measurement infrastructure
(schema-drift accounting, savings-per-fire, latency p50/p95) is
complete; when real `LUXE_LOG_TOOL_CALLS=1` JSONL arrives, the bash
measurement loop produces the verdict tables on first run.

**Next live work when un-archived:** Phase 2, Steps 2–4 from
`~/.claude/plans/drifting-waddling-scott.md`. Step 1 (scaffolding)
landed; Step 2 (trace capture) blocks on `luxe maintain` being
available with `LUXE_LOG_TOOL_CALLS=1`.

### Synthetic-corpus baseline numbers (harness-validation only)

- `exact_hash_dedup` vs `noop` on `git_diff_repeated` → PASS, **47.9% bytes saved**
- `structured_normalize` vs `noop` on `mypy_verbose` → PASS, **29.6% bytes saved**
- `structural_dedup` vs `exact_hash_dedup` on
  `git_diff_repeated_shifted` → catches 3/4 hunks (vs 0/4 for exact).
- `dedup_then_normalize` on simulator's `lint_heavy` → 84.8%; on
  `diff_heavy` → 68.8%; on `long_session` → 73.0%; on `hostile` →
  0% (the floor — confirms the no-fire branch holds).

### v0.2.1 deltas (over v0.2.0)

- **LoadStats** in `corpora/luxe_trace.py` — observable ingestion
  accounting. `load_jsonl_with_stats` / `load_dir_with_stats`
  return per-file parsed/skipped/skip%/sample-shapes. Existing
  `load_jsonl` / `load_dir` signatures unchanged.
- **`bytes_saved_per_fire` property** on `CompressorStats`. Surfaced
  as the `avg_B/fire` column in `format_table` and as a footer line
  in `format_report`.
- **Latency p50/p95** percentiles over corpus items via manual linear
  interpolation in `eval/_utils.py:percentile`. Pinned X.YY ms
  precision. Footer in both `format_table` and `format_report`.
- **Synthetic luxe-trace simulator** at `corpora/luxe_simulate.py`
  with four pinned archetypes (lint_heavy / diff_heavy /
  long_session / hostile). Deterministic for same seed. CLI:
  `tokeless dev simulate-luxe-traces`. Used to validate the bash
  measurement loop end-to-end before real traces arrive.
- **CLI schema-drift hook** in `_resolve_corpus`: when
  `--luxe-trace-dir` is used, prints the per-file ingestion
  accounting table on stderr when any file has `skip_rate > 0`.
  Silence-when-clean; no output when ingestion is clean.

## What's built

### Package skeleton
- `pyproject.toml` — Python ≥3.11, stdlib-only runtime deps, pytest dev extra
- `src/tokeless/` — layered package (compressors / corpora / eval / cli)
- `tests/` — 138 tests, pure pytest

### Compressors (`src/tokeless/compressors/`)
- `__init__.py` — `Message` TypedDict, `CompressorStats` dataclass with
  `merge()`, `tokens_in_estimate` / `tokens_out_estimate` /
  `tokens_saved_estimate` properties (bytes/4 proxy), `Compressor`
  protocol, registry (`register/get/names`), `NoOpCompressor` baseline,
  `compress_messages()` public API, `messages_bytes()` helper,
  `BYTES_PER_TOKEN_PROXY` constant, `estimate_tokens()` and
  `estimate_decode_seconds()` helpers.
- `exact_hash_dedup.py` — **Phase A**: byte-identical dedup. Replaces
  later occurrences of `role=='tool'` message bodies with a
  back-reference stub `[duplicate of msg #N tool=X hash=... bytes=...]`.
  Deterministic. Skips bodies under `min_bytes=32`.
- `structural_dedup.py` — **Phase A extension**: normalized-hash dedup.
  Whitespace-normalized + hunk-anchor-canonicalized fingerprinting.
  Catches diffs re-emitted with shifted line numbers but identical
  hunks. Hard non-goals: no internal-whitespace collapse, no
  blank-line collapse, no case folding, no file-header normalization
  (cross-file collision guard).
- `structured_normalize.py` — **Phase B**: per-tool normalizer registry.
  Ships `mypy` and `ruff` normalizers. Each condenses verbose tool
  output to one JSON line per diagnostic, preserving tool / level /
  file / line / col / code / msg. Unknown formats pass through
  unchanged (no silent drops). Stub-isolation guard skips bodies
  starting with `[duplicate of msg #...` so dedup → normalize
  composition is safe.
- `chain.py` — **Composition**: `ChainCompressor(name, links=[...])`
  applies links sequentially. Stats accumulated end-to-end
  (bytes_in / bytes_out = chain boundaries; fires = sum across links;
  latency end-to-end). Pre-registers `dedup_then_normalize` with the
  canonical `[StructuralDedupCompressor, StructuredNormalizeCompressor]`
  order.

### Corpora (`src/tokeless/corpora/`)
- `__init__.py` — `CorpusItem`, `Corpus`, registry (`register/get/names`).
- `synthetic.py` — 12 synthetic corpora targeting redundancy shapes
  from the design memo plus the v0.2.0 additions:
  - `mypy_verbose` — verbose mypy diagnostics (Phase B target)
  - `ruff_verbose` — verbose ruff diagnostics (Phase B target) [v0.2.0]
  - `git_diff_repeated` — same diff re-emitted across turns (Phase A target)
  - `git_diff_repeated_shifted` — same diff re-emitted with shifted
    anchors + trailing-ws drift; demonstrates structural_dedup win
    over exact_hash_dedup [v0.2.0]
  - `bm25_overlap` — overlapping retrieval hits (Phase A target)
  - `read_file_dup` — duplicate file reads (Phase A target)
  - `long_session_recall` — 22-turn agent session with deterministic
    recall-critical UUID; preservation-under-firing test [v0.2.0]
  - `mixed_session` — interleaved roles with multiple redundancy patterns
  - `adversarial_random_hex` — high-entropy unique blobs; no-fire test [v0.2.0]
  - `adversarial_unique_tokens` — structurally-similar but unique
    JSON event lines; no-fire test under realistic shape [v0.2.0]
  - `adversarial_mypy_lookalike` — mypy-shaped content matching no
    `_MYPY_LINE`; exercises regex-miss return-unchanged branch [v0.2.0]
  - `adversarial_ruff_lookalike` — ruff-shaped content matching no
    `_RUFF_LINE`; same as above for ruff [v0.2.0]
- `luxe_trace.py` — read-only JSONL adapter. **No luxe import** — purely
  shape-based. Tolerates malformed lines. `load_jsonl(path)` returns one
  `CorpusItem`; `load_dir(directory)` aggregates as one `Corpus`.
  `LoadStats` + `load_jsonl_with_stats` / `load_dir_with_stats` (v0.2.1)
  expose ingestion observability — per-file
  parsed/skipped/skip%/sample-shapes accounting with categorized skip
  buckets (blank, json_error, not_dict, no_role, unknown). PII contract:
  sample_skipped_shapes records sorted-key tuples, never values.
- `luxe_simulate.py` (v0.2.1) — synthetic JSONL generator for the four
  pinned archetypes (lint_heavy / diff_heavy / long_session / hostile).
  Deterministic per seed. File docstring is the load-bearing
  anti-conflation surface — *NOT real data*.

### Eval (`src/tokeless/eval/`)
- `runner.py` — `run_eval(corpus, compressor_id)` applies the compressor
  to every item, aggregates per-item + total stats, enforces structural
  integrity (message count + role order — raises on drift by default).
  `EvalResult.format_table(tokens_per_second=100.0)` prints a per-item
  + total table with bytes_in / bytes_out / saved / saved_T / avg_B/fire
  / ratio / latency plus footer lines for tokens-saved, decode-time
  proxy, and latency p50/p95 over corpus items. `latency_p50_s` /
  `latency_p95_s` exposed on `EvalResult` (v0.2.1).
- `compare.py` — `compare(corpus, control_id, treatment_id, thresholds)`
  runs both compressors against the same corpus and produces a
  `ComparisonReport` with per-item deltas and a binary `PASS`/`FAIL`
  verdict. Default `ComparisonThresholds`:
  - `min_bytes_improvement: 0.20` (treatment must beat control by ≥20%)
  - `min_items_fired: 1`
  - `max_latency_per_item_s: 0.100`
  `format_report(tokens_per_second=100.0)` includes total tokens saved,
  decode-time proxy, treatment avg-savings-per-fire, and treatment
  latency p50/p95 (v0.2.1) alongside bytes-saved totals.
- `_utils.py` (v0.2.1) — shared helpers: `percentile()` (manual linear
  interpolation; numpy-free; stays within [min, max] on small samples)
  and `format_load_stats_table()` for the schema-drift display.

### CLI (`src/tokeless/cli.py`)
- `tokeless compressor list`
- `tokeless corpus list`
- `tokeless eval <compressor> <corpus>`
- `tokeless eval <compressor> --luxe-trace-dir <path>`
- `tokeless compare <control> <treatment> <corpus>`
- `tokeless compare <control> <treatment> --luxe-trace-dir <path>`
- `tokeless dev simulate-luxe-traces --output-dir <path> [--seed N]`
  (v0.2.1) — writes four synthetic archetype bundles. Diagnostic /
  non-production. Intentionally namespaced under `dev` so it can't
  be mistaken for production tooling.
- Compare-mode threshold tuning via `--min-bytes-improvement`,
  `--min-items-fired`, `--max-latency-per-item-s`.
- Both `eval` and `compare` accept `--tokens-per-second` (default 100.0)
  for the decode-time proxy.
- Compare returns exit code 0 on PASS, 1 on FAIL (CI-friendly).
- `--luxe-trace-dir` paths emit per-file schema-drift accounting on
  STDERR when any file has skip_rate > 0; silent when clean (v0.2.1).

### Tests (`tests/`)
138 tests across 11 files. Stdlib-only — no luxe import.
- `test_compressors_protocol.py` — registry, noop identity, stats math,
  tokens-saved proxy properties, decode-time guard
- `test_compressors_exact_hash_dedup.py` — dedup correctness, min_bytes
  threshold, non-tool-role passthrough, three-repeat case, stub fields
- `test_compressors_structural_dedup.py` — byte-identical wins, shifted
  anchors (with counts, omitted counts, zero counts), trailing-ws,
  cross-file collision guard, internal-whitespace guard,
  line-ending preservation
- `test_compressors_structured_normalize.py` — mypy + ruff normalizer
  correctness, error-code preservation, summary-line dropping,
  unknown-format passthrough, custom-normalizer registration,
  mypy/ruff lookalike no-match branch
- `test_compressors_chain.py` — empty chain passthrough, single-link
  equivalence, two-link boundary accounting, fires aggregation,
  no caller mutation, idempotency, sub-compressor exception propagation
- `test_corpora_synthetic.py` — corpora register, deterministic, have
  items, redundancy is actually present (including adversarial /
  long-session / shifted-diff corpora)
- `test_corpora_luxe_trace.py` — JSONL parsing, malformed-line
  tolerance, missing-content fill, multi-file aggregation, empty-dir,
  LoadStats categorization (blank/json_error/not_dict/no_role), distinct-
  shape dedup, _MAX_SAMPLE_SHAPES=3 cap, sorted-key tuples, zero-message
  contract, legacy byte-identical snapshot (v0.2.1)
- `test_corpora_luxe_simulate.py` (v0.2.1) — per-archetype valid JSONL,
  byte-identical determinism per seed, hostile-zero-fires across all
  compressors (the floor), long_session UUID preservation under all
  compressors, bundle layout, manifest schema keys
- `test_eval_utils.py` (v0.2.1) — percentile correctness against
  hand-derived numpy-equivalent answers (n=1, n=2, n=5)
- `test_eval_runner.py` — runner math, integrity check raises on
  drift (role-order and message-count branches; can be disabled),
  `format_table` output (tokens columns + decode-time + avg_B/fire +
  latency p50/p95 footers)
- `test_eval_compare.py` — verdict logic (passes when justified, fails
  on no-improvement, fails when nothing fires, threshold tuning,
  latency-ceiling branch), tokens-saved + avg-savings-per-fire +
  latency p50/p95 footers in report
- `test_cli.py` — every subcommand, luxe-trace-dir flow, exit codes,
  `--tokens-per-second` flag, threshold-flag plumbing, `dev
  simulate-luxe-traces` bundle creation + seed plumbing, stderr
  schema-drift display with silence-when-clean policy

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

# Generate synthetic luxe-trace bundle (NOT real data; harness-validation only)
.venv/bin/python -m tokeless dev simulate-luxe-traces --output-dir traces/_synthetic/

# Run the bash measurement loop against synthetic data (proxy for the
# real Phase 2 loop). Produces all four measurement surfaces:
# total bytes, avg savings per fire, latency p50/p95, tokens saved.
for f in traces/_synthetic/archetype_*/; do
  for c in exact_hash_dedup structural_dedup structured_normalize dedup_then_normalize; do
    .venv/bin/python -m tokeless compare noop "$c" --luxe-trace-dir "$f"
  done
done

# Against a real luxe run directory (read-only)
.venv/bin/python -m tokeless eval exact_hash_dedup --luxe-trace-dir ~/.luxe/runs/<id>/stages
```

## What's next (sequencing follows the design memo's Phase A → F)

### Roadmap status (as of v0.2.1, 2026-05-17)

| # | Title | Status |
|---|-------|--------|
| 1 | Structural Phase A dedup | **DONE** (`structural_dedup.py`, `git_diff_repeated_shifted` corpus) |
| 2 | More Phase B normalizers | **PARTIAL** (ruff shipped; eslint, git_log, git_show, OSV-CVE still pending) |
| 3 | Adversarial corpora | **DONE** (random_hex, unique_tokens, mypy/ruff lookalikes; long_session_recall as inverse-firing complement) |
| 4 | Wall-time proxy metric | **DONE** (tokens-saved = bytes/4; decode-time at default 100 tok/s; `--tokens-per-second` CLI flag) |
| 5 | Real luxe-trace seeding | **NEXT PHASE** — see `~/.claude/plans/drifting-waddling-scott.md` |
| 6 | Compressor chaining | **DONE** (`ChainCompressor`; `dedup_then_normalize` pre-registered) |
| 7 | Confidence-interval reporting | UNTOUCHED (deferred — per-item determinism makes CI near-zero today) |
| 8 | Embedding-based Phase C clustering | UNTOUCHED (deferred research) |
| 9 | Learned token pruning probe (Phase E) | UNTOUCHED (deferred research) |
| 10 | Promotion checklist | UNTOUCHED (gated on #5 verdict) |

### Near-term — item details retained for context

1. **Structural Phase A dedup** — DONE. Whitespace-normalization +
   hunk-anchor canonicalization. Conservative: no internal-whitespace
   collapse, no blank-line collapse, no case folding, no file-header
   normalization (cross-file collision guard).
2. **More Phase B normalizers** — PARTIAL. `ruff` (concise format)
   shipped alongside `mypy`. Remaining: eslint, git_log, git_show,
   OSV-CVE. Per next-phase plan, these are strictly downstream of
   item #5 — completing them before real-trace evidence risks adding
   surface area no workload exercises.
3. **Adversarial corpora** — DONE. Four adversarial corpora exercise
   the "no fire" branch:
   - `adversarial_random_hex` (high-entropy unique)
   - `adversarial_unique_tokens` (structurally similar, unique)
   - `adversarial_mypy_lookalike` (regex-miss branch for mypy)
   - `adversarial_ruff_lookalike` (regex-miss branch for ruff)
4. **Wall-time proxy metric** — DONE. `bytes/4` proxy on
   `CompressorStats`. `format_table` and `format_report` both surface
   tokens-saved + decode-time. `--tokens-per-second` CLI flag tunes
   the rate without touching the proxy.

### Medium-term

5. **Real luxe-trace corpus seeding** — **NEXT PHASE.** Detailed plan
   at `~/.claude/plans/drifting-waddling-scott.md`. Four archetype
   fixtures (lint-heavy, diff-heavy, long-session, hostile) with
   per-fixture manifest.json, hard schema-drift accounting,
   savings-per-fire metric, cross-trace contamination check. Verdict
   routes to one of A (promote → item #10), B (offline-only), or C
   (pre-elision dominates).
6. **Compressor chaining** — DONE. `ChainCompressor(name, links=[...])`
   with end-to-end stats accumulation. Canonical `dedup_then_normalize`
   pre-registered.
7. **Confidence-interval reporting** — UNTOUCHED. Out of scope for
   the next phase; per-item determinism of current compressors makes
   bootstrapped CI near-zero. Revisit once a non-deterministic
   compressor (e.g. embedding-based) enters the harness.

### Long-term, requires research
8. **Embedding-based Phase C clustering** — UNTOUCHED. Only after
   deterministic Phase A+B plateau on real traces. Requires an
   embedding model (oMLX or local sentence-transformer); careful
   guardrails on code/diff content per the memo's hard exclusion.
9. **Learned token pruning probe (Phase E)** — UNTOUCHED. Only if
   A–D plateau. Memo positions this as last-resort; the harness
   should support it for completeness, but expect a negative result.

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

- **Why "explicit transcript transformation system," not "compressor."**
  The governing abstraction tokeless commits to is inspectable,
  deterministic, replayable transcript transformation — not maximal
  compression ratio. Every output message is an artifact a human or grader
  can read; every transformation is reproducible; every integrity assertion
  is exact-match and model-independent. Transformations remain inspectable
  and policy-explicit whether they are lossless or intentionally
  lossy-by-policy — the durable invariants are *auditability* and
  *deterministic replay*, not bit-for-bit reversibility. This is the
  load-bearing distinction that disqualifies latent-memory approaches
  (e.g. δ-mem) and decode-acceleration approaches (e.g. Orthrus) without
  needing to relitigate each one — both trade in opaque model-internal
  state, which is categorically outside tokeless's contract.
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

### Research-watch references (non-aligned, not planned trajectory)

- **δ-mem** (arxiv 2605.12357) — *"δ-mem: Efficient Online Memory for
  Large Language Models,"* Lei et al., May 2026. Augments a frozen
  full-attention backbone with an 8×8 online memory state updated by a
  delta-rule. Reports 1.10×–1.31× uplift on MemoryAgentBench / LoCoMo.
  **Not a planned tokeless trajectory** — operates on attention
  activations, not transcript bytes, so categorically outside the
  `Compressor.apply(messages)` contract (latent-memory substitution vs
  explicit transcript transformation). Inspired the
  `long_session_recall` corpus shape (benchmark idea borrowed, technique
  rejected). Future luxe-side bookmark belongs near
  `~/Downloads/luxe/lessons.md:417` — pending separate session.
- **Orthrus** (github.com/chiennv2000/orthrus) — Dual-view AR + diffusion
  decoder with shared KV cache and exact intra-model consensus.
  4.25×–5.36× decode speedup vs EAGLE-3 / DFlash on Qwen3 sizes.
  **Not for tokeless** — decode-acceleration axis, does not reduce
  prompt size, KV residency, or upstream context bandwidth. Bookmarked
  here so future readers don't relitigate; belongs in luxe's
  speculative-decoding watch list (`~/Downloads/luxe/lessons.md:397-419`
  neighborhood) — pending separate session.

## Git

Local repo initialized 2026-05-15. Private GitHub remote
`michaeldtimpe/tokeless` (see push step in the conversation that set
this up).
