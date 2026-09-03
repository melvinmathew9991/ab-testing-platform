"""Sequential testing: how to peek at a running experiment without inflating
the false positive rate.

Checking a fixed-horizon p-value every day and stopping at the first p < 0.05
pushes the real error rate well above 5%. The Lan-DeMets alpha-spending
approach fixes this by spending the error budget gradually: early looks face
a much stricter bar than the final one.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


def obrien_fleming_spending(information_fraction: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Cumulative alpha spent by the O'Brien-Fleming spending function."""
    t = np.clip(np.asarray(information_fraction, dtype=float), 1e-9, 1.0)
    return 2 * (1 - stats.norm.cdf(stats.norm.ppf(1 - alpha / 2) / np.sqrt(t)))


def obrien_fleming_boundaries(n_looks: int, alpha: float = 0.05) -> pd.DataFrame:
    """Critical z-values for ``n_looks`` equally spaced interim analyses.

    Returns a frame with the information fraction, the cumulative alpha spent,
    the alpha available at that look and the corresponding two-sided z and
    p-value thresholds.
    """
    if n_looks < 1:
        raise ValueError("n_looks must be at least 1")
    t = np.arange(1, n_looks + 1) / n_looks
    cumulative = obrien_fleming_spending(t, alpha)
    incremental = np.diff(np.concatenate([[0.0], cumulative]))
    z_crit = stats.norm.ppf(1 - cumulative / 2)
    return pd.DataFrame(
        {
            "look": np.arange(1, n_looks + 1),
            "information_fraction": t,
            "alpha_spent_cumulative": cumulative,
            "alpha_spent_at_look": incremental,
            "z_critical": z_crit,
            "p_threshold": 2 * stats.norm.sf(z_crit),
        }
    )


@dataclass
class SequentialLook:
    """One interim analysis of a running experiment."""

    look: int
    label: str
    n_control: int
    n_treatment: int
    rate_control: float
    rate_treatment: float
    z_score: float
    p_value: float
    p_threshold: float
    information_fraction: float
    crossed: bool


def sequential_analysis(
    looks: list[dict],
    alpha: float = 0.05,
    planned_n_total: int | None = None,
) -> pd.DataFrame:
    """Replay a series of interim looks against O'Brien-Fleming boundaries.

    Args:
        looks: Ordered list of cumulative snapshots, each with keys
            ``label``, ``conversions_control``, ``n_control``,
            ``conversions_treatment``, ``n_treatment``.
        planned_n_total: Total sample the experiment was powered for. Used to
            compute the information fraction; defaults to the sample present
            at the final look.

    Returns:
        One row per look, with a naive fixed-horizon p-value alongside the
        sequential threshold, so the two decisions can be compared directly.
    """
    if not looks:
        raise ValueError("At least one look is required")

    final_n = looks[-1]["n_control"] + looks[-1]["n_treatment"]
    planned = planned_n_total or final_n

    rows = []
    crossed_already = False
    for i, look in enumerate(looks, start=1):
        n0, n1 = look["n_control"], look["n_treatment"]
        c0, c1 = look["conversions_control"], look["conversions_treatment"]
        p0, p1 = c0 / n0, c1 / n1
        pooled = (c0 + c1) / (n0 + n1)
        se = np.sqrt(pooled * (1 - pooled) * (1 / n0 + 1 / n1))
        z = (p1 - p0) / se if se > 0 else 0.0
        p_value = float(2 * stats.norm.sf(abs(z)))

        info = min((n0 + n1) / planned, 1.0)
        spent = float(obrien_fleming_spending(np.array([info]), alpha)[0])
        z_crit = float(stats.norm.ppf(1 - spent / 2))
        threshold = float(2 * stats.norm.sf(z_crit))
        crossed = bool(abs(z) >= z_crit)
        crossed_already = crossed_already or crossed

        rows.append(
            {
                "look": i,
                "label": look.get("label", f"look {i}"),
                "n_total": n0 + n1,
                "information_fraction": info,
                "rate_control": p0,
                "rate_treatment": p1,
                "absolute_diff": p1 - p0,
                "z_score": z,
                "p_value_fixed": p_value,
                "p_threshold_sequential": threshold,
                "z_critical": z_crit,
                "stop_sequential": crossed,
                "stop_naive": p_value < alpha,
                "stopped_by_now": crossed_already,
            }
        )
    return pd.DataFrame(rows)
