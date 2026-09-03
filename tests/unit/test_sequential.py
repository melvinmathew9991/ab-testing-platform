"""Alpha spending and interim analyses."""
from __future__ import annotations

import pytest

from abtest.exceptions import ConfigurationError, InsufficientDataError
from abtest.stats.sequential import obrien_fleming_boundaries, sequential_analysis


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
        with pytest.raises(InsufficientDataError):
            sequential_analysis([])
