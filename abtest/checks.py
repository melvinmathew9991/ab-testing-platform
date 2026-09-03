"""Trustworthiness checks that run before anyone is allowed to read a result.

A significant p-value from a broken experiment is worse than no result at
all. These checks catch the failure modes that actually happen in practice:
a broken split, metrics dominated by a handful of users, and a metric so
sparse the normal approximation does not hold.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from abtest.data import ExperimentData


@dataclass
class CheckResult:
    """Outcome of one diagnostic check."""

    name: str
    passed: bool
    severity: str  # "critical" | "warning" | "info"
    message: str
    details: dict | None = None

    @property
    def status(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.severity == "critical" else "WARN"

    def to_dict(self) -> dict:
        return {
            "check": self.name,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
        }


def sample_ratio_mismatch(
    n_control: int,
    n_treatment: int,
    expected_split: tuple[float, float] = (0.5, 0.5),
    alpha: float = 0.001,
) -> CheckResult:
    """Chi-square test that the observed split matches the intended one.

    A failing SRM check invalidates the experiment: if assignment is skewed,
    the two arms are not comparable and no amount of statistics fixes it.
    The threshold is deliberately strict (0.001) because this check runs on
    every experiment and should not cry wolf.
    """
    observed = np.array([n_control, n_treatment], dtype=float)
    total = observed.sum()
    expected = np.array(expected_split, dtype=float) * total

    if total == 0:
        return CheckResult(
            "sample_ratio_mismatch", False, "critical", "No units in the experiment"
        )

    chi2 = float(((observed - expected) ** 2 / expected).sum())
    p_value = float(stats.chi2.sf(chi2, df=1))
    passed = p_value >= alpha
    actual_ratio = n_control / total

    return CheckResult(
        name="sample_ratio_mismatch",
        passed=passed,
        severity="critical",
        message=(
            f"Split {actual_ratio:.3%}/{1 - actual_ratio:.3%} vs expected "
            f"{expected_split[0]:.1%}/{expected_split[1]:.1%} "
            f"(chi2={chi2:.2f}, p={p_value:.4f})"
            + ("" if passed else " - assignment is skewed, results are not trustworthy")
        ),
        details={
            "chi2": chi2,
            "p_value": p_value,
            "n_control": int(n_control),
            "n_treatment": int(n_treatment),
            "observed_ratio": actual_ratio,
            "threshold": alpha,
        },
    )


def outlier_influence(
    values: np.ndarray,
    metric_name: str,
    top_share: float = 0.001,
    warn_contribution: float = 0.05,
) -> CheckResult:
    """Flag metrics where a tiny fraction of units drives the total.

    When the top 0.1% of users contribute more than 5% of the metric, the
    mean is fragile and a single whale landing in one arm can move the
    result. That is a case for winsorizing or a rank-based test.
    """
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0 or v.sum() == 0:
        return CheckResult(
            f"outlier_influence[{metric_name}]",
            True,
            "info",
            f"{metric_name}: no positive mass to concentrate",
        )

    k = max(1, int(np.ceil(v.size * top_share)))
    top_sum = float(np.sort(v)[-k:].sum())
    contribution = top_sum / float(v.sum())
    passed = contribution <= warn_contribution

    return CheckResult(
        name=f"outlier_influence[{metric_name}]",
        passed=passed,
        severity="warning",
        message=(
            f"{metric_name}: top {k:,} units ({top_share:.2%} of the sample) hold "
            f"{contribution:.1%} of the total"
            + ("" if passed else " - consider winsorizing before testing the mean")
        ),
        details={
            "top_units": k,
            "contribution": contribution,
            "max_value": float(v.max()),
            "p99": float(np.quantile(v, 0.99)),
            "mean": float(v.mean()),
            "median": float(np.median(v)),
        },
    )


def normal_approximation(
    conversions: int, n: int, metric_name: str, minimum: int = 30
) -> CheckResult:
    """Check the success/failure counts support a normal approximation."""
    failures = n - conversions
    passed = min(conversions, failures) >= minimum
    return CheckResult(
        name=f"normal_approximation[{metric_name}]",
        passed=passed,
        severity="warning",
        message=(
            f"{metric_name}: {conversions:,} conversions / {failures:,} non-conversions"
            + (
                ""
                if passed
                else f" - fewer than {minimum} in a cell, prefer an exact or "
                f"bootstrap method"
            )
        ),
        details={"conversions": int(conversions), "failures": int(failures)},
    )


def segment_balance(
    data: ExperimentData, dimension: str, alpha: float = 0.001
) -> CheckResult:
    """Check a pre-experiment dimension is distributed alike across variants.

    Randomisation should balance every pre-assignment attribute. A large
    imbalance points at a bug in the assignment or in the data pipeline.
    """
    cfg = data.config
    table = pd.crosstab(data.df[dimension], data.df[cfg.variant_col])
    if table.shape[0] < 2 or table.shape[1] < 2:
        return CheckResult(
            f"segment_balance[{dimension}]",
            True,
            "info",
            f"{dimension}: not enough levels to test balance",
        )
    chi2, p_value, dof, _ = stats.chi2_contingency(table)
    passed = p_value >= alpha
    return CheckResult(
        name=f"segment_balance[{dimension}]",
        passed=passed,
        severity="warning",
        message=(
            f"{dimension}: chi2={chi2:.2f}, dof={dof}, p={p_value:.4f}"
            + ("" if passed else " - imbalanced across variants, check assignment")
        ),
        details={"chi2": float(chi2), "p_value": float(p_value), "dof": int(dof)},
    )


def run_all_checks(data: ExperimentData) -> list[CheckResult]:
    """Run the standard battery for an experiment."""
    cfg = data.config
    counts = data.counts()
    results: list[CheckResult] = [
        sample_ratio_mismatch(
            counts[cfg.control], counts[cfg.treatment], cfg.expected_split
        )
    ]

    for metric in cfg.metrics:
        pooled = data.df[metric.column].to_numpy(dtype=float)
        if metric.type == "binary":
            for variant in cfg.variants:
                v = data.values(metric, variant)
                results.append(
                    normal_approximation(
                        int(np.nansum(v)), int(v.size), f"{metric.name} / {variant}"
                    )
                )
        else:
            results.append(outlier_influence(pooled, metric.name))

    for issue in data.issues:
        results.append(
            CheckResult("data_quality", False, "warning", issue)
        )
    return results


def checks_to_frame(checks: list[CheckResult]) -> pd.DataFrame:
    return pd.DataFrame([c.to_dict() for c in checks])
