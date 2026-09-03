"""Statistical engine: frequentist tests, resampling, power, Bayesian and
variance-reduction utilities. Each module is import-light and side-effect free."""

from abtest.stats.frequentist import TestResult, proportion_test, welch_ttest
from abtest.stats.bootstrap import bootstrap_ci, permutation_test
from abtest.stats.power import (
    mde_for_sample,
    power_curve,
    power_for_proportions,
    sample_size_proportions,
)
from abtest.stats.bayesian import BayesianResult, beta_binomial_test
from abtest.stats.multiple_testing import adjust_pvalues
from abtest.stats.variance_reduction import cuped_adjust, winsorize
from abtest.stats.sequential import obrien_fleming_boundaries, sequential_analysis

__all__ = [
    "TestResult",
    "proportion_test",
    "welch_ttest",
    "bootstrap_ci",
    "permutation_test",
    "sample_size_proportions",
    "power_for_proportions",
    "power_curve",
    "mde_for_sample",
    "BayesianResult",
    "beta_binomial_test",
    "adjust_pvalues",
    "cuped_adjust",
    "winsorize",
    "obrien_fleming_boundaries",
    "sequential_analysis",
]
