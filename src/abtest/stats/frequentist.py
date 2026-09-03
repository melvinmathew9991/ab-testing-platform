"""Frequentist two-sample tests for binary and continuous metrics.

Both tests return the same :class:`TestResult` container so that downstream
reporting never needs to know which test produced the numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from scipy import stats

Alternative = str  # one of: two-sided, larger, smaller


@dataclass
class TestResult:
    """Outcome of a single two-sample comparison.

    ``absolute_diff`` is treatment minus control in the metric's own units;
    ``relative_diff`` is that difference as a fraction of the control value
    (the "lift" stakeholders ask for). The confidence interval is always on
    the absolute difference.
    """

    metric: str
    method: str
    n_control: int
    n_treatment: int
    mean_control: float
    mean_treatment: float
    absolute_diff: float
    relative_diff: float
    ci_low: float
    ci_high: float
    standard_error: float
    statistic: float
    p_value: float
    dof: float
    alpha: float
    significant: bool
    mde_absolute: float
    power_observed: float = float("nan")
    alternative: Alternative = "two-sided"

    @property
    def relative_ci(self) -> tuple[float, float]:
        """Confidence interval expressed as relative lift on control."""
        if self.mean_control == 0:
            return (float("nan"), float("nan"))
        return (self.ci_low / self.mean_control, self.ci_high / self.mean_control)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["relative_ci_low"], d["relative_ci_high"] = self.relative_ci
        return d

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        verdict = "SIGNIFICANT" if self.significant else "not significant"
        return (
            f"<{self.metric}: {self.mean_control:.4g} -> {self.mean_treatment:.4g} "
            f"({self.relative_diff:+.2%}), p={self.p_value:.4g}, {verdict}>"
        )


def _pvalue_from_z(z: float, alternative: Alternative) -> float:
    if alternative == "two-sided":
        return float(2 * stats.norm.sf(abs(z)))
    if alternative == "larger":
        return float(stats.norm.sf(z))
    if alternative == "smaller":
        return float(stats.norm.cdf(z))
    raise ValueError(f"Unknown alternative {alternative!r}")


def _pvalue_from_t(t_stat: float, dof: float, alternative: Alternative) -> float:
    if alternative == "two-sided":
        return float(2 * stats.t.sf(abs(t_stat), dof))
    if alternative == "larger":
        return float(stats.t.sf(t_stat, dof))
    if alternative == "smaller":
        return float(stats.t.cdf(t_stat, dof))
    raise ValueError(f"Unknown alternative {alternative!r}")


def proportion_test(
    conversions_control: int,
    n_control: int,
    conversions_treatment: int,
    n_treatment: int,
    alpha: float = 0.05,
    alternative: Alternative = "two-sided",
    power: float = 0.80,
    metric: str = "conversion_rate",
) -> TestResult:
    """Two-proportion z-test.

    The test statistic uses the pooled standard error (valid under the null),
    while the confidence interval uses the unpooled standard error. That is
    the standard combination and keeps the interval consistent with the
    point estimate.
    """
    if min(n_control, n_treatment) <= 0:
        raise ValueError("Both variants need at least one unit")
    if conversions_control > n_control or conversions_treatment > n_treatment:
        raise ValueError("Conversions cannot exceed the number of units")

    p0 = conversions_control / n_control
    p1 = conversions_treatment / n_treatment
    diff = p1 - p0

    pooled = (conversions_control + conversions_treatment) / (n_control + n_treatment)
    se_pooled = float(np.sqrt(pooled * (1 - pooled) * (1 / n_control + 1 / n_treatment)))
    se_unpooled = float(
        np.sqrt(p0 * (1 - p0) / n_control + p1 * (1 - p1) / n_treatment)
    )

    z = diff / se_pooled if se_pooled > 0 else 0.0
    p_value = _pvalue_from_z(z, alternative)

    z_crit = float(stats.norm.ppf(1 - alpha / 2))
    ci_low, ci_high = diff - z_crit * se_unpooled, diff + z_crit * se_unpooled
    mde = (z_crit + float(stats.norm.ppf(power))) * se_unpooled

    # Power the design actually had against the effect that was observed.
    observed_power = float(
        stats.norm.sf(z_crit - abs(diff) / se_unpooled)
        if se_unpooled > 0
        else np.nan
    )

    return TestResult(
        metric=metric,
        method="two-proportion z-test",
        n_control=int(n_control),
        n_treatment=int(n_treatment),
        mean_control=float(p0),
        mean_treatment=float(p1),
        absolute_diff=float(diff),
        relative_diff=float(diff / p0) if p0 else float("nan"),
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        standard_error=se_unpooled,
        statistic=float(z),
        p_value=float(p_value),
        dof=float("inf"),
        alpha=alpha,
        significant=bool(p_value < alpha),
        mde_absolute=float(mde),
        power_observed=observed_power,
        alternative=alternative,
    )


def welch_ttest(
    control: np.ndarray,
    treatment: np.ndarray,
    alpha: float = 0.05,
    alternative: Alternative = "two-sided",
    power: float = 0.80,
    metric: str = "mean",
) -> TestResult:
    """Welch's t-test for two independent samples with unequal variances.

    Welch rather than Student is the right default for experiments: a
    treatment can change the variance of a metric as well as its mean.
    """
    control = np.asarray(control, dtype=float)
    treatment = np.asarray(treatment, dtype=float)
    control = control[~np.isnan(control)]
    treatment = treatment[~np.isnan(treatment)]

    n0, n1 = control.size, treatment.size
    if min(n0, n1) < 2:
        raise ValueError("Welch's t-test needs at least two observations per variant")

    m0, m1 = float(control.mean()), float(treatment.mean())
    v0, v1 = float(control.var(ddof=1)), float(treatment.var(ddof=1))
    se = float(np.sqrt(v0 / n0 + v1 / n1))
    diff = m1 - m0

    if se == 0:
        dof, t_stat, p_value = float(n0 + n1 - 2), 0.0, 1.0
    else:
        # Welch-Satterthwaite: each variance is paired with the sample size
        # it was estimated from.
        dof = (v0 / n0 + v1 / n1) ** 2 / (
            (v0 / n0) ** 2 / (n0 - 1) + (v1 / n1) ** 2 / (n1 - 1)
        )
        t_stat = diff / se
        p_value = _pvalue_from_t(t_stat, dof, alternative)

    t_crit = float(stats.t.ppf(1 - alpha / 2, dof))
    ci_low, ci_high = diff - t_crit * se, diff + t_crit * se
    mde = (t_crit + float(stats.t.ppf(power, dof))) * se
    observed_power = float(
        stats.norm.sf(stats.norm.ppf(1 - alpha / 2) - abs(diff) / se)
        if se > 0
        else np.nan
    )

    return TestResult(
        metric=metric,
        method="Welch's t-test",
        n_control=int(n0),
        n_treatment=int(n1),
        mean_control=m0,
        mean_treatment=m1,
        absolute_diff=float(diff),
        relative_diff=float(diff / m0) if m0 else float("nan"),
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        standard_error=se,
        statistic=float(t_stat),
        p_value=float(p_value),
        dof=float(dof),
        alpha=alpha,
        significant=bool(p_value < alpha),
        mde_absolute=float(mde),
        power_observed=observed_power,
        alternative=alternative,
    )
