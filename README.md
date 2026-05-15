# tokeless

Standalone test harness for evaluating LLM-context compression mechanisms
against luxe-shaped tool-output corpora.

Parallel development to the [luxe](../luxe/) agentic-coding harness. Not
coupled to luxe's runtime. Compressor candidates that prove out here may
later be folded into luxe as a feature set under luxe's own gating
discipline.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```sh
# List what's available
tokeless compressor list
tokeless corpus list

# Run one compressor against one synthetic corpus
tokeless eval exact_hash_dedup git_diff_repeated

# Paired comparison + binary verdict (PASS/FAIL)
tokeless compare noop exact_hash_dedup mixed_session
tokeless compare noop structured_normalize mypy_verbose

# Ingest a real luxe trace directory (read-only)
tokeless eval exact_hash_dedup --luxe-trace-dir ~/.luxe/runs/<run_id>/stages

# Tune the verdict thresholds
tokeless compare noop exact_hash_dedup mixed_session \
    --min-bytes-improvement 0.30 \
    --max-latency-per-item-s 0.050
```

## Test

```sh
.venv/bin/python -m pytest -q
```

## Layout

```
src/tokeless/
├── compressors/         # protocol + registry + stubs (noop, exact_hash_dedup, structured_normalize)
├── corpora/             # Corpus primitives + synthetic generators + luxe-trace adapter
├── eval/                # run_eval + paired compare + verdict reporter
├── cli.py               # `tokeless ...` entry point
└── __main__.py          # `python -m tokeless`
tests/                   # pytest suite (46 tests, stdlib-only deps)
```

See `RESUME.md` for the project status, design rationale, and what's next.
