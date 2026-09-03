"""CUPED and winsorization."""
from __future__ import annotations

import numpy as np
import pytest

from abtest.exceptions import DataValidationError
from abtest.stats.variance_reduction import cuped_adjust, winsorize


class TestVarianceReduction:
    def test_cuped_reduces_variance_with_a_correlated_covariate(self):
        rng = np.random.default_rng(12)
        x_c, x_t = rng.normal(10, 3, 2_000), rng.normal(10, 3, 2_000)
        y_c = 2 * x_c + rng.normal(0, 1, 2_000)
        y_t = 2 * x_t + rng.normal(0, 1, 2_000)
        res = cuped_adjust(y_c, x_c, y_t, x_t)
        assert res.variance_reduction > 0.8
        assert res.effective_sample_gain > 5

    def test_cuped_estimates_the_true_effect_more_precisely(self):
        """CUPED must stay unbiased while shrinking the spread of the estimate.

        It is not expected to reproduce the raw difference run by run: part of
        what it removes is chance imbalance in the covariate between arms.
        What must hold is that it estimates the same quantity on average, with
        less run-to-run variability.
        """
        true_effect = 0.5
        raw_errors, adj_errors = [], []
        for seed in range(20):
            rng = np.random.default_rng(seed)
            x_c, x_t = rng.normal(5, 2, 1_000), rng.normal(5, 2, 1_000)
            y_c = x_c + rng.normal(0, 1, 1_000)
            y_t = x_t + rng.normal(0, 1, 1_000) + true_effect
            res = cuped_adjust(y_c, x_c, y_t, x_t)
            raw_errors.append(y_t.mean() - y_c.mean() - true_effect)
            adj_errors.append(
                res.adjusted_treatment.mean() - res.adjusted_control.mean() - true_effect
            )

        assert np.mean(adj_errors) == pytest.approx(0, abs=0.03)  # unbiased
        assert np.std(adj_errors) < np.std(raw_errors) / 2  # and more precise

    def test_uncorrelated_covariate_does_nothing_much(self):
        rng = np.random.default_rng(14)
        x_c, x_t = rng.normal(0, 1, 2_000), rng.normal(0, 1, 2_000)
        y_c, y_t = rng.normal(0, 1, 2_000), rng.normal(0, 1, 2_000)
        res = cuped_adjust(y_c, x_c, y_t, x_t)
        assert abs(res.variance_reduction) < 0.05

    def test_mismatched_arrays_are_rejected(self):
        with pytest.raises(DataValidationError):
            cuped_adjust(np.zeros(10), np.zeros(9), np.zeros(10), np.zeros(10))

    def test_winsorize_caps_at_the_quantile(self):
        values = np.append(np.arange(99, dtype=float), 10_000.0)
        capped, cap = winsorize(values, 0.99)
        assert capped.max() == cap
        assert cap < 200
        assert capped[:99].tolist() == values[:99].tolist()

    def test_winsorize_reuses_a_shared_cap(self):
        control = np.array([1.0, 2, 3, 400])
        treatment = np.array([1.0, 2, 3, 4])
        _, cap = winsorize(np.concatenate([control, treatment]), 0.9)
        capped_c, _ = winsorize(control, cap=cap)
        capped_t, _ = winsorize(treatment, cap=cap)
        assert capped_c.max() == cap
        assert capped_t.max() == 4  # untouched: already below the shared cap
