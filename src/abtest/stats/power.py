"""Power analysis: how much traffic an experiment needs, and what effect it
could have detected once it is over.

Everything here is written for the two-proportion case (the common one for
conversion metrics) plus a generic variant that works from a standard
deviation, which covers continuous metrics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from abtest.exceptions import ConfigurationError


def sample_size_proportions(
    baseline_rate: float,
    mde_relative: float | None = None,
    mde_absolute: float | None = None,
    alpha: float = 0.05,
    power: float = 0.80,
    ratio: float = 1.0,
    alternative: str = "two-sided",
) -> dict:
    """Units per variant needed to detect a given effect.

    Args:
        baseline_rate: Conversion rate expected in control.
        mde_relative: Target effect as a fraction of baseline (0.05 = +5%).
        mde_absolute: Target effect in percentage points; overrides
            ``mde_relative`` when given.
        ratio: Treatment size divided by control size (1.0 = even split).

    Returns:
        Dict with ``n_control``, ``n_treatment`` and ``n_total``.
    """
    if not 0 < baseline_rate < 1:
        raise ConfigurationError("baseline_rate must be in (0, 1)")
    if mde_absolute is None:
        if mde_relative is None:
            raise ConfigurationError("Provide either mde_relative or mde_absolute")
        mde_absolute = baseline_rate * mde_relative
    if mde_absolute == 0:
        raise ConfigurationError("The minimum detectable effect cannot be zero")

    p0 = baseline_rate
    p1 = p0 + mde_absolute
    if not 0 < p1 < 1:
        raise ConfigurationError("baseline + effect must stay within (0, 1)")

    z_alpha = stats.norm.ppf(1 - alpha / 2) if alternative == "two-sided" else stats.norm.ppf(1 - alpha)
    z_beta = stats.norm.ppf(power)

    # Unequal allocation: variance of the difference scales with 1 + 1/ratio.
    pooled_var = p0 * (1 - p0) + p1 * (1 - p1) / ratio
    n_control = ((z_alpha + z_beta) ** 2 * pooled_var) / mde_absolute**2
    n_control = int(np.ceil(n_control))
    n_treatment = int(np.ceil(n_control * ratio))

    return {
        "n_control": n_control,
        "n_treatment": n_treatment,
        "n_total": n_control + n_treatment,
        "baseline_rate": p0,
        "mde_absolute": float(mde_absolute),
        "mde_relative": float(mde_absolute / p0),
        "alpha": alpha,
        "power": power,
    }


def sample_size_means(
    std: float,
    mde_absolute: float,
    alpha: float = 0.05,
    power: float = 0.80,
    ratio: float = 1.0,
) -> dict:
    """Units per variant needed to detect ``mde_absolute`` on a continuous metric."""
    if std <= 0:
        raise ConfigurationError("std must be positive")
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    n_control = ((z_alpha + z_beta) ** 2 * std**2 * (1 + 1 / ratio)) / mde_absolute**2
    n_control = int(np.ceil(n_control))
    return {
        "n_control": n_control,
        "n_treatment": int(np.ceil(n_control * ratio)),
        "n_total": n_control + int(np.ceil(n_control * ratio)),
        "mde_absolute": float(mde_absolute),
        "alpha": alpha,
        "power": power,
    }


def power_for_proportions(
    baseline_rate: float,
    effect_absolute: float,
    n_control: int,
    n_treatment: int | None = None,
    alpha: float = 0.05,
) -> float:
    """Probability of detecting ``effect_absolute`` with this much traffic."""
    n_treatment = n_treatment or n_control
    p0 = baseline_rate
    p1 = p0 + effect_absolute
    if not 0 < p1 < 1:
        return float("nan")
    se = np.sqrt(p0 * (1 - p0) / n_control + p1 * (1 - p1) / n_treatment)
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    # Two-sided power, both tails (the wrong-side tail is negligible but free).
    upper = stats.norm.sf(z_alpha - abs(effect_absolute) / se)
    lower = stats.norm.cdf(-z_alpha - abs(effect_absolute) / se)
    return float(upper + lower)


def mde_for_sample(
    baseline_rate: float,
    n_control: int,
    n_treatment: int | None = None,
    alpha: float = 0.05,
    power: float = 0.80,
) -> dict:
    """Smallest effect this sample size can reliably detect.

    Solved iteratively because the standard error itself depends on the
    effect size through the treatment variance.
    """
    n_treatment = n_treatment or n_control
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    p0 = baseline_rate

    mde = (z_alpha + z_beta) * np.sqrt(
        p0 * (1 - p0) * (1 / n_control + 1 / n_treatment)
    )
    for _ in range(50):
        p1 = min(max(p0 + mde, 1e-9), 1 - 1e-9)
        se = np.sqrt(p0 * (1 - p0) / n_control + p1 * (1 - p1) / n_treatment)
        new = (z_alpha + z_beta) * se
        if abs(new - mde) < 1e-12:
            break
        mde = new
    return {
        "mde_absolute": float(mde),
        "mde_relative": float(mde / p0),
        "n_control": int(n_control),
        "n_treatment": int(n_treatment),
        "alpha": alpha,
        "power": power,
    }


def power_curve(
    baseline_rate: float,
    effects_relative: np.ndarray | None = None,
    n_control: int = 10_000,
    n_treatment: int | None = None,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Power as a function of true effect size, for a fixed sample size."""
    if effects_relative is None:
        effects_relative = np.linspace(0.0, 0.30, 61)
    rows = []
    for rel in effects_relative:
        abs_effect = baseline_rate * rel
        rows.append(
            {
                "effect_relative": float(rel),
                "effect_absolute": float(abs_effect),
                "power": power_for_proportions(
                    baseline_rate, abs_effect, n_control, n_treatment, alpha
                ),
            }
        )
    return pd.DataFrame(rows)


def sample_size_curve(
    baseline_rate: float,
    effects_relative: np.ndarray | None = None,
    alpha: float = 0.05,
    power: float = 0.80,
) -> pd.DataFrame:
    """Traffic required per variant across a range of target effects."""
    if effects_relative is None:
        effects_relative = np.linspace(0.01, 0.30, 30)
    rows = []
    for rel in effects_relative:
        try:
            res = sample_size_proportions(
                baseline_rate, mde_relative=float(rel), alpha=alpha, power=power
            )
        except ValueError:
            continue
        rows.append(
            {
                "effect_relative": float(rel),
                "n_per_variant": res["n_control"],
                "n_total": res["n_total"],
            }
        )
    return pd.DataFrame(rows)
