"""Loading and validating unit-level experiment data.

The toolkit works on one row per randomisation unit - usually a user. Getting
that contract right is most of the battle: duplicated units, unexpected
variant labels or missing metrics all quietly corrupt a test.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from abtest.config import ExperimentConfig, MetricSpec
from abtest.exceptions import ConfigurationError, DataValidationError
from abtest.log import get_logger

logger = get_logger(__name__)


@dataclass
class ExperimentData:
    """Validated unit-level experiment data.

    Attributes:
        df: One row per randomisation unit, restricted to the two variants
            named in the config.
        config: The experiment this data belongs to.
        issues: Non-fatal problems found during validation, surfaced in the
            report rather than raised.
    """

    df: pd.DataFrame
    config: ExperimentConfig
    issues: list[str] = field(default_factory=list)
    double_assigned: int = 0
    _arms: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dataframe(
        cls, df: pd.DataFrame, config: ExperimentConfig, validate: bool = True
    ) -> ExperimentData:
        data = cls(df=df.copy(), config=config)
        if validate:
            data.validate()
        return data

    @classmethod
    def from_file(
        cls, path: str | os.PathLike, config: ExperimentConfig, **read_kwargs
    ) -> ExperimentData:
        """Load a CSV or Parquet file of unit-level data."""
        path = str(path)
        if path.endswith(".parquet"):
            df = pd.read_parquet(path, **read_kwargs)
        elif path.endswith((".csv", ".csv.gz", ".txt")):
            df = pd.read_csv(path, **read_kwargs)
        else:
            raise ConfigurationError(f"Unsupported file type: {path}")
        return cls.from_dataframe(df, config)

    def validate(self) -> ExperimentData:
        """Enforce the data contract; fatal problems raise, the rest are logged."""
        cfg = self.config
        df = self.df

        required = [cfg.unit_col, cfg.variant_col] + [m.column for m in cfg.metrics]
        covariates = [m.covariate for m in cfg.metrics if m.covariate]
        missing = [c for c in required + covariates if c not in df.columns]
        if missing:
            raise DataValidationError(f"Missing required columns: {missing}")

        present = set(df[cfg.variant_col].dropna().unique())
        expected = set(cfg.variants)
        if not expected.issubset(present):
            raise DataValidationError(
                f"Variant column {cfg.variant_col!r} has {sorted(present)}, "
                f"expected to find {sorted(expected)}"
            )
        extra = present - expected
        if extra:
            self.issues.append(
                f"Dropped {len(df[df[cfg.variant_col].isin(extra)]):,} rows from "
                f"variants outside the test: {sorted(extra)}"
            )
            df = df[df[cfg.variant_col].isin(expected)]

        # Double assignment has to be measured before de-duplication, or the
        # evidence for it is the very thing that gets dropped. Only repeated
        # ids can be double-assigned, so the grouping runs on that subset
        # rather than on the whole frame.
        repeated = df[cfg.unit_col].duplicated(keep=False)
        n_dupes = int(repeated.sum())
        if n_dupes:
            per_unit_variants = (
                df.loc[repeated, [cfg.unit_col, cfg.variant_col]]
                .groupby(cfg.unit_col, observed=True)[cfg.variant_col]
                .nunique()
            )
            self.double_assigned = int((per_unit_variants > 1).sum())
            if self.double_assigned:
                self.issues.append(
                    f"{self.double_assigned:,} units appear in both variants "
                    f"(double assignment) - their outcomes cannot be attributed "
                    f"to either arm"
                )
            self.issues.append(
                f"{n_dupes:,} rows share a {cfg.unit_col} with another row - each "
                f"unit must appear once; keeping the first occurrence"
            )
            df = df.drop_duplicates(subset=cfg.unit_col, keep="first")

        for metric in cfg.metrics:
            col = df[metric.column]
            n_null = int(col.isna().sum())
            if n_null:
                self.issues.append(
                    f"Metric {metric.name!r}: {n_null:,} missing values ({n_null / len(df):.2%})"
                )
            if metric.type == "binary":
                values = set(pd.unique(col.dropna()))
                if not values.issubset({0, 1}):
                    raise DataValidationError(
                        f"Binary metric {metric.name!r} holds non-binary values: "
                        f"{sorted(values)[:5]}"
                    )

        self.df = df.reset_index(drop=True)
        # One grouping pass replaces a full-frame scan per arm access; the
        # analysis reads each arm many times (checks, tests, resampling).
        self._arms = {
            str(variant): frame
            for variant, frame in self.df.groupby(cfg.variant_col, observed=True)
        }
        logger.info(
            "Validated %s: %d units across %s, %d metrics, %d issues",
            cfg.name,
            len(self.df),
            cfg.variants,
            len(cfg.metrics),
            len(self.issues),
        )
        for issue in self.issues:
            logger.warning("Data quality issue in %s: %s", cfg.name, issue)
        return self

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def arm(self, variant: str) -> pd.DataFrame:
        """Rows belonging to one variant, from the cache built at validation."""
        if variant not in self._arms:
            self._arms[variant] = self.df[self.df[self.config.variant_col] == variant]
        return self._arms[variant]

    def values(self, metric: MetricSpec | str, variant: str) -> np.ndarray:
        """Metric values for one variant as a float array."""
        spec = metric if isinstance(metric, MetricSpec) else self.config.metric(metric)
        return self.arm(variant)[spec.column].to_numpy(dtype=float)

    def counts(self) -> dict[str, int]:
        """Units per variant."""
        counts = self.df[self.config.variant_col].value_counts()
        return {v: int(counts.get(v, 0)) for v in self.config.variants}

    def summary(self) -> pd.DataFrame:
        """Per-variant summary of every configured metric."""
        rows = []
        for metric in self.config.metrics:
            for variant in self.config.variants:
                v = self.values(metric, variant)
                v = v[~np.isnan(v)]
                rows.append(
                    {
                        "metric": metric.name,
                        "variant": variant,
                        "n": int(v.size),
                        "mean": float(v.mean()) if v.size else np.nan,
                        "std": float(v.std(ddof=1)) if v.size > 1 else np.nan,
                        "median": float(np.median(v)) if v.size else np.nan,
                        "p99": float(np.quantile(v, 0.99)) if v.size else np.nan,
                        "max": float(v.max()) if v.size else np.nan,
                    }
                )
        return pd.DataFrame(rows)

    def __len__(self) -> int:
        return len(self.df)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        counts = self.counts()
        return (
            f"<ExperimentData {self.config.name!r}: {len(self):,} units "
            f"({', '.join(f'{k}={v:,}' for k, v in counts.items())}), "
            f"{len(self.config.metrics)} metrics, {len(self.issues)} issues>"
        )
