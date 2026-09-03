"""Calibration under the null: does the pipeline lie 5% of the time, as promised?

Unit tests check that each function computes what its formula says. They
cannot catch a pipeline that is individually correct and collectively wrong -
a mis-wired correction, a variance computed on the wrong subset, a filter
applied to one arm only. Running many A/A experiments does: with no effect
present, significance should appear at exactly the advertised rate.

This is the test that justifies the phrase "trustworthy result" in the
product description, so it asserts on the number the user is promised.

Every simulation is seeded, so failures are reproducible rather than flaky.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from abtest.config import MetricSpec
from abtest.data import ExperimentData
from abtest.experiment import Experiment
from abtest.stats.frequentist import proportion_test, welch_ttest
from abtest.stats.multiple_testing import adjust_pvalues
from tests.conftest import make_config, make_data

ALPHA = 0.05


def _binomial_bounds(n_sims: int, alpha: float = ALPHA, z: float = 3.5) -> tuple[float, float]:
    """Acceptable false-positive range for ``n_sims`` runs.

    Wide enough that a correctly calibrated pipeline effectively never fails,
    narrow enough that a broken one does: a test at 0.10 instead of 0.05 is
    far outside these bounds at every sample size used here.
    """
    se = np.sqrt(alpha * (1 - alpha) / n_sims)
    return max(0.0, alpha - z * se), alpha + z * se


class TestNullCalibration:
    def test_proportion_test_rejects_at_the_advertised_rate(self):
        n_sims, n_per_arm, rate = 4_000, 3_000, 0.2
        rng = np.random.default_rng(20240903)
        control = rng.binomial(n_per_arm, rate, n_sims)
        treatment = rng.binomial(n_per_arm, rate, n_sims)

        rejections = sum(
            proportion_test(int(c), n_per_arm, int(t), n_per_arm, alpha=ALPHA).significant
            for c, t in zip(control, treatment, strict=True)
        )
        rate_observed = rejections / n_sims
        low, high = _binomial_bounds(n_sims)
        assert low <= rate_observed <= high, f"false positive rate {rate_observed:.4f}"

    def test_welch_rejects_at_the_advertised_rate_with_unequal_arms(self):
        """Unequal sizes and variances are where a wrong dof shows up."""
        n_sims = 2_000
        rng = np.random.default_rng(11)
        rejections = 0
        for _ in range(n_sims):
            control = rng.normal(0, 1.0, 400)
            treatment = rng.normal(0, 3.0, 90)
            rejections += welch_ttest(control, treatment, alpha=ALPHA).significant

        rate_observed = rejections / n_sims
        low, high = _binomial_bounds(n_sims)
        assert low <= rate_observed <= high, f"false positive rate {rate_observed:.4f}"

    def test_pvalues_are_uniform_under_the_null(self):
        n_sims, n_per_arm, rate = 2_000, 4_000, 0.15
        rng = np.random.default_rng(7)
        p_values = np.array(
            [
                proportion_test(
                    int(rng.binomial(n_per_arm, rate)),
                    n_per_arm,
                    int(rng.binomial(n_per_arm, rate)),
                    n_per_arm,
                ).p_value
                for _ in range(n_sims)
            ]
        )
        # Discreteness of a binomial makes the fit imperfect; a p-value below
        # 0.001 on the KS test would mean a real distortion, not granularity.
        assert stats.kstest(p_values, "uniform").pvalue > 0.001

    def test_benjamini_hochberg_controls_the_family_error_rate(self):
        """With five null metrics per experiment, at least one 'discovery'
        should still appear in about 5% of experiments after correction."""
        n_sims, n_metrics, n_per_arm, rate = 2_000, 5, 2_000, 0.25
        rng = np.random.default_rng(99)
        families_with_a_discovery = 0
        for _ in range(n_sims):
            p_values = [
                proportion_test(
                    int(rng.binomial(n_per_arm, rate)),
                    n_per_arm,
                    int(rng.binomial(n_per_arm, rate)),
                    n_per_arm,
                ).p_value
                for _ in range(n_metrics)
            ]
            adjusted = adjust_pvalues(p_values, method="bh", alpha=ALPHA)
            families_with_a_discovery += bool(adjusted["significant"].any())

        corrected_rate = families_with_a_discovery / n_sims
        uncorrected_expectation = 1 - (1 - ALPHA) ** n_metrics  # ~0.226
        assert corrected_rate < uncorrected_expectation / 2
        assert corrected_rate <= _binomial_bounds(n_sims)[1]


@pytest.mark.slow
class TestPipelineCalibration:
    def test_full_pipeline_does_not_manufacture_winners(self):
        """End to end, through validation, checks, tests and correction."""
        n_sims = 200
        config = make_config(
            metrics=[
                MetricSpec("converted", "converted", "binary", primary=True),
                MetricSpec("revenue", "revenue", "continuous", primary=True),
            ]
        )
        ships = 0
        for seed in range(n_sims):
            data = ExperimentData.from_dataframe(make_data(n=3_000, lift=0.0, seed=seed), config)
            results = Experiment(data, config).run()
            ships += results.decision()["recommendation"] == "ship"

        rate_observed = ships / n_sims
        assert rate_observed <= _binomial_bounds(n_sims)[1], (
            f"pipeline recommended shipping {ships}/{n_sims} A/A experiments"
        )

    def test_pipeline_finds_a_real_effect_it_is_powered_for(self):
        """The mirror of the test above: calibration is worthless without power."""
        n_sims = 60
        config = make_config(metrics=[MetricSpec("converted", "converted", "binary", primary=True)])
        detected = 0
        for seed in range(n_sims):
            data = ExperimentData.from_dataframe(
                make_data(n=30_000, lift=0.15, seed=1_000 + seed), config
            )
            results = Experiment(data, config).run()
            detected += results.outcome("converted").verdict == "win"

        assert detected / n_sims > 0.80
