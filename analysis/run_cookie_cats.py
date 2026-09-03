"""Showcase analysis: the Cookie Cats gate-placement experiment.

Runs the full decision pipeline on a real public dataset and writes an HTML
report, a Markdown summary, a JSON result file and the figures behind them.

    python analysis/run_cookie_cats.py

Everything is seeded, so re-running reproduces the same numbers.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from abtest import Experiment, ExperimentConfig, ExperimentData  # noqa: E402
from abtest.reporting import plots  # noqa: E402
from abtest.reporting.report import build_html_report, build_markdown_report  # noqa: E402
from abtest.stats.power import (  # noqa: E402
    power_curve,
    sample_size_proportions,
)
from abtest.stats.sequential import sequential_analysis  # noqa: E402
from analysis.fetch_data import DEST as DATA_PATH, fetch  # noqa: E402

CONFIG_PATH = "configs/cookie_cats.yml"
FIG_DIR = os.path.join("reports", "figures")
REPORT_HTML = os.path.join("reports", "cookie_cats_report.html")
REPORT_MD = os.path.join("reports", "cookie_cats_summary.md")
REPORT_JSON = os.path.join("reports", "cookie_cats_results.json")


def simulate_peeking(df: pd.DataFrame, config: ExperimentConfig, n_looks: int = 8) -> pd.DataFrame:
    """Replay the experiment as if it had been checked repeatedly while running.

    The dataset has no timestamps, so users are placed in a random arrival
    order (seeded) and the metric is recomputed at eight equally spaced
    points. That is not a claim about how the real experiment accumulated -
    it is a demonstration of what repeated testing does to the false positive
    rate, using real data.
    """
    shuffled = df.sample(frac=1.0, random_state=config.seed).reset_index(drop=True)
    metric = "retention_7"
    looks = []
    for i in range(1, n_looks + 1):
        chunk = shuffled.iloc[: int(len(shuffled) * i / n_looks)]
        control = chunk[chunk[config.variant_col] == config.control]
        treatment = chunk[chunk[config.variant_col] == config.treatment]
        looks.append(
            {
                "label": f"{i}/{n_looks} of traffic",
                "n_control": len(control),
                "n_treatment": len(treatment),
                "conversions_control": int(control[metric].sum()),
                "conversions_treatment": int(treatment[metric].sum()),
            }
        )
    return sequential_analysis(looks, alpha=config.alpha)


def main() -> int:
    fetch()
    os.makedirs(FIG_DIR, exist_ok=True)

    config = ExperimentConfig.from_yaml(CONFIG_PATH)
    data = ExperimentData.from_file(DATA_PATH, config)
    print(data)

    experiment = Experiment(data, config)
    results = experiment.run(resample=True)
    summary = results.summary()

    print("\n--- Results ---")
    print(summary.to_string(index=False))
    print("\n--- Trust checks ---")
    print(results.checks_frame().to_string(index=False))

    # ---------------------------------------------------------------- power
    primary = results.outcome("retention_7")
    sensitivity = experiment.sensitivity("retention_7")
    baseline = primary.test.mean_control
    curve = power_curve(
        baseline,
        effects_relative=np.linspace(0, 0.12, 61),
        n_control=results.counts[config.control],
        n_treatment=results.counts[config.treatment],
        alpha=config.alpha,
    )
    needed_for_2pct = sample_size_proportions(baseline, mde_relative=0.02, power=config.power)

    print("\n--- Sensitivity (retention_7) ---")
    print(
        f"With {sum(results.counts.values()):,} users the experiment could detect a "
        f"{sensitivity['mde_relative']:+.2%} relative change at {config.power:.0%} power.\n"
        f"Detecting a 2% relative change would need "
        f"{needed_for_2pct['n_total']:,} users ({needed_for_2pct['n_total'] / sum(results.counts.values()):.1f}x "
        f"this experiment)."
    )

    # ------------------------------------------------------------- peeking
    looks = simulate_peeking(data.df, config)
    naive_stops = looks[looks["stop_naive"] & ~looks["stop_sequential"]]
    print("\n--- Peeking simulation (retention_7, random arrival order) ---")
    print(
        looks[["label", "n_total", "rate_control", "rate_treatment", "z_score",
               "p_value_fixed", "p_threshold_sequential", "stop_naive", "stop_sequential"]]
        .to_string(index=False)
    )

    # ------------------------------------------------------------- figures
    figures = []
    figures.append((
        "Relative lift with 95% confidence intervals. Day-7 retention is the only "
        "metric whose interval clears zero - and it clears it downwards.",
        plots.lift_forest(summary, os.path.join(FIG_DIR, "lift_forest.png")),
    ))
    figures.append((
        "Retention levels in both arms. The gap is small in absolute terms "
        "(0.8 percentage points on day 7) but consistent.",
        plots.metric_bars(
            summary[summary["role"] == "primary"],
            os.path.join(FIG_DIR, "metric_levels.png"),
            title="Retention by variant",
        ),
    ))
    figures.append((
        "What this experiment could see. At the traffic it collected, only effects "
        f"larger than {sensitivity['mde_relative']:.1%} relative were reliably detectable - "
        "the observed day-7 drop sits just past that line.",
        plots.power_curve_plot(
            curve,
            observed_effect=primary.test.relative_diff,
            mde=sensitivity["mde_relative"],
            target_power=config.power,
            path=os.path.join(FIG_DIR, "power_curve.png"),
            title="Power curve - day-7 retention",
        ),
    ))
    figures.append((
        "The same conclusion without a normal approximation: the posterior gives "
        f"{primary.bayesian.prob_treatment_better:.1%} probability that gate 40 is better.",
        plots.posterior_plot(
            primary.bayesian, os.path.join(FIG_DIR, "posterior_retention_7.png"),
            title="Day-7 retention - posterior lift",
        ),
    ))

    rounds = results.outcome("game_rounds")
    figures.append((
        "Game rounds per player, clipped at the 99th percentile. The metric is "
        "heavily right-skewed, which is why it is winsorized before testing and "
        "checked with a permutation test.",
        plots.distribution_plot(
            data.values("game_rounds", config.control),
            data.values("game_rounds", config.treatment),
            os.path.join(FIG_DIR, "gamerounds_distribution.png"),
            title="Game rounds per player",
            xlabel="Rounds played",
        ),
    ))
    if rounds.permutation is not None:
        figures.append((
            f"Permutation null for game rounds: {rounds.permutation.n_permutations:,} random "
            "re-assignments of the same players. The observed difference sits well inside "
            "the noise.",
            plots.null_distribution_plot(
                rounds.permutation, os.path.join(FIG_DIR, "permutation_null.png"),
                title="Game rounds - permutation null vs observed",
            ),
        ))
    figures.append((
        "Peeking at day-7 retention as traffic accumulates. A naive daily check would "
        f"have called the result at {len(naive_stops)} of 8 looks where the sequential "
        "boundary says to keep waiting.",
        plots.sequential_plot(looks, os.path.join(FIG_DIR, "sequential.png")),
    ))

    # ------------------------------------------------------------- reports
    raw_control = data.values("game_rounds", config.control)
    raw_treatment = data.values("game_rounds", config.treatment)
    raw_lift = (raw_treatment.mean() - raw_control.mean()) / raw_control.mean()
    without_whale = raw_control[raw_control < raw_control.max()]
    lift_without_whale = (raw_treatment.mean() - without_whale.mean()) / without_whale.mean()

    narrative = {
        "The engagement metric is one player wide": (
            f"<p>Raw mean rounds played differ by <strong>{raw_lift:+.2%}</strong> between "
            f"arms ({raw_control.mean():.2f} vs {raw_treatment.mean():.2f}). Remove the single "
            f"most extreme player - one account with {raw_control.max():,.0f} rounds against a "
            f"median of {np.median(np.concatenate([raw_control, raw_treatment])):,.0f} - and the "
            f"difference collapses to <strong>{lift_without_whale:+.2%}</strong>.</p>"
            f"<p>That is why the guardrail is winsorized at the 99th percentile "
            f"(cap = {rounds.winsor_cap:,.0f} rounds, computed on pooled data and applied to both "
            f"arms) before it is tested. Capping keeps every randomised player in their assigned "
            f"arm; dropping outliers would quietly remove units from one side. The permutation "
            f"test on the capped metric returns p = "
            f"{rounds.permutation.p_value:.3f} against the t-test's {rounds.test.p_value:.3f} - "
            f"the parametric approximation holds up here.</p>"
        ),
        "How much this experiment could see": (
            f"<p>With {sum(results.counts.values()):,} players split "
            f"{results.counts[config.control]:,}/{results.counts[config.treatment]:,}, the "
            f"smallest day-7 retention change detectable at {config.power:.0%} power was "
            f"<strong>{sensitivity['mde_relative']:+.2%}</strong> relative "
            f"({sensitivity['mde_absolute']:+.4f} absolute). The observed drop of "
            f"{primary.test.relative_diff:+.2%} is larger than that, which is why it "
            f"registers.</p><p>A 2% relative change - a plausible size for a gate tweak - "
            f"would have needed about {needed_for_2pct['n_total']:,} players, roughly "
            f"{needed_for_2pct['n_total'] / sum(results.counts.values()):.1f}x this "
            f"experiment. Ninety thousand users is not automatically 'enough data'; it is "
            f"enough for effects of a particular size.</p>"
        ),
        "Why there is no segment breakdown": (
            "<p>The dataset carries no pre-assignment attributes - no country, device, "
            "acquisition channel or tenure. The only other column, rounds played, is "
            "measured <em>after</em> assignment and is itself affected by the gate. "
            "Splitting results by it would compare groups that the treatment helped "
            "define, which manufactures differences rather than finding them. The "
            "toolkit supports segmentation "
            "(<code>Experiment.analyse_segments</code>, corrected across all slices); "
            "this experiment simply has nothing legitimate to segment on.</p>"
        ),
        "On the uneven split": (
            "<p>The arms are not exactly equal: 44,700 against 45,489, a "
            "49.56/50.44 split with a chi-square p of 0.0086. That would fail a naive "
            "0.05 threshold. The sample-ratio check uses 0.001 deliberately - it runs on "
            "every experiment, and at that threshold this imbalance is within what "
            "randomisation produces. It is reported rather than buried, and it is the "
            "one check that can invalidate everything below it.</p>"
        ),
        "What a naive daily check would have done": (
            "<p>Replaying the experiment in a random arrival order and testing at eight "
            f"points, a fixed 0.05 threshold fires at {int(looks['stop_naive'].sum())} of "
            f"8 looks, while the O'Brien-Fleming boundary fires at "
            f"{int(looks['stop_sequential'].sum())}. Repeated testing against a fixed "
            "threshold inflates the false positive rate well past 5%; alpha spending is "
            "what makes mid-flight checks safe.</p>"
        ),
    }

    build_html_report(results, figures=figures, output_path=REPORT_HTML, narrative=narrative)
    build_markdown_report(results, REPORT_MD)
    payload = results.to_dict()
    payload["sensitivity"] = sensitivity
    payload["sample_size_for_2pct_lift"] = needed_for_2pct
    payload["peeking"] = looks.to_dict(orient="records")
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    decision = results.decision()
    print(f"\n--- Decision ---\n{decision['recommendation'].upper()}: {decision['reason']}")
    print(f"\nWrote {REPORT_HTML}\n      {REPORT_MD}\n      {REPORT_JSON}")
    print(f"      {len(figures)} figures in {FIG_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
