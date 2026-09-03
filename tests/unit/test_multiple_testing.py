"""Bonferroni and Benjamini-Hochberg corrections."""

from __future__ import annotations

import pytest

from abtest.exceptions import ConfigurationError, DataValidationError
from abtest.stats.multiple_testing import adjust_pvalues


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
        with pytest.raises((ConfigurationError, DataValidationError)):
            adjust_pvalues([0.5, 1.4])
        with pytest.raises((ConfigurationError, DataValidationError)):
            adjust_pvalues([0.5], method="magic")
