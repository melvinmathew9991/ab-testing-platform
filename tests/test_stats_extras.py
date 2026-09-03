"""Power, resampling, Bayesian, corrections, variance reduction, sequential."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from abtest.stats.bayesian import beta_binomial_test
from abtest.stats.bootstrap import bootstrap_ci, permutation_test
from abtest.stats.multiple import adjust_pvalues
from abtest.stats.power import (
    mde_for_sample,
    power_curve,
    power_for_proportions,
    sample_size_means,
    sample_size_proportions,
)
from abtest.stats.sequential import obrien_fleming_boundaries, sequential_analysis
from abtest.stats.variance import cuped_adjust, winsorize


class TestPower:
    def test_sample_size_matches_textbook_formula(self):
        res = sample_size_proportions(0.20, mde_relative=0.10)
        p0, p1 = 0.20, 0.22
        z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
        expected = np.ceil(z**2 * (p0 * (1 - p0) + p1 * (1 - p1)) / (p1 - p0) ** 2)
        assert res["n_control"] == expected

    def test_smaller_effects_need_more_traffic(self):
        big = sample_size_proportions(0.2, mde_relative=0.10)["n_total"]
        small = sample_size_proportions(0.2, mde_relative=0.02)["n_total"]
        assert small > big * 20  # sample size scales with 1/effect^2

    def test_mde_and_power_are_inverse_of_each_other(self):
        mde = mde_for_sample(0.19, 45_000, 45_000)["mde_absolute"]
        achieved = power_for_proportions(0.19, mde, 45_000, 45_000)
        assert achieved == pytest.approx(0.80, abs=0.01)

    def test_sample_size_round_trips_to_target_power(self):
        res = sample_size_proportions(0.19, mde_relative=0.05)
        achieved = power_for_proportions(
            0.19, res["mde_absolute"], res["n_control"], res["n_treatment"]
        )
        assert achieved == pytest.approx(0.80, abs=0.01)

    def test_power_curve_is_monotonic(self):
        curve = power_curve(0.2, np.linspace(0, 0.2, 25), n_control=5_000)
        assert curve["power"].is_monotonic_increasing
        assert curve["power"].iloc[0] == pytest.approx(0.05, abs=0.005)  # alpha at zero effect

    def test_continuous_sample_size(self):
        res = sample_size_means(std=2.0, mde_absolute=0.1)
        z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
        assert res["n_control"] == np.ceil(z**2 * 4.0 * 2 / 0.01)

    def test_rejects_out_of_range_inputs(self):
        with pytest.raises(ValueError):
            sample_size_proportions(1.4, mde_relative=0.1)
        with pytest.raises(ValueError):
            sample_size_proportions(0.2, mde_absolute=0.9)


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


class TestBayesian:
    def test_clear_winner_gets_high_probability(self):
        res = beta_binomial_test(1_000, 10_000, 1_400, 10_000, n_samples=40_000)
        assert res.prob_treatment_better > 0.99
        assert res.decision == "ship treatment"
        assert res.expected_loss_treatment < res.expected_loss_control

    def test_identical_data_is_a_coin_flip(self):
        res = beta_binomial_test(500, 5_000, 500, 5_000, n_samples=40_000)
        assert res.prob_treatment_better == pytest.approx(0.5, abs=0.02)
        assert res.decision == "inconclusive"

    def test_credible_interval_brackets_the_median(self):
        res = beta_binomial_test(900, 10_000, 950, 10_000, n_samples=40_000)
        assert res.lift_ci_low < res.lift_median < res.lift_ci_high

    def test_agrees_with_the_frequentist_direction(self):
        from abtest.stats.frequentist import proportion_test

        freq = proportion_test(8_502, 44_700, 8_279, 45_489)
        bayes = beta_binomial_test(8_502, 44_700, 8_279, 45_489, n_samples=60_000)
        # A significant drop should leave very little posterior mass above zero.
        assert freq.absolute_diff < 0 and freq.significant
        assert bayes.prob_treatment_better < 0.01


class TestMultipleTesting:
    def test_bonferroni_multiplies_by_family_size(self):
        out = adjust_pvalues([0.01, 0.02, 0.03], method="bonferroni")
        assert list(out["p_adjusted"]) == pytest.approx([0.03, 0.06, 0.09])

    def test_bh_is_less_conservative_than_bonferroni(self):
        p = [0.001, 0.01, 0.02, 0.04, 0.2]
        bh = adjust_pvalues(p, method="bh")["p_adjusted"]
        bonf = adjust_pvalues(p, method="bonferroni")["p_adjusted"]
        assert (bh <= bonf + 1e-12).all()
        assert bh.iloc[1] < bonf.iloc[1]

    def test_bh_is_monotonic_in_the_original_ordering(self):
        p = [0.04, 0.001, 0.2, 0.01]
        out = adjust_pvalues(p, method="bh").sort_values("p_value")
        assert out["p_adjusted"].is_monotonic_increasing

    def test_adjusted_values_never_exceed_one(self):
        out = adjust_pvalues([0.5, 0.6, 0.9], method="bonferroni")
        assert (out["p_adjusted"] <= 1.0).all()

    def test_none_passes_through(self):
        out = adjust_pvalues([0.01, 0.2], method="none")
        assert list(out["p_adjusted"]) == [0.01, 0.2]

    def test_rejects_invalid_input(self):
        with pytest.raises(ValueError):
            adjust_pvalues([0.5, 1.4])
        with pytest.raises(ValueError):
            adjust_pvalues([0.5], method="magic")


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
        with pytest.raises(ValueError):
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


class TestSequential:
    def test_boundaries_are_stricter_early(self):
        b = obrien_fleming_boundaries(4)
        assert b["z_critical"].is_monotonic_decreasing
        assert b["z_critical"].iloc[-1] == pytest.approx(1.96, abs=0.01)
        assert b["z_critical"].iloc[0] > 3.5

    def test_total_alpha_spent_equals_alpha(self):
        b = obrien_fleming_boundaries(5, alpha=0.05)
        assert b["alpha_spent_cumulative"].iloc[-1] == pytest.approx(0.05, rel=1e-9)
        assert b["alpha_spent_at_look"].sum() == pytest.approx(0.05, rel=1e-9)

    def test_naive_testing_stops_earlier_than_sequential(self):
        looks = [
            {"label": "d1", "n_control": 500, "conversions_control": 100,
             "n_treatment": 500, "conversions_treatment": 130},
            {"label": "d2", "n_control": 5_000, "conversions_control": 1_000,
             "n_treatment": 5_000, "conversions_treatment": 1_090},
        ]
        out = sequential_analysis(looks, planned_n_total=10_000)
        assert out.loc[0, "stop_naive"]
        assert not out.loc[0, "stop_sequential"]  # too early to call
        assert out["information_fraction"].iloc[-1] == pytest.approx(1.0)

    def test_requires_looks(self):
        with pytest.raises(ValueError):
            sequential_analysis([])
