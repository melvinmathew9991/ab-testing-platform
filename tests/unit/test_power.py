"""Sample size, MDE and power curves, checked against closed-form results."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from abtest.exceptions import ConfigurationError
from abtest.stats.power import (
    mde_for_sample,
    power_curve,
    power_for_proportions,
    sample_size_means,
    sample_size_proportions,
)


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

    def test_power_curve_handles_effects_beyond_the_valid_range(self):
        """A treatment rate outside (0, 1) is undefined, not a number."""
        curve = power_curve(0.9, np.linspace(0, 0.5, 11), n_control=5_000)
        assert curve["power"].notna().any()
        assert curve.loc[curve["effect_absolute"] + 0.9 >= 1, "power"].isna().all()

    def test_vectorised_power_matches_scalar_calls(self):
        effects = np.linspace(0.001, 0.05, 15)
        vectorised = power_for_proportions(0.2, effects, 10_000, 10_000)
        scalar = [power_for_proportions(0.2, float(e), 10_000, 10_000) for e in effects]
        assert np.allclose(vectorised, scalar)

    def test_power_curve_is_monotonic(self):
        curve = power_curve(0.2, np.linspace(0, 0.2, 25), n_control=5_000)
        assert curve["power"].is_monotonic_increasing
        assert curve["power"].iloc[0] == pytest.approx(0.05, abs=0.005)  # alpha at zero effect

    def test_continuous_sample_size(self):
        res = sample_size_means(std=2.0, mde_absolute=0.1)
        z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
        assert res["n_control"] == np.ceil(z**2 * 4.0 * 2 / 0.01)

    def test_rejects_out_of_range_inputs(self):
        with pytest.raises(ConfigurationError):
            sample_size_proportions(1.4, mde_relative=0.1)
        with pytest.raises(ConfigurationError):
            sample_size_proportions(0.2, mde_absolute=0.9)
