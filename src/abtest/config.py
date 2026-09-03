"""Experiment configuration objects.

An experiment is described declaratively (in code or YAML) so that the same
analysis can be re-run, reviewed and version-controlled.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Literal, Sequence

import yaml

from abtest.exceptions import ConfigurationError

MetricType = Literal["binary", "continuous"]
Direction = Literal["increase", "decrease"]


@dataclass
class MetricSpec:
    """Definition of a single metric evaluated in an experiment.

    Attributes:
        name: Human readable metric name used in reports.
        column: Column in the unit-level dataframe holding the metric value.
        type: ``binary`` (0/1 per unit) or ``continuous``.
        direction: Whether an increase or a decrease is the desired outcome.
        primary: Primary metrics drive the ship decision; the rest are
            secondary/guardrail metrics and are reported separately.
        guardrail: Metric that must *not* regress, even if it is not the goal.
        winsorize_quantile: Optional upper quantile (e.g. ``0.99``) used to cap
            extreme values of a continuous metric before testing.
        covariate: Optional column with a pre-experiment measurement of the
            same metric, enabling CUPED variance reduction.
    """

    name: str
    column: str
    type: MetricType = "binary"
    direction: Direction = "increase"
    primary: bool = False
    guardrail: bool = False
    winsorize_quantile: float | None = None
    covariate: str | None = None

    def __post_init__(self) -> None:
        if self.type not in ("binary", "continuous"):
            raise ConfigurationError(f"Unknown metric type {self.type!r}")
        if self.direction not in ("increase", "decrease"):
            raise ConfigurationError(f"Unknown direction {self.direction!r}")
        if self.winsorize_quantile is not None:
            if not 0 < self.winsorize_quantile <= 1:
                raise ConfigurationError("winsorize_quantile must be in (0, 1]")
            if self.type != "continuous":
                raise ConfigurationError("Winsorizing only applies to continuous metrics")


@dataclass
class ExperimentConfig:
    """Everything needed to analyse one experiment.

    The defaults encode the decision rules agreed *before* looking at the data:
    significance level, target power and the expected traffic split.
    """

    name: str
    unit_col: str
    variant_col: str
    control: str
    treatment: str
    metrics: Sequence[MetricSpec]
    alpha: float = 0.05
    power: float = 0.80
    expected_split: tuple[float, float] = (0.5, 0.5)
    hypothesis: str = ""
    n_bootstrap: int = 10_000
    n_permutations: int = 10_000
    seed: int = 42
    multiple_testing: Literal["none", "bonferroni", "bh"] = "bh"

    def __post_init__(self) -> None:
        self.metrics = [
            m if isinstance(m, MetricSpec) else MetricSpec(**m) for m in self.metrics
        ]
        if not 0 < self.alpha < 1:
            raise ConfigurationError("alpha must be in (0, 1)")
        if not 0 < self.power < 1:
            raise ConfigurationError("power must be in (0, 1)")
        if abs(sum(self.expected_split) - 1) > 1e-9:
            raise ConfigurationError("expected_split must sum to 1")
        if not self.metrics:
            raise ConfigurationError("An experiment needs at least one metric")
        if self.control == self.treatment:
            raise ConfigurationError(
                f"Control and treatment are both {self.control!r}; an experiment "
                f"needs two distinct variants"
            )
        if self.unit_col == self.variant_col:
            raise ConfigurationError(
                f"unit_col and variant_col are both {self.unit_col!r}"
            )
        names = [m.name for m in self.metrics]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ConfigurationError(
                f"Duplicate metric names: {sorted(duplicates)}. Names identify "
                f"metrics in results and reports, so they must be unique"
            )

    @property
    def variants(self) -> tuple[str, str]:
        return (self.control, self.treatment)

    @property
    def primary_metrics(self) -> list[MetricSpec]:
        return [m for m in self.metrics if m.primary]

    def metric(self, name: str) -> MetricSpec:
        for m in self.metrics:
            if m.name == name:
                return m
        raise KeyError(name)

    @classmethod
    def from_yaml(cls, path: str | os.PathLike) -> "ExperimentConfig":
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        split = raw.get("expected_split")
        if split is not None:
            raw["expected_split"] = tuple(split)
        return cls(**raw)

    def to_dict(self) -> dict:
        return asdict(self)
