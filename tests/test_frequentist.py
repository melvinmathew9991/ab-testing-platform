"""The frequentist tests are checked against scipy and against closed-form
identities, not against previously recorded output - a snapshot test would
happily lock in a bug."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from abtest.stats.frequentist import proportion_test, welch_ttest


class TestWelchTTest:
    def test_matches_scipy(self):
        rng = np.random.default_rng(0)
        control = rng.normal(10, 2, 500)
        treatment = rng.normal(10.4, 3.5, 640)

        ours = welch_ttest(control, treatment)
        theirs = stats.ttest_ind(treatment, control, equal_var=False)

        assert ours.statistic == pytest.approx(theirs.statistic, rel=1e-12)
        assert ours.p_value == pytest.approx(theirs.pvalue, rel=1e-12)
        assert ours.dof == pytest.approx(theirs.df, rel=1e-12)

    def test_degrees_of_freedom_pair_variance_with_own_sample_size(self):
        """Regression guard: swapping the variance/size pairing changes dof.

        With very different group sizes and variances, the Welch-Satterthwaite
        value is far from the naive n0 + n1 - 2, and a mismatched pairing
        produces a different number - this pins the correct one.
        """
        rng = np.random.default_rng(1)
        control = rng.normal(0, 1.0, 2000)
        treatment = rng.normal(0, 6.0, 120)

        result = welch_ttest(control, treatment)
        expected = stats.ttest_ind(treatment, control, equal_var=False).df

        assert result.dof == pytest.approx(expected, rel=1e-12)
        assert result.dof < 200  # dominated by the small, noisy arm

    def test_confidence_interval_brackets_the_difference(self):
        rng = np.random.default_rng(2)
        control = rng.normal(5, 1, 400)
        treatment = rng.normal(6, 1, 400)
        r = welch_ttest(control, treatment)

        assert r.ci_low < r.absolute_diff < r.ci_high
        assert r.significant
        assert r.relative_diff == pytest.approx(r.absolute_diff / r.mean_control)

    def test_identical_samples_are_not_significant(self):
        values = np.arange(100, dtype=float)
        r = welch_ttest(values, values.copy())
        assert r.p_value == pytest.approx(1.0)
        assert not r.significant

    def test_zero_variance_does_not_explode(self):
        r = welch_ttest(np.ones(50), np.ones(50))
        assert r.p_value == 1.0
        assert not r.significant

    def test_requires_two_observations(self):
        with pytest.raises(ValueError):
            welch_ttest(np.array([1.0]), np.array([1.0, 2.0]))

    def test_one_sided_alternatives(self):
        rng = np.random.default_rng(3)
        control = rng.normal(0, 1, 300)
        treatment = rng.normal(0.4, 1, 300)
        two = welch_ttest(control, treatment, alternative="two-sided")
        larger = welch_ttest(control, treatment, alternative="larger")
        assert larger.p_value == pytest.approx(two.p_value / 2, rel=1e-9)


class TestProportionTest:
    def test_matches_manual_z_calculation(self):
        c_conv, n0, t_conv, n1 = 8_502, 44_700, 8_279, 45_489
        r = proportion_test(c_conv, n0, t_conv, n1)

        p0, p1 = c_conv / n0, t_conv / n1
        pooled = (c_conv + t_conv) / (n0 + n1)
        se = np.sqrt(pooled * (1 - pooled) * (1 / n0 + 1 / n1))
        z = (p1 - p0) / se

        assert r.statistic == pytest.approx(z, rel=1e-12)
        assert r.p_value == pytest.approx(2 * stats.norm.sf(abs(z)), rel=1e-12)

    def test_ci_uses_unpooled_error_and_contains_estimate(self):
        r = proportion_test(200, 1000, 260, 1000)
        p0, p1 = 0.2, 0.26
        se = np.sqrt(p0 * (1 - p0) / 1000 + p1 * (1 - p1) / 1000)
        assert r.standard_error == pytest.approx(se, rel=1e-12)
        assert r.ci_low < r.absolute_diff < r.ci_high

    def test_no_difference_gives_p_one(self):
        r = proportion_test(100, 1000, 100, 1000)
        assert r.p_value == pytest.approx(1.0)
        assert r.absolute_diff == 0

    def test_larger_sample_shrinks_the_interval(self):
        small = proportion_test(100, 1_000, 110, 1_000)
        large = proportion_test(10_000, 100_000, 11_000, 100_000)
        assert (large.ci_high - large.ci_low) < (small.ci_high - small.ci_low)

    def test_rejects_impossible_inputs(self):
        with pytest.raises(ValueError):
            proportion_test(10, 5, 3, 100)
        with pytest.raises(ValueError):
            proportion_test(1, 0, 1, 10)

    def test_mde_scales_with_standard_error(self):
        r = proportion_test(200, 1000, 210, 1000)
        z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
        assert r.mde_absolute == pytest.approx(z * r.standard_error, rel=1e-12)
