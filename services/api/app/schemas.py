"""Request and response models.

These mirror the library's dataclasses rather than reusing them: the wire
format is a contract with the UI and has to stay stable while the library is
free to change. Conversion happens here and nowhere else, so the library never
learns that HTTP exists.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from abtest.checks import CheckResult
from abtest.config import ExperimentConfig, MetricSpec
from abtest.experiment import ExperimentResults, MetricOutcome

# --------------------------------------------------------------------------
# Experiment definition
# --------------------------------------------------------------------------


class MetricIn(BaseModel):
    """One metric to evaluate."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100, examples=["retention_7"])
    column: str = Field(min_length=1, max_length=200)
    type: Literal["binary", "continuous"] = "binary"
    direction: Literal["increase", "decrease"] = "increase"
    primary: bool = False
    guardrail: bool = False
    winsorize_quantile: float | None = Field(default=None, gt=0, le=1)
    covariate: str | None = None

    def to_spec(self) -> MetricSpec:
        return MetricSpec(**self.model_dump())


class ExperimentConfigIn(BaseModel):
    """The experiment definition, as the UI sends it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    unit_col: str = Field(min_length=1, max_length=200)
    variant_col: str = Field(min_length=1, max_length=200)
    control: str = Field(min_length=1, max_length=200)
    treatment: str = Field(min_length=1, max_length=200)
    metrics: list[MetricIn] = Field(min_length=1)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    power: float = Field(default=0.80, gt=0, lt=1)
    expected_split: tuple[float, float] = (0.5, 0.5)
    hypothesis: str = Field(default="", max_length=2000)
    multiple_testing: Literal["none", "bonferroni", "bh"] = "bh"
    n_bootstrap: int = Field(default=10_000, ge=100)
    n_permutations: int = Field(default=10_000, ge=100)
    seed: int = 42

    @field_validator("expected_split")
    @classmethod
    def _split_sums_to_one(cls, value: tuple[float, float]) -> tuple[float, float]:
        if abs(sum(value) - 1) > 1e-9:
            raise ValueError("expected_split must sum to 1")
        return value

    def to_config(self) -> ExperimentConfig:
        """Build the library object. Its own validation still applies."""
        payload = self.model_dump()
        payload["metrics"] = [MetricIn(**m).to_spec() for m in payload["metrics"]]
        payload["expected_split"] = tuple(payload["expected_split"])
        return ExperimentConfig(**payload)


class AnalyzeRequest(BaseModel):
    """An analysis of a bundled dataset, or of an uploaded file."""

    model_config = ConfigDict(extra="forbid")

    config: ExperimentConfigIn
    dataset_id: str | None = Field(
        default=None, description="Bundled dataset to analyse when no file is uploaded"
    )
    resample: bool = Field(
        default=False, description="Add bootstrap intervals and permutation tests"
    )
    segment_by: list[str] = Field(default_factory=list, max_length=5)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


class MetricResultOut(BaseModel):
    """One metric's result, in the shape the UI table needs."""

    metric: str
    role: str
    method: str
    n_control: int
    n_treatment: int
    control: float
    treatment: float
    absolute_diff: float
    relative_diff: float | None
    ci_low: float | None
    ci_high: float | None
    rel_ci_low: float | None
    rel_ci_high: float | None
    p_value: float
    p_adjusted: float
    significant: bool
    verdict: Literal["win", "regression", "flat"]
    mde_absolute: float
    power_observed: float | None
    prob_better: float | None = None
    expected_loss: float | None = None
    winsor_cap: float | None = None
    variance_reduction: float | None = None
    permutation_p_value: float | None = None
    bootstrap_ci_low: float | None = None
    bootstrap_ci_high: float | None = None

    @classmethod
    def from_outcome(cls, outcome: MetricOutcome) -> MetricResultOut:
        row = outcome.to_row()
        test = outcome.test
        return cls(
            **{k: _clean(v) for k, v in row.items()},
            n_control=test.n_control,
            n_treatment=test.n_treatment,
            winsor_cap=_clean(outcome.winsor_cap),
            variance_reduction=(
                _clean(outcome.cuped.variance_reduction) if outcome.cuped else None
            ),
            permutation_p_value=(
                _clean(outcome.permutation.p_value) if outcome.permutation else None
            ),
            bootstrap_ci_low=(_clean(outcome.bootstrap.ci_low) if outcome.bootstrap else None),
            bootstrap_ci_high=(_clean(outcome.bootstrap.ci_high) if outcome.bootstrap else None),
        )


class CheckOut(BaseModel):
    """One trust check."""

    check: str
    status: Literal["PASS", "FAIL", "WARN"]
    severity: Literal["critical", "warning", "info"]
    message: str

    @classmethod
    def from_check(cls, check: CheckResult) -> CheckOut:
        return cls(**check.to_dict())


class DecisionOut(BaseModel):
    """The recommendation, with the reasoning behind it."""

    recommendation: str
    confidence: str
    reason: str


class SegmentOut(BaseModel):
    """One metric within one segment, already corrected across all slices."""

    dimension: str
    segment: str
    metric: str
    n_control: int
    n_treatment: int
    control: float
    treatment: float
    relative_diff: float | None
    p_value: float
    p_adjusted: float
    significant: bool


class AnalyzeResponse(BaseModel):
    """Everything needed to render a readout."""

    experiment: str
    run_at: str
    counts: dict[str, int]
    decision: DecisionOut
    metrics: list[MetricResultOut]
    checks: list[CheckOut]
    segments: list[SegmentOut] = Field(default_factory=list)
    blocking_failures: list[str] = Field(
        default_factory=list,
        description="Critical checks that failed; when present the result must not be used",
    )

    @classmethod
    def from_results(cls, results: ExperimentResults) -> AnalyzeResponse:
        segments: list[SegmentOut] = []
        if results.segments is not None and not results.segments.empty:
            segments = [
                SegmentOut(
                    dimension=row["dimension"],
                    segment=str(row["segment"]),
                    metric=row["metric"],
                    n_control=int(row["n_control"]),
                    n_treatment=int(row["n_treatment"]),
                    control=_clean(row["control"]),
                    treatment=_clean(row["treatment"]),
                    relative_diff=_clean(row["relative_diff"]),
                    p_value=_clean(row["p_value"]),
                    p_adjusted=_clean(row["p_adjusted"]),
                    significant=bool(row["significant"]),
                )
                for _, row in results.segments.iterrows()
            ]
        return cls(
            experiment=results.config.name,
            run_at=results.run_at,
            counts=results.counts,
            decision=DecisionOut(**results.decision()),
            metrics=[MetricResultOut.from_outcome(o) for o in results.outcomes],
            checks=[CheckOut.from_check(c) for c in results.checks],
            segments=segments,
            blocking_failures=[c.message for c in results.blocking_failures],
        )


class ValidateResponse(BaseModel):
    """Trust checks alone, for the pre-analysis step in the UI."""

    experiment: str
    counts: dict[str, int]
    checks: list[CheckOut]
    issues: list[str]
    usable: bool = Field(description="False when a critical check failed")


# --------------------------------------------------------------------------
# Data inspection and datasets
# --------------------------------------------------------------------------


class ColumnOut(BaseModel):
    """One column, with what the UI needs to offer it as a choice."""

    name: str
    dtype: str
    n_missing: int
    n_unique: int
    sample_values: list[str]
    binary_candidate: bool
    variant_candidate: bool
    unit_candidate: bool


class InspectResponse(BaseModel):
    """Shape of an uploaded file, before any experiment is defined."""

    filename: str
    n_rows: int
    n_columns: int
    columns: list[ColumnOut]
    suggested_unit_col: str | None = None
    suggested_variant_col: str | None = None
    suggested_variants: list[str] = Field(default_factory=list)


class DatasetOut(BaseModel):
    """A bundled dataset the service can analyse without an upload."""

    id: str
    name: str
    description: str
    n_rows: int
    unit_col: str
    variant_col: str
    variants: list[str]
    metrics: list[MetricIn]
    hypothesis: str


# --------------------------------------------------------------------------
# Power and sequential monitoring
# --------------------------------------------------------------------------


class SampleSizeRequest(BaseModel):
    """How much traffic is needed to detect an effect worth having."""

    model_config = ConfigDict(extra="forbid")

    baseline_rate: float = Field(gt=0, lt=1)
    mde_relative: float | None = Field(default=None, description="e.g. 0.05 for a 5% lift")
    mde_absolute: float | None = None
    alpha: float = Field(default=0.05, gt=0, lt=1)
    power: float = Field(default=0.80, gt=0, lt=1)
    ratio: float = Field(default=1.0, gt=0, le=10)
    daily_traffic: int | None = Field(
        default=None, gt=0, description="Units per day, to translate the answer into days"
    )

    @model_validator(mode="after")
    def _one_effect_given(self) -> SampleSizeRequest:
        if self.mde_relative is None and self.mde_absolute is None:
            raise ValueError("Provide either mde_relative or mde_absolute")
        return self


class SampleSizeResponse(BaseModel):
    n_control: int
    n_treatment: int
    n_total: int
    baseline_rate: float
    mde_absolute: float
    mde_relative: float
    alpha: float
    power: float
    days_required: float | None = None


class MdeRequest(BaseModel):
    """What the traffic already available can detect."""

    model_config = ConfigDict(extra="forbid")

    baseline_rate: float = Field(gt=0, lt=1)
    n_control: int = Field(gt=1)
    n_treatment: int | None = Field(default=None, gt=1)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    power: float = Field(default=0.80, gt=0, lt=1)


class MdeResponse(BaseModel):
    mde_absolute: float
    mde_relative: float
    n_control: int
    n_treatment: int
    alpha: float
    power: float


class PowerCurveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_rate: float = Field(gt=0, lt=1)
    n_control: int = Field(gt=1)
    n_treatment: int | None = Field(default=None, gt=1)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    max_effect_relative: float = Field(default=0.30, gt=0, le=5)
    points: int = Field(default=61, ge=5, le=500)


class PowerCurvePoint(BaseModel):
    effect_relative: float
    effect_absolute: float
    power: float | None


class PowerCurveResponse(BaseModel):
    baseline_rate: float
    n_control: int
    n_treatment: int
    points: list[PowerCurvePoint]


class LookIn(BaseModel):
    """One interim look at a running experiment."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="", max_length=100)
    n_control: int = Field(gt=0)
    n_treatment: int = Field(gt=0)
    conversions_control: int = Field(ge=0)
    conversions_treatment: int = Field(ge=0)

    @model_validator(mode="after")
    def _conversions_within_units(self) -> LookIn:
        if self.conversions_control > self.n_control:
            raise ValueError("conversions_control cannot exceed n_control")
        if self.conversions_treatment > self.n_treatment:
            raise ValueError("conversions_treatment cannot exceed n_treatment")
        return self


class SequentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    looks: list[LookIn] = Field(min_length=1, max_length=50)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    planned_n_total: int | None = Field(default=None, gt=0)


class SequentialLookOut(BaseModel):
    look: int
    label: str
    n_total: int
    information_fraction: float
    rate_control: float
    rate_treatment: float
    absolute_diff: float
    z_score: float
    p_value_fixed: float
    p_threshold_sequential: float
    z_critical: float
    stop_sequential: bool
    stop_naive: bool


class SequentialResponse(BaseModel):
    looks: list[SequentialLookOut]
    naive_stops: int = Field(description="Looks a fixed 0.05 threshold would have called")
    sequential_stops: int = Field(description="Looks the alpha-spending boundary allows")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    environment: str


def _clean(value):
    """Replace NaN and infinities with None so the response is valid JSON.

    A metric with a zero baseline has an undefined relative effect; the wire
    format says so with null rather than with a token no JSON parser accepts.
    """
    import math

    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value
