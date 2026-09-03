"""The orchestrator: turn configured data into a decision.

``Experiment.run()`` executes the same sequence every time - validate, check,
test, correct, decide - so that no experiment gets a bespoke analysis that
happens to favour the desired outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from abtest.checks import CheckResult, checks_to_frame, run_all_checks, segment_balance
from abtest.config import ExperimentConfig, MetricSpec
from abtest.data import ExperimentData
from abtest.exceptions import ConfigurationError, UnsupportedMetricError
from abtest.log import get_logger, log_duration
from abtest.stats.bayesian import BayesianResult, beta_binomial_test
from abtest.stats.bootstrap import (
    BootstrapResult,
    PermutationResult,
    bootstrap_ci,
    permutation_test,
)
from abtest.stats.frequentist import TestResult, proportion_test, welch_ttest
from abtest.stats.multiple_testing import adjust_pvalues
from abtest.stats.power import mde_for_sample
from abtest.stats.variance_reduction import CupedResult, cuped_adjust, winsorize

logger = get_logger(__name__)


@dataclass
class MetricOutcome:
    """Everything computed for one metric."""

    spec: MetricSpec
    test: TestResult
    bayesian: BayesianResult | None = None
    bootstrap: BootstrapResult | None = None
    permutation: PermutationResult | None = None
    cuped: CupedResult | None = None
    winsor_cap: float | None = None
    p_adjusted: float = float("nan")
    significant_adjusted: bool = False

    @property
    def moved_in_intended_direction(self) -> bool:
        wanted_up = self.spec.direction == "increase"
        return self.test.absolute_diff > 0 if wanted_up else self.test.absolute_diff < 0

    @property
    def verdict(self) -> str:
        """One-line read of this metric, after multiple-testing correction."""
        if not self.significant_adjusted:
            return "flat"
        return "win" if self.moved_in_intended_direction else "regression"

    def to_row(self) -> dict:
        t = self.test
        lo, hi = t.relative_ci
        return {
            "metric": self.spec.name,
            "role": "primary"
            if self.spec.primary
            else ("guardrail" if self.spec.guardrail else "secondary"),
            "method": t.method,
            "control": t.mean_control,
            "treatment": t.mean_treatment,
            "absolute_diff": t.absolute_diff,
            "relative_diff": t.relative_diff,
            "ci_low": t.ci_low,
            "ci_high": t.ci_high,
            "rel_ci_low": lo,
            "rel_ci_high": hi,
            "p_value": t.p_value,
            "p_adjusted": self.p_adjusted,
            "significant": self.significant_adjusted,
            "verdict": self.verdict,
            "mde_absolute": t.mde_absolute,
            "power_observed": t.power_observed,
            "prob_better": self.bayesian.prob_treatment_better if self.bayesian else np.nan,
            "expected_loss": self.bayesian.expected_loss_treatment if self.bayesian else np.nan,
        }


@dataclass
class ExperimentResults:
    """Complete, report-ready output of one experiment analysis."""

    config: ExperimentConfig
    counts: dict[str, int]
    checks: list[CheckResult]
    outcomes: list[MetricOutcome]
    segments: pd.DataFrame | None = None
    run_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )

    # -- views ---------------------------------------------------------
    def summary(self) -> pd.DataFrame:
        """One row per metric: the table that goes in front of stakeholders."""
        return pd.DataFrame([o.to_row() for o in self.outcomes])

    def checks_frame(self) -> pd.DataFrame:
        return checks_to_frame(self.checks)

    def outcome(self, metric_name: str) -> MetricOutcome:
        for o in self.outcomes:
            if o.spec.name == metric_name:
                return o
        raise KeyError(metric_name)

    @property
    def blocking_failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "critical"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def decision(self) -> dict:
        """Ship / do-not-ship recommendation with the reasoning behind it."""
        if self.blocking_failures:
            return {
                "recommendation": "do not use this result",
                "confidence": "none",
                "reason": "; ".join(c.message for c in self.blocking_failures),
            }

        primary = [o for o in self.outcomes if o.spec.primary]
        guardrails = [o for o in self.outcomes if o.spec.guardrail]
        broken = [o for o in guardrails if o.verdict == "regression"]
        wins = [o for o in primary if o.verdict == "win"]
        regressions = [o for o in primary if o.verdict == "regression"]

        if regressions:
            reason = "; ".join(
                f"{o.spec.name} moved {o.test.relative_diff:+.2%} against the "
                f"hypothesis (p={o.p_adjusted:.4f})"
                for o in regressions
            )
            return {"recommendation": "do not ship", "confidence": "high", "reason": reason}
        if broken:
            return {
                "recommendation": "do not ship",
                "confidence": "high",
                "reason": "guardrail regression: "
                + "; ".join(f"{o.spec.name} {o.test.relative_diff:+.2%}" for o in broken),
            }
        if wins:
            return {
                "recommendation": "ship",
                "confidence": "high",
                "reason": "; ".join(
                    f"{o.spec.name} {o.test.relative_diff:+.2%} "
                    f"(95% CI {o.test.relative_ci[0]:+.2%} to {o.test.relative_ci[1]:+.2%})"
                    for o in wins
                ),
            }

        detectable = ", ".join(
            f"{o.spec.name} could only detect {o.test.mde_absolute / o.test.mean_control:+.2%}"
            for o in primary
            if o.test.mean_control
        )
        return {
            "recommendation": "do not ship (no evidence of improvement)",
            "confidence": "medium",
            "reason": f"No primary metric moved significantly. At this sample size, {detectable}.",
        }

    def to_dict(self) -> dict:
        return {
            "experiment": self.config.name,
            "run_at": self.run_at,
            "counts": self.counts,
            "decision": self.decision(),
            "checks": [c.to_dict() for c in self.checks],
            "metrics": [o.to_row() for o in self.outcomes],
        }


class Experiment:
    """Analyse one experiment end to end."""

    def __init__(self, data: ExperimentData, config: ExperimentConfig | None = None):
        self.data = data
        self.config = config or data.config
        self.results: ExperimentResults | None = None

    # ------------------------------------------------------------------
    def _metric_arrays(
        self, spec: MetricSpec
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
        """Return per-arm metric values, and covariate values when configured.

        Rows with a missing metric value are dropped. When a covariate is in
        play the same rows must be dropped from both series, or CUPED is
        handed two arrays that no longer describe the same units - so the
        mask is built from both and applied once.
        """
        cfg = self.config
        arrays: list[np.ndarray] = []
        covariates: list[np.ndarray | None] = []
        for variant in (cfg.control, cfg.treatment):
            frame = self.data.arm(variant)
            values = frame[spec.column].to_numpy(dtype=float)
            keep = ~np.isnan(values)
            covariate = None
            if spec.covariate:
                covariate = frame[spec.covariate].to_numpy(dtype=float)
                keep &= ~np.isnan(covariate)
                covariate = covariate[keep]
            arrays.append(values[keep])
            covariates.append(covariate)
        return arrays[0], arrays[1], covariates[0], covariates[1]

    def _require_dimensions(self, dimensions: list[str]) -> None:
        """Fail with the available columns before any segment work starts."""
        missing = [d for d in dimensions if d not in self.data.df.columns]
        if missing:
            raise ConfigurationError(
                f"Cannot segment by {missing}: not in the data. Available "
                f"columns: {sorted(self.data.df.columns)}"
            )

    def _test_metric(self, spec: MetricSpec) -> MetricOutcome:
        cfg = self.config
        control, treatment, x_control, x_treatment = self._metric_arrays(spec)

        alternative = "two-sided"  # always two-sided: a regression must be visible

        if spec.type == "binary":
            c_conv, t_conv = int(control.sum()), int(treatment.sum())
            test = proportion_test(
                c_conv,
                control.size,
                t_conv,
                treatment.size,
                alpha=cfg.alpha,
                alternative=alternative,
                power=cfg.power,
                metric=spec.name,
            )
            bayes = beta_binomial_test(
                c_conv,
                control.size,
                t_conv,
                treatment.size,
                seed=cfg.seed,
                metric=spec.name,
            )
            return MetricOutcome(spec=spec, test=test, bayesian=bayes)

        cap = None
        if spec.winsorize_quantile is not None:
            # One threshold from the pooled data, applied to both arms, so the
            # capping cannot itself create a difference between variants.
            pooled = np.concatenate([control, treatment])
            _, cap = winsorize(pooled, spec.winsorize_quantile)
            control, _ = winsorize(control, cap=cap)
            treatment, _ = winsorize(treatment, cap=cap)

        cuped = None
        if spec.covariate and x_control is not None and x_treatment is not None:
            cuped = cuped_adjust(control, x_control, treatment, x_treatment)
            control, treatment = cuped.adjusted_control, cuped.adjusted_treatment
            logger.info(
                "CUPED on %s: theta=%.4f, variance reduced %.1f%%",
                spec.name,
                cuped.theta,
                cuped.variance_reduction * 100,
            )

        test = welch_ttest(
            control,
            treatment,
            alpha=cfg.alpha,
            alternative=alternative,
            power=cfg.power,
            metric=spec.name,
        )
        return MetricOutcome(spec=spec, test=test, cuped=cuped, winsor_cap=cap)

    def _resample_metric(self, outcome: MetricOutcome) -> None:
        """Attach bootstrap and permutation results to a continuous metric."""
        cfg = self.config
        spec = outcome.spec
        control = self.data.values(spec, cfg.control)
        treatment = self.data.values(spec, cfg.treatment)
        if outcome.winsor_cap is not None:
            control, _ = winsorize(control, cap=outcome.winsor_cap)
            treatment, _ = winsorize(treatment, cap=outcome.winsor_cap)

        outcome.bootstrap = bootstrap_ci(
            control,
            treatment,
            n_bootstrap=cfg.n_bootstrap,
            alpha=cfg.alpha,
            seed=cfg.seed,
            metric=spec.name,
        )
        outcome.permutation = permutation_test(
            control,
            treatment,
            n_permutations=cfg.n_permutations,
            alpha=cfg.alpha,
            seed=cfg.seed,
            metric=spec.name,
        )

    # ------------------------------------------------------------------
    def run(
        self,
        resample: bool = False,
        segment_by: list[str] | None = None,
    ) -> ExperimentResults:
        """Run the full analysis.

        Args:
            resample: Also compute bootstrap CIs and permutation p-values for
                continuous metrics. Slower, but the honest choice when a
                metric is heavy-tailed.
            segment_by: Pre-experiment dimensions to break the primary metric
                down by. Segments are exploratory: their p-values are
                corrected and should never on their own justify shipping.
        """
        cfg = self.config
        logger.info(
            "Analysing %s: %d metrics, resample=%s, segments=%s",
            cfg.name,
            len(cfg.metrics),
            resample,
            segment_by or [],
        )
        checks = run_all_checks(self.data)
        for check in checks:
            if not check.passed:
                log = logger.error if check.severity == "critical" else logger.warning
                log("Check %s: %s", check.status, check.message)

        with log_duration(logger, f"Tested {len(cfg.metrics)} metrics"):
            outcomes = [self._test_metric(m) for m in cfg.metrics]
        if resample:
            for o in outcomes:
                if o.spec.type == "continuous":
                    self._resample_metric(o)

        adjusted = adjust_pvalues(
            [o.test.p_value for o in outcomes],
            method=cfg.multiple_testing,
            alpha=cfg.alpha,
            labels=[o.spec.name for o in outcomes],
        )
        for outcome, (_, row) in zip(outcomes, adjusted.iterrows(), strict=True):
            outcome.p_adjusted = float(row["p_adjusted"])
            outcome.significant_adjusted = bool(row["significant"])

        segments = None
        if segment_by:
            self._require_dimensions(segment_by)
            for dim in segment_by:
                checks.append(segment_balance(self.data, dim))
            segments = self.analyse_segments(segment_by)

        self.results = ExperimentResults(
            config=cfg,
            counts=self.data.counts(),
            checks=checks,
            outcomes=outcomes,
            segments=segments,
        )
        logger.info("Decision for %s: %s", cfg.name, self.results.decision()["recommendation"])
        return self.results

    # ------------------------------------------------------------------
    def analyse_segments(
        self, dimensions: list[str], metrics: list[str] | None = None
    ) -> pd.DataFrame:
        """Break metrics down by pre-experiment dimensions.

        Every segment test is included in one Benjamini-Hochberg family, so
        the reported significance already accounts for how many slices were
        looked at.
        """
        cfg = self.config
        specs = (
            [cfg.metric(m) for m in metrics]
            if metrics
            else (cfg.primary_metrics or list(cfg.metrics))
        )
        self._require_dimensions(dimensions)
        rows = []
        for dim in dimensions:
            for level, chunk in self.data.df.groupby(dim, dropna=True, observed=True):
                control = chunk[chunk[cfg.variant_col] == cfg.control]
                treatment = chunk[chunk[cfg.variant_col] == cfg.treatment]
                if len(control) < 30 or len(treatment) < 30:
                    continue
                for spec in specs:
                    c = control[spec.column].to_numpy(dtype=float)
                    t = treatment[spec.column].to_numpy(dtype=float)
                    c, t = c[~np.isnan(c)], t[~np.isnan(t)]
                    try:
                        if spec.type == "binary":
                            res = proportion_test(
                                int(c.sum()),
                                c.size,
                                int(t.sum()),
                                t.size,
                                alpha=cfg.alpha,
                                metric=spec.name,
                            )
                        else:
                            res = welch_ttest(c, t, alpha=cfg.alpha, metric=spec.name)
                    except ValueError:
                        continue
                    rows.append(
                        {
                            "dimension": dim,
                            "segment": str(level),
                            "metric": spec.name,
                            "n_control": res.n_control,
                            "n_treatment": res.n_treatment,
                            "control": res.mean_control,
                            "treatment": res.mean_treatment,
                            "relative_diff": res.relative_diff,
                            "ci_low": res.ci_low,
                            "ci_high": res.ci_high,
                            "p_value": res.p_value,
                        }
                    )

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        adj = adjust_pvalues(df["p_value"], method="bh", alpha=cfg.alpha)
        df["p_adjusted"] = adj["p_adjusted"].to_numpy()
        df["significant"] = adj["significant"].to_numpy()
        return df.sort_values(["dimension", "metric", "segment"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    def sensitivity(self, metric_name: str | None = None) -> dict:
        """What effect this experiment was actually able to detect."""
        cfg = self.config
        spec = cfg.metric(metric_name) if metric_name else (cfg.primary_metrics or cfg.metrics)[0]
        counts = self.data.counts()
        baseline = float(np.nanmean(self.data.values(spec, cfg.control)))
        if spec.type != "binary":
            raise UnsupportedMetricError(
                f"Sensitivity is implemented for binary metrics; {spec.name!r} is "
                f"{spec.type}. Use stats.power.sample_size_means for continuous metrics."
            )
        return mde_for_sample(
            baseline,
            counts[cfg.control],
            counts[cfg.treatment],
            alpha=cfg.alpha,
            power=cfg.power,
        )
