"""Bayesian view of a binary experiment.

A Beta-Binomial model answers the two questions stakeholders actually ask:
"how likely is B better than A?" and "if I ship B and I am wrong, how much
do I lose?". Both are decision-ready in a way a p-value is not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BayesianResult:
    """Posterior summary for a two-variant binary metric."""

    metric: str
    prob_treatment_better: float
    expected_loss_treatment: float
    expected_loss_control: float
    lift_median: float
    lift_ci_low: float
    lift_ci_high: float
    posterior_mean_control: float
    posterior_mean_treatment: float
    n_samples: int
    prior: tuple[float, float]

    @property
    def decision(self) -> str:
        """Plain-language read of the posterior at a 95% threshold."""
        if self.prob_treatment_better >= 0.95:
            return "ship treatment"
        if self.prob_treatment_better <= 0.05:
            return "keep control"
        return "inconclusive"

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "prob_treatment_better": self.prob_treatment_better,
            "expected_loss_treatment": self.expected_loss_treatment,
            "expected_loss_control": self.expected_loss_control,
            "lift_median": self.lift_median,
            "lift_ci_low": self.lift_ci_low,
            "lift_ci_high": self.lift_ci_high,
            "decision": self.decision,
        }


def beta_binomial_test(
    conversions_control: int,
    n_control: int,
    conversions_treatment: int,
    n_treatment: int,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    n_samples: int = 100_000,
    credible_mass: float = 0.95,
    seed: int | None = 42,
    metric: str = "conversion_rate",
) -> BayesianResult:
    """Posterior comparison of two conversion rates.

    With the default Beta(1, 1) prior every rate is equally plausible before
    seeing data, so the posterior is driven entirely by the experiment.

    ``expected_loss_treatment`` is the average conversion rate given up by
    shipping treatment when control is in fact better - the quantity to
    compare against a "loss we can tolerate" threshold.
    """
    rng = np.random.default_rng(seed)
    post_c = rng.beta(
        prior_alpha + conversions_control,
        prior_beta + n_control - conversions_control,
        n_samples,
    )
    post_t = rng.beta(
        prior_alpha + conversions_treatment,
        prior_beta + n_treatment - conversions_treatment,
        n_samples,
    )

    prob_better = float(np.mean(post_t > post_c))
    loss_t = float(np.mean(np.maximum(post_c - post_t, 0)))
    loss_c = float(np.mean(np.maximum(post_t - post_c, 0)))

    lift = (post_t - post_c) / post_c
    tail = (1 - credible_mass) / 2
    lo, med, hi = np.quantile(lift, [tail, 0.5, 1 - tail])

    return BayesianResult(
        metric=metric,
        prob_treatment_better=prob_better,
        expected_loss_treatment=loss_t,
        expected_loss_control=loss_c,
        lift_median=float(med),
        lift_ci_low=float(lo),
        lift_ci_high=float(hi),
        posterior_mean_control=float(post_c.mean()),
        posterior_mean_treatment=float(post_t.mean()),
        n_samples=n_samples,
        prior=(prior_alpha, prior_beta),
    )
