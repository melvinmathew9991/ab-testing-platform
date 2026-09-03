"""Config, data contract, checks and the end-to-end experiment pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from abtest.checks import normal_approximation, outlier_influence, sample_ratio_mismatch
from abtest.config import ExperimentConfig, MetricSpec
from abtest.data import DataValidationError, ExperimentData
from abtest.experiment import Experiment
from abtest.report import build_html_report, build_markdown_report


def make_config(**overrides) -> ExperimentConfig:
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


class TestConfig:
    def test_yaml_round_trip(self, tmp_path):
        path = tmp_path / "exp.yml"
        path.write_text(
            "name: demo\nunit_col: uid\nvariant_col: v\ncontrol: a\ntreatment: b\n"
            "expected_split: [0.5, 0.5]\n"
            "metrics:\n  - name: cr\n    column: cr\n    type: binary\n    primary: true\n",
            encoding="utf-8",
        )
        cfg = ExperimentConfig.from_yaml(path)
        assert cfg.variants == ("a", "b")
        assert cfg.primary_metrics[0].name == "cr"
        assert isinstance(cfg.metrics[0], MetricSpec)

    def test_rejects_bad_parameters(self):
        with pytest.raises(ValueError):
            make_config(alpha=1.5)
        with pytest.raises(ValueError):
            make_config(expected_split=(0.6, 0.6))
        with pytest.raises(ValueError):
            make_config(metrics=[])

    def test_rejects_bad_metric_spec(self):
        with pytest.raises(ValueError):
            MetricSpec("m", "m", type="ordinal")
        with pytest.raises(ValueError):
            MetricSpec("m", "m", type="binary", winsorize_quantile=0.99)


class TestDataContract:
    def test_missing_column_is_fatal(self):
        df = make_data().drop(columns=["revenue"])
        with pytest.raises(DataValidationError, match="Missing required columns"):
            ExperimentData.from_dataframe(df, make_config())

    def test_missing_variant_is_fatal(self):
        df = make_data()
        df = df[df["variant"] == "A"]
        with pytest.raises(DataValidationError):
            ExperimentData.from_dataframe(df, make_config())

    def test_non_binary_values_in_binary_metric_are_fatal(self):
        df = make_data()
        df.loc[0, "converted"] = 7
        with pytest.raises(DataValidationError, match="non-binary"):
            ExperimentData.from_dataframe(df, make_config())

    def test_duplicate_units_are_dropped_and_reported(self):
        df = pd.concat([make_data(1_000), make_data(1_000).head(50)])
        data = ExperimentData.from_dataframe(df, make_config())
        assert len(data) == 1_000
        assert any("duplicated" in issue for issue in data.issues)

    def test_extra_variants_are_dropped_and_reported(self):
        df = make_data(2_000)
        df.loc[df.index[:100], "variant"] = "C"
        data = ExperimentData.from_dataframe(df, make_config())
        assert set(data.df["variant"]) == {"A", "B"}
        assert any("outside the test" in issue for issue in data.issues)

    def test_summary_covers_every_metric_and_variant(self):
        data = ExperimentData.from_dataframe(make_data(), make_config())
        summary = data.summary()
        assert len(summary) == 4
        assert set(summary["variant"]) == {"A", "B"}


class TestChecks:
    def test_srm_passes_on_a_fair_split(self):
        assert sample_ratio_mismatch(50_000, 50_100).passed

    def test_srm_fails_on_a_broken_split(self):
        result = sample_ratio_mismatch(50_000, 45_000)
        assert not result.passed
        assert result.severity == "critical"
        assert result.status == "FAIL"

    def test_srm_respects_an_uneven_planned_split(self):
        assert sample_ratio_mismatch(9_000, 1_000, expected_split=(0.9, 0.1)).passed
        assert not sample_ratio_mismatch(5_000, 5_000, expected_split=(0.9, 0.1)).passed

    def test_outlier_influence_flags_a_dominant_tail(self):
        values = np.concatenate([np.ones(9_990), np.full(10, 1e6)])
        assert not outlier_influence(values, "revenue").passed

    def test_outlier_influence_passes_on_a_tame_metric(self):
        assert outlier_influence(np.random.default_rng(0).normal(10, 1, 10_000), "x").passed

    def test_normal_approximation_flags_sparse_cells(self):
        assert not normal_approximation(3, 1_000, "rare_event").passed
        assert normal_approximation(300, 1_000, "common_event").passed


class TestExperiment:
    def test_detects_a_real_effect(self):
        data = ExperimentData.from_dataframe(
            make_data(n=40_000, lift=0.25, seed=3), make_config()
        )
        results = Experiment(data).run()
        outcome = results.outcome("converted")
        assert outcome.verdict == "win"
        assert outcome.test.relative_diff > 0
        assert results.decision()["recommendation"] == "ship"

    def test_reports_no_effect_when_there_is_none(self):
        data = ExperimentData.from_dataframe(make_data(n=20_000, lift=0.0, seed=4), make_config())
        results = Experiment(data).run()
        assert results.outcome("converted").verdict == "flat"
        assert "do not ship" in results.decision()["recommendation"]

    def test_a_regression_blocks_the_launch(self):
        data = ExperimentData.from_dataframe(
            make_data(n=60_000, lift=-0.3, seed=5), make_config()
        )
        results = Experiment(data).run()
        assert results.outcome("converted").verdict == "regression"
        assert results.decision()["recommendation"] == "do not ship"

    def test_srm_failure_invalidates_the_whole_result(self):
        data = ExperimentData.from_dataframe(
            make_data(n=20_000, lift=0.5, seed=6, variant_ratio=0.65), make_config()
        )
        results = Experiment(data).run()
        assert results.blocking_failures
        assert results.decision()["recommendation"] == "do not use this result"

    def test_multiple_testing_correction_is_applied(self):
        data = ExperimentData.from_dataframe(make_data(n=30_000, lift=0.1, seed=7), make_config())
        results = Experiment(data).run()
        for outcome in results.outcomes:
            assert outcome.p_adjusted >= outcome.test.p_value - 1e-12

    def test_winsorizing_uses_one_shared_cap(self):
        df = make_data(n=10_000, seed=8)
        df.loc[df.index[:5], "revenue"] = 1e7  # whales, all in one place
        config = make_config(
            metrics=[
                MetricSpec("converted", "converted", "binary", primary=True),
                MetricSpec("revenue", "revenue", "continuous", winsorize_quantile=0.99),
            ]
        )
        data = ExperimentData.from_dataframe(df, config)
        results = Experiment(data).run()
        outcome = results.outcome("revenue")
        assert outcome.winsor_cap is not None
        assert outcome.test.mean_control < 1e6

    def test_resampling_attaches_to_continuous_metrics(self):
        config = make_config(n_bootstrap=300, n_permutations=300)
        data = ExperimentData.from_dataframe(make_data(n=3_000, seed=9), config)
        results = Experiment(data, config).run(resample=True)
        revenue = results.outcome("revenue")
        assert revenue.bootstrap is not None and revenue.permutation is not None
        assert results.outcome("converted").bootstrap is None  # binary uses the z-test

    def test_segments_are_corrected_across_slices(self):
        data = ExperimentData.from_dataframe(make_data(n=30_000, lift=0.1, seed=10), make_config())
        results = Experiment(data).run(segment_by=["country"])
        assert results.segments is not None
        assert set(results.segments["dimension"]) == {"country"}
        assert (results.segments["p_adjusted"] >= results.segments["p_value"] - 1e-12).all()
        assert any(c.name.startswith("segment_balance") for c in results.checks)

    def test_sensitivity_reports_what_was_detectable(self):
        data = ExperimentData.from_dataframe(make_data(n=20_000, seed=11), make_config())
        experiment = Experiment(data)
        experiment.run()
        sensitivity = experiment.sensitivity("converted")
        assert 0 < sensitivity["mde_relative"] < 1

    def test_results_serialise(self):
        data = ExperimentData.from_dataframe(make_data(n=5_000, seed=12), make_config())
        payload = Experiment(data).run().to_dict()
        assert payload["experiment"] == "test experiment"
        assert len(payload["metrics"]) == 2
        assert "recommendation" in payload["decision"]


class TestReports:
    def test_html_report_is_self_contained(self, tmp_path):
        data = ExperimentData.from_dataframe(make_data(n=5_000, seed=13), make_config())
        results = Experiment(data).run()
        path = build_html_report(results, output_path=str(tmp_path / "r.html"))
        html = open(path, encoding="utf-8").read()
        assert "<!doctype html>" in html
        assert "Recommendation" in html
        assert "converted" in html
        assert "http://" not in html  # no external assets to break

    def test_markdown_report_lists_every_metric(self):
        data = ExperimentData.from_dataframe(make_data(n=5_000, seed=14), make_config())
        results = Experiment(data).run()
        md = build_markdown_report(results)
        assert "| converted |" in md
        assert "| revenue |" in md
        assert "Recommendation" in md
