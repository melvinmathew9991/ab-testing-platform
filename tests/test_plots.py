"""Smoke tests for the figures: they must render, save and stay non-empty.

Chart correctness is a visual property, but a chart that raises or writes a
zero-byte file is a bug a test can catch.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from abtest import plots
from abtest.stats.bayesian import beta_binomial_test
from abtest.stats.bootstrap import permutation_test
from abtest.stats.power import power_curve
from abtest.stats.sequential import sequential_analysis


@pytest.fixture
def summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric": "retention_1", "role": "primary", "control": 0.448,
             "treatment": 0.442, "relative_diff": -0.0132, "rel_ci_low": -0.028,
             "rel_ci_high": 0.0013, "p_adjusted": 0.112, "verdict": "flat"},
            {"metric": "retention_7", "role": "primary", "control": 0.190,
             "treatment": 0.182, "relative_diff": -0.0431, "rel_ci_low": -0.070,
             "rel_ci_high": -0.016, "p_adjusted": 0.005, "verdict": "regression"},
        ]
    )


def _written(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 1_000


def test_lift_forest(tmp_path, summary):
    path = plots.lift_forest(summary, str(tmp_path / "forest.png"))
    assert _written(path)


def test_metric_bars(tmp_path, summary):
    assert _written(plots.metric_bars(summary, str(tmp_path / "bars.png")))


def test_power_curve_plot(tmp_path):
    curve = power_curve(0.19, np.linspace(0, 0.1, 30), n_control=45_000)
    path = plots.power_curve_plot(
        curve, observed_effect=-0.043, mde=0.039, path=str(tmp_path / "power.png")
    )
    assert _written(path)


def test_posterior_plot(tmp_path):
    bayes = beta_binomial_test(8_502, 44_700, 8_279, 45_489, n_samples=5_000)
    assert _written(plots.posterior_plot(bayes, str(tmp_path / "post.png")))


def test_null_distribution_plot(tmp_path):
    rng = np.random.default_rng(0)
    perm = permutation_test(rng.normal(0, 1, 300), rng.normal(0.1, 1, 300),
                            n_permutations=200, seed=1)
    assert _written(plots.null_distribution_plot(perm, str(tmp_path / "null.png")))


def test_sequential_plot(tmp_path):
    looks = sequential_analysis(
        [
            {"label": f"look {i}", "n_control": 1_000 * i, "n_treatment": 1_000 * i,
             "conversions_control": 200 * i, "conversions_treatment": 190 * i}
            for i in range(1, 5)
        ]
    )
    assert _written(plots.sequential_plot(looks, str(tmp_path / "seq.png")))


def test_distribution_plot(tmp_path):
    rng = np.random.default_rng(2)
    path = plots.distribution_plot(
        rng.exponential(50, 2_000), rng.exponential(52, 2_000), str(tmp_path / "dist.png")
    )
    assert _written(path)


def test_segment_forest(tmp_path):
    segments = pd.DataFrame(
        [
            {"dimension": "country", "segment": s, "metric": "cr", "control": 0.2,
             "relative_diff": d, "ci_low": -0.01, "ci_high": 0.02, "significant": False}
            for s, d in [("US", 0.01), ("FR", -0.02), ("JP", 0.03)]
        ]
    )
    assert _written(plots.segment_forest(segments, "cr", str(tmp_path / "seg.png")))


def test_segment_forest_returns_none_when_metric_absent(tmp_path):
    empty = pd.DataFrame(columns=["dimension", "segment", "metric", "control",
                                  "relative_diff", "ci_low", "ci_high", "significant"])
    assert plots.segment_forest(empty, "missing", str(tmp_path / "x.png")) is None
