"""Variance reduction and outlier handling.

Both techniques buy sensitivity: CUPED by removing pre-experiment variance,
winsorization by stopping a handful of extreme users from dominating the
mean. Neither changes what is being estimated when applied to both arms.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from abtest.exceptions import ConfigurationError, DataValidationError


@dataclass
class CupedResult:
    """Outcome of a CUPED adjustment."""

    theta: float
    variance_before: float
    variance_after: float
    adjusted_control: np.ndarray
    adjusted_treatment: np.ndarray

    @property
    def variance_reduction(self) -> float:
        """Fraction of variance removed, e.g. 0.30 = 30% less variance."""
        if self.variance_before == 0:
            return 0.0
        return 1 - self.variance_after / self.variance_before

    @property
    def effective_sample_gain(self) -> float:
        """Sample-size multiplier this reduction is worth.

        Halving the variance is worth doubling the traffic, so the gain is
        ``1 / (1 - variance_reduction)``.
        """
        if self.variance_reduction >= 1:
            return float("inf")
        return 1 / (1 - self.variance_reduction)


def cuped_adjust(
    y_control: np.ndarray,
    x_control: np.ndarray,
    y_treatment: np.ndarray,
    x_treatment: np.ndarray,
) -> CupedResult:
    """CUPED: remove variance explained by a pre-experiment covariate.

    ``theta`` is estimated on the pooled data - a covariate measured before
    assignment cannot be affected by the treatment, so pooling is safe and
    keeps the estimator unbiased.

    Args:
        y_*: In-experiment metric values per unit.
        x_*: Pre-experiment covariate for the same units, same order.
    """
    y_c = np.asarray(y_control, dtype=float)
    x_c = np.asarray(x_control, dtype=float)
    y_t = np.asarray(y_treatment, dtype=float)
    x_t = np.asarray(x_treatment, dtype=float)

    if y_c.shape != x_c.shape or y_t.shape != x_t.shape:
        raise DataValidationError("Metric and covariate arrays must align unit by unit")

    y_all = np.concatenate([y_c, y_t])
    x_all = np.concatenate([x_c, x_t])
    var_x = x_all.var(ddof=1)
    theta = float(np.cov(y_all, x_all, ddof=1)[0, 1] / var_x) if var_x > 0 else 0.0
    x_mean = float(x_all.mean())

    adj_c = y_c - theta * (x_c - x_mean)
    adj_t = y_t - theta * (x_t - x_mean)

    return CupedResult(
        theta=theta,
        variance_before=float(y_all.var(ddof=1)),
        variance_after=float(np.concatenate([adj_c, adj_t]).var(ddof=1)),
        adjusted_control=adj_c,
        adjusted_treatment=adj_t,
    )


def winsorize(
    values: np.ndarray,
    upper_quantile: float = 0.99,
    lower_quantile: float | None = None,
    cap: float | None = None,
) -> tuple[np.ndarray, float]:
    """Cap extreme values instead of dropping the users that produced them.

    Dropping outliers drops units and can break the randomisation; capping
    keeps every unit in its assigned arm. Pass ``cap`` to apply a threshold
    computed elsewhere - the caller should compute one threshold on the
    pooled data and reuse it for both arms.

    Returns:
        The capped array and the upper threshold that was applied.
    """
    v = np.asarray(values, dtype=float)
    if cap is None:
        if not 0 < upper_quantile <= 1:
            raise ConfigurationError("upper_quantile must be in (0, 1]")
        cap = float(np.quantile(v[~np.isnan(v)], upper_quantile))
    out = np.minimum(v, cap)
    if lower_quantile is not None:
        floor = float(np.quantile(v[~np.isnan(v)], lower_quantile))
        out = np.maximum(out, floor)
    return out, float(cap)
