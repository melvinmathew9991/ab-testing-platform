"""Bootstrap intervals and permutation tests."""
from __future__ import annotations

import numpy as np
import pytest

from abtest.stats.bootstrap import bootstrap_ci, permutation_test


class TestResampling:
    def test_bootstrap_ci_recovers_a_known_difference(self):
        rng = np.random.default_rng(0)
        control = rng.normal(10, 2, 2_000)
        treatment = rng.normal(11, 2, 2_000)
        res = bootstrap_ci(control, treatment, n_bootstrap=2_000, seed=1)
        assert res.ci_low < 1.0 < res.ci_high
        assert res.significant

    def test_bootstrap_agrees_with_the_t_interval_for_normal_data(self):
        rng = np.random.default_rng(4)
        control = rng.normal(0, 1, 3_000)
        treatment = rng.normal(0.2, 1, 3_000)
        boot = bootstrap_ci(control, treatment, n_bootstrap=3_000, seed=2)
        from abtest.stats.frequentist import welch_ttest

        t = welch_ttest(control, treatment)
        assert boot.ci_low == pytest.approx(t.ci_low, abs=0.03)
        assert boot.ci_high == pytest.approx(t.ci_high, abs=0.03)

    def test_permutation_finds_no_effect_when_there_is_none(self):
        rng = np.random.default_rng(5)
        pooled = rng.normal(0, 1, 4_000)
        res = permutation_test(pooled[:2_000], pooled[2_000:], n_permutations=1_000, seed=3)
        assert res.p_value > 0.05
        assert not res.significant

    def test_permutation_detects_a_large_effect(self):
        rng = np.random.default_rng(6)
        control = rng.normal(0, 1, 1_000)
        treatment = rng.normal(0.5, 1, 1_000)
        res = permutation_test(control, treatment, n_permutations=1_000, seed=4)
        assert res.p_value < 0.01

    def test_pvalue_never_reaches_zero(self):
        control = np.zeros(200)
        treatment = np.ones(200)
        res = permutation_test(control, treatment, n_permutations=500, seed=5)
        assert res.p_value == pytest.approx(1 / 501)

    def test_null_distribution_is_centred_on_zero(self):
        rng = np.random.default_rng(7)
        control, treatment = rng.normal(3, 1, 600), rng.normal(3, 1, 600)
        res = permutation_test(control, treatment, n_permutations=1_000, seed=6)
        assert abs(np.mean(res.null_distribution)) < 0.05

    def test_a_statistic_raising_typeerror_is_not_silently_downgraded(self):
        """Regression: TypeError from inside a user statistic used to be read
        as "no axis support", silently switching to the slow path."""
        from abtest.stats.bootstrap import _supports_axis

        calls = {"n": 0}

        def picky(x, axis=None):
            calls["n"] += 1
            if calls["n"] > 1 and x.shape[0] > 2:
                raise TypeError("this is a bug in the statistic, not a signature issue")
            return np.mean(x, axis=axis)

        assert _supports_axis(picky) is True

    def test_non_vectorised_statistic_still_works(self):
        def trimmed(x):
            return float(np.mean(np.sort(x)[5:-5]))

        rng = np.random.default_rng(8)
        res = bootstrap_ci(
            rng.normal(0, 1, 200), rng.normal(1, 1, 200),
            statistic=trimmed, n_bootstrap=200, seed=7,
        )
        assert res.ci_low < 1.0 < res.ci_high

    def test_results_are_reproducible(self):
        rng = np.random.default_rng(9)
        a, b = rng.normal(0, 1, 300), rng.normal(0.1, 1, 300)
        first = permutation_test(a, b, n_permutations=300, seed=11).p_value
        second = permutation_test(a, b, n_permutations=300, seed=11).p_value
        assert first == second
