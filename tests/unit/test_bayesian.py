"""Beta-Binomial posterior comparisons."""
from __future__ import annotations

import pytest

from abtest.stats.bayesian import beta_binomial_test


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
