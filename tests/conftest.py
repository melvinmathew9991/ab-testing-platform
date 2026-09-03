"""Shared test fixtures.

The synthetic experiment factory lives here so unit, integration and
calibration tests all generate data the same way - a calibration result is
only meaningful if the data generating process is the one everything else
is tested against.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from abtest.config import ExperimentConfig, MetricSpec


def make_config(**overrides) -> ExperimentConfig:
    """A two-metric experiment definition, overridable field by field."""
    base = dict(
        name="test experiment",
        unit_col="user_id",
        variant_col="variant",
        control="A",
        treatment="B",
        metrics=[
            MetricSpec("converted", "converted", "binary", primary=True),
            MetricSpec("revenue", "revenue", "continuous", guardrail=True),
        ],
        seed=1,
    )
    base.update(overrides)
    return ExperimentConfig(**base)


def make_data(
    n: int = 4_000,
    lift: float = 0.0,
    base_rate: float = 0.20,
    seed: int = 0,
    variant_ratio: float = 0.5,
) -> pd.DataFrame:
    """Unit-level data for a synthetic experiment.

    ``lift`` is the relative effect applied to the treatment arm; ``0.0``
    makes it an A/A test, which is what the calibration tests need.
    """
    rng = np.random.default_rng(seed)
    variant = np.where(rng.random(n) < variant_ratio, "A", "B")
    rate = np.where(variant == "A", base_rate, base_rate * (1 + lift))
    converted = (rng.random(n) < rate).astype(int)
    revenue = converted * rng.gamma(2, 20, n)
    return pd.DataFrame(
        {
            "user_id": np.arange(n),
            "variant": variant,
            "converted": converted,
            "revenue": revenue,
            "country": rng.choice(["US", "FR", "JP"], n),
        }
    )


@pytest.fixture
def config() -> ExperimentConfig:
    return make_config()


@pytest.fixture
def experiment_data() -> pd.DataFrame:
    return make_data()
