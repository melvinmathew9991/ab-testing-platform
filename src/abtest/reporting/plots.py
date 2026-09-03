"""Charts for experiment reports.

Every figure here answers one question a reader will actually ask, and each
follows the same visual system: light chart surface, recessive grid and axes,
identity carried by a fixed two-slot categorical palette (control = blue,
treatment = orange) that never depends on which variant "won".

Colour values are taken verbatim from the validated reference palette: slots 1
and 2 of the categorical theme, the fixed status colours, and the chart chrome
inks. They are used as documented rather than re-stepped.
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")  # report generation is headless
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --- design tokens ---------------------------------------------------------
CONTROL = "#2a78d6"      # categorical slot 1 (blue)
TREATMENT = "#eb6834"    # categorical slot 2 (orange)
GOOD = "#0ca30c"
CRITICAL = "#d03b3b"
WARNING = "#fab219"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

_FONT_STACK = ["Segoe UI", "DejaVu Sans", "Arial", "sans-serif"]


def apply_style() -> None:
    """Apply the shared chart style to matplotlib's global rcParams."""
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.sans-serif": _FONT_STACK,
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": INK_SECONDARY,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": INK_SECONDARY,
            "ytick.labelcolor": INK_SECONDARY,
            "legend.frameon": False,
            "figure.dpi": 130,
        }
    )


def _title(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=22 if subtitle else 8)
    if subtitle:
        ax.text(
            0, 1.015, subtitle, transform=ax.transAxes, fontsize=9,
            color=INK_SECONDARY, va="bottom",
        )


def _save(fig, path: str | None):
    if path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
    return path


# ---------------------------------------------------------------------------
def lift_forest(summary: pd.DataFrame, path: str | None = None, title: str = "Relative lift by metric"):
    """Point estimate and 95% CI per metric, on a shared relative scale.

    The reference line at zero is the decision line: intervals that cross it
    are consistent with no effect, whatever the point estimate looks like.
    """
    apply_style()
    df = summary.iloc[::-1].reset_index(drop=True)
    n = len(df)
    fig, ax = plt.subplots(figsize=(8.0, 1.4 + 0.52 * n))
    y = np.arange(n)
    span = float(np.nanmax(df["rel_ci_high"]) - np.nanmin(df["rel_ci_low"])) or 0.02
    pad = span * 0.04

    for i, row in df.iterrows():
        colour = GOOD if row["verdict"] == "win" else (CRITICAL if row["verdict"] == "regression" else MUTED)
        ax.plot(
            [row["rel_ci_low"], row["rel_ci_high"]], [i, i],
            color=colour, linewidth=2, solid_capstyle="round", zorder=2,
        )
        ax.scatter(
            [row["relative_diff"]], [i], s=64, color=colour,
            edgecolor=SURFACE, linewidth=2, zorder=3,
        )
        ax.text(
            row["rel_ci_high"] + pad, i,
            f"{row['relative_diff']:+.2%}  (p={row['p_adjusted']:.3f})",
            fontsize=9, color=INK_SECONDARY, va="center", ha="left",
        )

    ax.axvline(0, color=AXIS, linewidth=1.2, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['metric']}\n{r['role']}" for _, r in df.iterrows()], fontsize=9)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
    ax.set_xlabel("Relative change vs control (95% CI)")
    ax.grid(axis="y", visible=False)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlim(
        min(float(np.nanmin(df["rel_ci_low"])) - pad * 2, -pad * 2),
        float(np.nanmax(df["rel_ci_high"])) + span * 0.75,
    )
    _title(ax, title, "Green = significant win, red = significant regression, grey = no detectable effect")
    fig.tight_layout()
    return _save(fig, path)


def metric_bars(summary: pd.DataFrame, path: str | None = None, title: str = "Metric levels by variant"):
    """Absolute level of each metric in both arms, side by side."""
    apply_style()
    n = len(summary)
    fig, ax = plt.subplots(figsize=(1.9 + 1.7 * n, 4.2))
    x = np.arange(n)
    width = 0.34
    gap = 0.02  # 2px-equivalent surface gap between adjacent fills

    ax.bar(x - width / 2 - gap / 2, summary["control"], width, label="Control", color=CONTROL)
    ax.bar(x + width / 2 + gap / 2, summary["treatment"], width, label="Treatment", color=TREATMENT)

    for i, row in summary.reset_index(drop=True).iterrows():
        for offset, key in ((-width / 2 - gap / 2, "control"), (width / 2 + gap / 2, "treatment")):
            ax.text(
                i + offset, row[key], f"{row[key]:.4g}", ha="center", va="bottom",
                fontsize=8.5, color=INK_SECONDARY,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(summary["metric"], fontsize=9)
    ax.set_ylabel("Metric value")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right", fontsize=9, labelcolor=INK_SECONDARY)
    _title(ax, title)
    fig.tight_layout()
    return _save(fig, path)


def power_curve_plot(
    curve: pd.DataFrame,
    observed_effect: float | None = None,
    mde: float | None = None,
    target_power: float = 0.80,
    path: str | None = None,
    title: str = "Power curve at the achieved sample size",
):
    """Detection probability as a function of the true effect."""
    apply_style()
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(curve["effect_relative"], curve["power"], color=CONTROL, linewidth=2, zorder=3)
    ax.axhline(target_power, color=MUTED, linewidth=1, linestyle="--", zorder=2)
    ax.text(
        curve["effect_relative"].max(), target_power + 0.02,
        f"target power {target_power:.0%}", fontsize=8.5, color=MUTED, ha="right",
    )

    if mde is not None:
        ax.axvline(mde, color=TREATMENT, linewidth=1.6, zorder=2)
        ax.text(mde, 0.04, f"  MDE {mde:+.1%}", fontsize=9, color=TREATMENT, ha="left")
    if observed_effect is not None:
        ax.axvline(abs(observed_effect), color=INK_SECONDARY, linewidth=1.2, linestyle=":", zorder=2)
        ax.text(
            abs(observed_effect), 0.92, f"observed {observed_effect:+.2%}  ",
            fontsize=9, color=INK_SECONDARY, ha="right",
        )

    ax.set_xlabel("True relative effect")
    ax.set_ylabel("Probability of detecting it")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_ylim(0, 1.02)
    _title(ax, title, "Effects to the left of the orange line are not reliably detectable with this traffic")
    fig.tight_layout()
    return _save(fig, path)


def posterior_plot(
    bayes, path: str | None = None, title: str = "Posterior distribution of the lift"
):
    """Posterior for the relative lift, with the probability mass either side of zero."""
    apply_style()
    # The result object carries the posterior summary rather than the draws,
    # so the interval is drawn as an interval.
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    lo, med, hi = bayes.lift_ci_low, bayes.lift_median, bayes.lift_ci_high
    ax.plot([lo, hi], [0, 0], color=CONTROL, linewidth=3, solid_capstyle="round")
    ax.scatter([med], [0], s=90, color=CONTROL, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.axvline(0, color=AXIS, linewidth=1.2)
    ax.set_yticks([])
    ax.set_ylim(-0.5, 0.5)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
    ax.set_xlabel("Relative lift (95% credible interval)")
    ax.grid(axis="y", visible=False)
    ax.text(
        med, 0.12,
        f"P(treatment better) = {bayes.prob_treatment_better:.1%}",
        ha="center", fontsize=9.5, color=INK,
    )
    ax.text(
        med, -0.2, f"median {med:+.2%}   expected loss if shipped {bayes.expected_loss_treatment:.4f}",
        ha="center", fontsize=8.5, color=INK_SECONDARY,
    )
    _title(ax, title, f"Beta-Binomial posterior, {bayes.metric}")
    fig.tight_layout()
    return _save(fig, path)


def null_distribution_plot(
    permutation, path: str | None = None, title: str = "Permutation null vs observed effect"
):
    """Where the observed difference falls in the distribution of pure noise."""
    apply_style()
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    null = permutation.null_distribution
    ax.hist(null, bins=60, color=CONTROL, alpha=0.85, edgecolor=SURFACE, linewidth=0.5)
    ax.axvline(permutation.observed_diff, color=TREATMENT, linewidth=2, zorder=3)
    ax.text(
        permutation.observed_diff, ax.get_ylim()[1] * 0.92,
        f"  observed {permutation.observed_diff:+.4g}\n  p = {permutation.p_value:.4f}",
        color=TREATMENT, fontsize=9, va="top",
    )
    ax.set_xlabel(f"Difference in {permutation.statistic_name} under random re-assignment")
    ax.set_ylabel("Permutations")
    ax.grid(axis="x", visible=False)
    _title(
        ax, title,
        f"{permutation.n_permutations:,} random re-assignments of the same units",
    )
    fig.tight_layout()
    return _save(fig, path)


def sequential_plot(
    looks: pd.DataFrame, path: str | None = None, title: str = "Peeking: sequential boundary vs fixed threshold"
):
    """Z-score at each interim look against the alpha-spending boundary."""
    apply_style()
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    x = looks["information_fraction"]
    ax.plot(x, looks["z_critical"], color=MUTED, linewidth=1.6, linestyle="--", label="Sequential boundary")
    ax.plot(x, -looks["z_critical"], color=MUTED, linewidth=1.6, linestyle="--")
    ax.axhline(1.96, color=AXIS, linewidth=1.2, label="Fixed-horizon 1.96")
    ax.axhline(-1.96, color=AXIS, linewidth=1.2)
    ax.plot(x, looks["z_score"], color=CONTROL, linewidth=2, marker="o", markersize=7,
            markeredgecolor=SURFACE, markeredgewidth=1.5, label="Observed z", zorder=3)

    for _, row in looks.iterrows():
        if row["stop_naive"] and not row["stop_sequential"]:
            ax.scatter([row["information_fraction"]], [row["z_score"]], s=150,
                       facecolor="none", edgecolor=WARNING, linewidth=2, zorder=4)

    ax.set_xlabel("Information fraction (share of planned sample collected)")
    ax.set_ylabel("z-score")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.legend(fontsize=9, labelcolor=INK_SECONDARY, loc="upper right")
    _title(ax, title, "Circled points would have been called significant by a naive daily check")
    fig.tight_layout()
    return _save(fig, path)


def distribution_plot(
    control: np.ndarray,
    treatment: np.ndarray,
    path: str | None = None,
    title: str = "Metric distribution by variant",
    clip_quantile: float = 0.99,
    xlabel: str = "Metric value",
):
    """Overlaid distributions, clipped so the tail does not flatten the body."""
    apply_style()
    control = np.asarray(control, dtype=float)
    treatment = np.asarray(treatment, dtype=float)
    cap = float(np.quantile(np.concatenate([control, treatment]), clip_quantile))
    bins = np.linspace(0, max(cap, 1e-9), 50)

    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.hist(np.clip(control, 0, cap), bins=bins, color=CONTROL, alpha=0.6, label="Control")
    ax.hist(np.clip(treatment, 0, cap), bins=bins, color=TREATMENT, alpha=0.6, label="Treatment")
    ax.set_xlabel(f"{xlabel} (clipped at the {clip_quantile:.0%} quantile = {cap:,.0f})")
    ax.set_ylabel("Users")
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=9, labelcolor=INK_SECONDARY)
    _title(ax, title, "Heavy right tail: the mean is driven by a small number of users")
    fig.tight_layout()
    return _save(fig, path)


def segment_forest(
    segments: pd.DataFrame,
    metric: str,
    path: str | None = None,
    title: str | None = None,
):
    """Per-segment lift for one metric, with corrected significance."""
    apply_style()
    df = segments[segments["metric"] == metric].copy()
    if df.empty:
        return None
    df["rel_ci_low"] = df["ci_low"] / df["control"]
    df["rel_ci_high"] = df["ci_high"] / df["control"]
    df = df.iloc[::-1].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(7.6, 1.0 + 0.5 * len(df)))
    for i, row in df.iterrows():
        colour = CRITICAL if (row["significant"] and row["relative_diff"] < 0) else (
            GOOD if row["significant"] else MUTED
        )
        ax.plot([row["rel_ci_low"], row["rel_ci_high"]], [i, i], color=colour, linewidth=2,
                solid_capstyle="round", zorder=2)
        ax.scatter([row["relative_diff"]], [i], s=54, color=colour, edgecolor=SURFACE,
                   linewidth=1.6, zorder=3)
    ax.axvline(0, color=AXIS, linewidth=1.2)
    ax.set_yticks(np.arange(len(df)))
    ax.set_yticklabels([f"{r['dimension']} = {r['segment']}" for _, r in df.iterrows()], fontsize=9)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
    ax.set_xlabel("Relative change vs control (95% CI)")
    ax.grid(axis="y", visible=False)
    _title(
        ax, title or f"{metric} by segment",
        "Exploratory: p-values corrected across all segments (Benjamini-Hochberg)",
    )
    fig.tight_layout()
    return _save(fig, path)
