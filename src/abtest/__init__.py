"""abtest - a small, opinionated A/B test analysis toolkit.

Typical use:

    from abtest import ExperimentConfig, ExperimentData, Experiment

    config = ExperimentConfig.from_yaml("configs/cookie_cats.yml")
    data = ExperimentData.from_file("data/raw/cookie_cats.csv", config)
    results = Experiment(data, config).run()
    print(results.summary())
"""

__version__ = "1.0.0"

from abtest.config import ExperimentConfig, MetricSpec
from abtest.data import ExperimentData, DataValidationError
from abtest.experiment import Experiment, ExperimentResults, MetricOutcome
from abtest.checks import CheckResult, run_all_checks

__all__ = [
    "__version__",
    "ExperimentConfig",
    "MetricSpec",
    "ExperimentData",
    "DataValidationError",
    "Experiment",
    "ExperimentResults",
    "MetricOutcome",
    "CheckResult",
    "run_all_checks",
]
