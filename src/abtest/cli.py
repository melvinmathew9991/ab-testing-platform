"""Command line interface.

    python -m abtest analyze --config configs/cookie_cats.yml --data data/raw/cookie_cats.csv
    python -m abtest power --baseline 0.19 --mde 0.05
    python -m abtest checks --config configs/cookie_cats.yml --data data/raw/cookie_cats.csv
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from abtest.config import ExperimentConfig
from abtest.data import ExperimentData
from abtest.experiment import Experiment
from abtest.reporting.report import build_html_report, build_markdown_report
from abtest.stats.power import sample_size_proportions


def _load(args) -> Experiment:
    config = ExperimentConfig.from_yaml(args.config)
    data = ExperimentData.from_file(args.data, config)
    return Experiment(data, config)


def cmd_analyze(args) -> int:
    exp = _load(args)
    results = exp.run(resample=args.resample, segment_by=args.segment_by or None)

    pd.set_option("display.width", 160, "display.max_columns", 40)
    print(f"\n{results.config.name}")
    print("=" * len(results.config.name))
    print(results.summary().to_string(index=False))
    print("\nChecks:")
    print(results.checks_frame().to_string(index=False))
    decision = results.decision()
    print(f"\nRecommendation: {decision['recommendation']}\n  {decision['reason']}\n")

    if args.html:
        print("HTML report:", build_html_report(results, output_path=args.html))
    if args.markdown:
        build_markdown_report(results, args.markdown)
        print("Markdown report:", args.markdown)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(results.to_dict(), fh, indent=2, default=str)
        print("JSON results:", args.json)
    return 0 if not results.blocking_failures else 1


def cmd_checks(args) -> int:
    exp = _load(args)
    results = exp.run()
    print(results.checks_frame().to_string(index=False))
    return 0 if not results.blocking_failures else 1


def cmd_power(args) -> int:
    res = sample_size_proportions(
        args.baseline,
        mde_relative=args.mde,
        alpha=args.alpha,
        power=args.power,
        ratio=args.ratio,
    )
    print(
        f"Baseline {res['baseline_rate']:.2%}, target lift {res['mde_relative']:+.2%} "
        f"({res['mde_absolute']:+.4f} absolute)\n"
        f"alpha {res['alpha']}, power {res['power']:.0%}\n\n"
        f"  Units per variant : {res['n_control']:,} control / {res['n_treatment']:,} treatment\n"
        f"  Total units       : {res['n_total']:,}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abtest", description="A/B test analysis toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Run a full experiment analysis")
    analyze.add_argument("--config", required=True, help="Experiment YAML")
    analyze.add_argument("--data", required=True, help="Unit-level CSV or Parquet")
    analyze.add_argument("--html", help="Write an HTML report here")
    analyze.add_argument("--markdown", help="Write a Markdown summary here")
    analyze.add_argument("--json", help="Write machine-readable results here")
    analyze.add_argument("--resample", action="store_true",
                         help="Add bootstrap CIs and permutation tests (slower)")
    analyze.add_argument("--segment-by", nargs="*", default=[],
                         help="Pre-experiment dimensions to break results down by")
    analyze.set_defaults(func=cmd_analyze)

    checks = sub.add_parser("checks", help="Run trust checks only")
    checks.add_argument("--config", required=True)
    checks.add_argument("--data", required=True)
    checks.set_defaults(func=cmd_checks)

    power = sub.add_parser("power", help="Sample size for a target effect")
    power.add_argument("--baseline", type=float, required=True, help="Baseline conversion rate")
    power.add_argument("--mde", type=float, required=True, help="Target relative lift, e.g. 0.05")
    power.add_argument("--alpha", type=float, default=0.05)
    power.add_argument("--power", type=float, default=0.80)
    power.add_argument("--ratio", type=float, default=1.0)
    power.set_defaults(func=cmd_power)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
