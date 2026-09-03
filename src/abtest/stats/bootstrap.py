"""Resampling methods: bootstrap confidence intervals and permutation tests.

These are the tools to reach for when the metric is not well behaved - heavy
tails, ratios, quantiles - and the normal approximation behind a t-test is
hard to defend.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from abtest.log import get_logger, log_duration

logger = get_logger(__name__)

Statistic = Callable[[np.ndarray], float]


@dataclass
class BootstrapResult:
    """Percentile bootstrap interval for a difference between two samples."""

    metric: str
    statistic_name: str
    observed_diff: float
    ci_low: float
    ci_high: float
    alpha: float
    n_bootstrap: int
    distribution: np.ndarray

    @property
    def significant(self) -> bool:
        """True when the interval excludes zero."""
        return not (self.ci_low <= 0 <= self.ci_high)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "statistic": self.statistic_name,
            "observed_diff": self.observed_diff,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "alpha": self.alpha,
            "n_bootstrap": self.n_bootstrap,
            "significant": self.significant,
        }


@dataclass
class PermutationResult:
    """Two-sided permutation (randomisation) test of the sharp null."""

    metric: str
    statistic_name: str
    observed_diff: float
    p_value: float
    alpha: float
    n_permutations: int
    null_distribution: np.ndarray

    @property
    def significant(self) -> bool:
        return bool(self.p_value < self.alpha)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "statistic": self.statistic_name,
            "observed_diff": self.observed_diff,
            "p_value": self.p_value,
            "alpha": self.alpha,
            "n_permutations": self.n_permutations,
            "significant": self.significant,
        }


#: Element budget per batch, so memory stays around 40 MB regardless of sample size.
_MAX_ELEMENTS = 5_000_000


def _resample_indices(rng, n: int, size: int, reps: int) -> np.ndarray:
    return rng.integers(0, n, size=(reps, size))


def _batch_size(requested: int, row_length: int) -> int:
    """Rows per batch that keep memory bounded for wide samples."""
    return max(1, min(requested, _MAX_ELEMENTS // max(row_length, 1)))


def _rowwise(statistic: Statistic, matrix: np.ndarray) -> np.ndarray:
    """Apply ``statistic`` to each row, vectorised when the callable allows it.

    ``np.mean``, ``np.median`` and friends accept an ``axis`` argument and run
    orders of magnitude faster that way; anything else falls back to a loop.
    """
    try:
        out = statistic(matrix, axis=1)  # type: ignore[call-arg]
    except TypeError:
        return np.apply_along_axis(statistic, 1, matrix)
    out = np.asarray(out, dtype=float)
    if out.shape != (matrix.shape[0],):
        return np.apply_along_axis(statistic, 1, matrix)
    return out


def bootstrap_ci(
    control: np.ndarray,
    treatment: np.ndarray,
    statistic: Statistic = np.mean,
    n_bootstrap: int = 10_000,
    alpha: float = 0.05,
    seed: int | None = 42,
    metric: str = "metric",
    batch_size: int = 1_000,
) -> BootstrapResult:
    """Percentile bootstrap CI for ``statistic(treatment) - statistic(control)``.

    Resampling runs in batches so memory stays bounded even for large samples
    and many replicates.
    """
    control = np.asarray(control, dtype=float)
    treatment = np.asarray(treatment, dtype=float)
    rng = np.random.default_rng(seed)

    observed = float(statistic(treatment)) - float(statistic(control))
    diffs = np.empty(n_bootstrap, dtype=float)

    done = 0
    step = _batch_size(batch_size, control.size + treatment.size)
    with log_duration(logger, f"Bootstrapped {metric} ({n_bootstrap:,} resamples)"):
        while done < n_bootstrap:
            reps = min(step, n_bootstrap - done)
            c_idx = _resample_indices(rng, control.size, control.size, reps)
            t_idx = _resample_indices(rng, treatment.size, treatment.size, reps)
            c_stat = _rowwise(statistic, control[c_idx])
            t_stat = _rowwise(statistic, treatment[t_idx])
            diffs[done : done + reps] = t_stat - c_stat
            done += reps

    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return BootstrapResult(
        metric=metric,
        statistic_name=getattr(statistic, "__name__", str(statistic)),
        observed_diff=observed,
        ci_low=float(lo),
        ci_high=float(hi),
        alpha=alpha,
        n_bootstrap=n_bootstrap,
        distribution=diffs,
    )


def permutation_test(
    control: np.ndarray,
    treatment: np.ndarray,
    statistic: Statistic = np.mean,
    n_permutations: int = 10_000,
    alpha: float = 0.05,
    seed: int | None = 42,
    metric: str = "metric",
    batch_size: int = 1_000,
) -> PermutationResult:
    """Permutation test: shuffle the labels, recompute the difference.

    The p-value uses the (r + 1) / (n + 1) correction, so it can never be
    exactly zero - with 10,000 permutations the floor is 1e-4.
    """
    control = np.asarray(control, dtype=float)
    treatment = np.asarray(treatment, dtype=float)
    pooled = np.concatenate([control, treatment])
    n0, n = control.size, pooled.size
    rng = np.random.default_rng(seed)

    observed = float(statistic(treatment)) - float(statistic(control))
    null = np.empty(n_permutations, dtype=float)

    done = 0
    step = _batch_size(batch_size, n)
    with log_duration(logger, f"Permuted {metric} ({n_permutations:,} permutations)"):
        while done < n_permutations:
            reps = min(step, n_permutations - done)
            # A partition on uniform noise splits each row into a random group
            # of size n0 and its complement - cheaper than a full sort, and a
            # full ordering is not needed.
            noise = rng.random((reps, n))
            order = np.argpartition(noise, n0 - 1, axis=1)
            shuffled = np.take_along_axis(np.broadcast_to(pooled, (reps, n)), order, axis=1)
            c_stat = _rowwise(statistic, shuffled[:, :n0])
            t_stat = _rowwise(statistic, shuffled[:, n0:])
            null[done : done + reps] = t_stat - c_stat
            done += reps

    extreme = int(np.sum(np.abs(null) >= abs(observed)))
    p_value = (extreme + 1) / (n_permutations + 1)

    return PermutationResult(
        metric=metric,
        statistic_name=getattr(statistic, "__name__", str(statistic)),
        observed_diff=observed,
        p_value=float(p_value),
        alpha=alpha,
        n_permutations=n_permutations,
        null_distribution=null,
    )
