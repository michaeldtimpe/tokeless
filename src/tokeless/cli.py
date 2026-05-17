"""tokeless command-line entry point.

Usage:
    tokeless compressor list
    tokeless corpus list
    tokeless eval <compressor> <corpus>
    tokeless compare <control> <treatment> <corpus>
    tokeless eval <compressor> --luxe-trace-dir <path>
    tokeless compare <control> <treatment> --luxe-trace-dir <path>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tokeless import compressors as compressor_mod
from tokeless import corpora as corpora_mod
from tokeless.corpora import Corpus
from tokeless.corpora.luxe_simulate import write_archetype_bundle
from tokeless.corpora.luxe_trace import load_dir_with_stats
from tokeless.eval._utils import format_load_stats_table
from tokeless.eval.compare import ComparisonThresholds, compare
from tokeless.eval.runner import run_eval


def _resolve_corpus(args: argparse.Namespace) -> Corpus:
    """Resolve --luxe-trace-dir or registered corpus name.

    For --luxe-trace-dir, runs ingestion accounting and prints the
    schema-drift table on STDERR when any file has skip_rate > 0.
    Silence-when-clean: no drift, no output. Stderr keeps it out of
    `tee`'d stdout captures while remaining visible to the operator.
    """
    if args.luxe_trace_dir:
        path = Path(args.luxe_trace_dir).expanduser().resolve()
        if not path.is_dir():
            raise SystemExit(f"luxe-trace-dir does not exist: {path}")
        corpus, stats = load_dir_with_stats(path)
        if any(s.skip_rate > 0 for s in stats):
            sys.stderr.write(format_load_stats_table(stats) + "\n")
        return corpus
    if not args.corpus:
        raise SystemExit("must provide either <corpus> or --luxe-trace-dir")
    return corpora_mod.get(args.corpus)


def cmd_compressor_list(_args: argparse.Namespace) -> int:
    for name in compressor_mod.names():
        print(name)
    return 0


def cmd_corpus_list(_args: argparse.Namespace) -> int:
    for name in corpora_mod.names():
        corpus = corpora_mod.get(name)
        print(f"{name:<24} {len(corpus):>3} item(s)  {corpus.description}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    corpus = _resolve_corpus(args)
    result = run_eval(corpus, args.compressor)
    print(f"corpus: {corpus.name}  compressor: {args.compressor}")
    print(result.format_table(tokens_per_second=args.tokens_per_second))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    corpus = _resolve_corpus(args)
    thresholds = ComparisonThresholds(
        min_bytes_improvement=args.min_bytes_improvement,
        min_items_fired=args.min_items_fired,
        max_latency_per_item_s=args.max_latency_per_item_s,
    )
    report = compare(corpus, args.control, args.treatment, thresholds)
    print(report.format_report(tokens_per_second=args.tokens_per_second))
    return 0 if report.verdict == "PASS" else 1


def cmd_dev_simulate_luxe_traces(args: argparse.Namespace) -> int:
    """Write four synthetic archetype trace bundles. NOT real data —
    see luxe_simulate.py docstring for the anti-conflation note.
    """
    root = Path(args.output_dir).expanduser().resolve()
    written = write_archetype_bundle(root, seed=args.seed)
    print(f"wrote {len(written)} archetype bundles under {root}")
    for archetype, jsonl in sorted(written.items()):
        print(f"  {archetype:<14} {jsonl}")
    print("(synthetic — NOT real luxe traces; see manifest.json "
          "'synthetic: true')")
    return 0


def _add_corpus_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "corpus",
        nargs="?",
        default=None,
        help="registered corpus name (omit when using --luxe-trace-dir)",
    )
    p.add_argument(
        "--luxe-trace-dir",
        default=None,
        help="load a Corpus from luxe-shaped JSONL files in this directory",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tokeless")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_compressor = sub.add_parser("compressor", help="compressor commands")
    p_compressor_sub = p_compressor.add_subparsers(dest="subcmd", required=True)
    p_compressor_list = p_compressor_sub.add_parser("list")
    p_compressor_list.set_defaults(fn=cmd_compressor_list)

    p_corpus = sub.add_parser("corpus", help="corpus commands")
    p_corpus_sub = p_corpus.add_subparsers(dest="subcmd", required=True)
    p_corpus_list = p_corpus_sub.add_parser("list")
    p_corpus_list.set_defaults(fn=cmd_corpus_list)

    p_eval = sub.add_parser("eval", help="run one compressor over one corpus")
    p_eval.add_argument("compressor", help="registered compressor name")
    _add_corpus_args(p_eval)
    p_eval.add_argument(
        "--tokens-per-second", type=float, default=100.0,
        help="rate for the synthetic decode-time estimate (default 100)",
    )
    p_eval.set_defaults(fn=cmd_eval)

    p_compare = sub.add_parser("compare", help="paired comparison + verdict")
    p_compare.add_argument("control", help="baseline compressor name")
    p_compare.add_argument("treatment", help="candidate compressor name")
    _add_corpus_args(p_compare)
    p_compare.add_argument("--min-bytes-improvement", type=float, default=0.20)
    p_compare.add_argument("--min-items-fired", type=int, default=1)
    p_compare.add_argument("--max-latency-per-item-s", type=float, default=0.100)
    p_compare.add_argument(
        "--tokens-per-second", type=float, default=100.0,
        help="rate for the synthetic decode-time estimate (default 100)",
    )
    p_compare.set_defaults(fn=cmd_compare)

    # `dev` namespace: diagnostic / non-production tooling. Keep this
    # narrow — once a dev namespace exists it tends to become a
    # dumping ground.
    p_dev = sub.add_parser("dev", help="diagnostic tooling (non-production)")
    p_dev_sub = p_dev.add_subparsers(dest="subcmd", required=True)
    p_dev_sim = p_dev_sub.add_parser(
        "simulate-luxe-traces",
        help="write four synthetic luxe-trace archetype bundles "
             "(NOT real data — for harness validation only)",
    )
    p_dev_sim.add_argument(
        "--output-dir",
        default="traces/_synthetic/",
        help="destination root (default: traces/_synthetic/)",
    )
    p_dev_sim.add_argument(
        "--seed", type=int, default=0,
        help="seed for the deterministic hostile-archetype RNG (default 0)",
    )
    p_dev_sim.set_defaults(fn=cmd_dev_simulate_luxe_traces)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
