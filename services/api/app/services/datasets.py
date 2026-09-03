"""Bundled demo datasets.

The landing page of the UI has to show a real analysis to someone who has not
uploaded anything, so the service ships with the experiment the project was
built around. Definitions live here rather than in the UI: the API is the
authority on what can be analysed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from abtest.log import get_logger
from app.config import Settings
from app.errors import DatasetNotFound
from app.schemas import DatasetOut, ExperimentConfigIn, MetricIn

logger = get_logger(__name__)


@dataclass(frozen=True)
class DemoDataset:
    """A dataset shipped with the service, plus the experiment it belongs to."""

    id: str
    name: str
    description: str
    filename: str
    unit_col: str
    variant_col: str
    control: str
    treatment: str
    hypothesis: str
    metrics: list[MetricIn] = field(default_factory=list)

    def default_config(self) -> ExperimentConfigIn:
        return ExperimentConfigIn(
            name=self.name,
            unit_col=self.unit_col,
            variant_col=self.variant_col,
            control=self.control,
            treatment=self.treatment,
            hypothesis=self.hypothesis,
            metrics=self.metrics,
        )


COOKIE_CATS = DemoDataset(
    id="cookie_cats",
    name="Cookie Cats - first gate at level 30 vs level 40",
    description=(
        "90,189 mobile game players randomised between a first progression gate "
        "at level 30 and at level 40, with day-1 and day-7 retention and rounds "
        "played in the first week."
    ),
    filename="cookie_cats.csv",
    unit_col="userid",
    variant_col="version",
    control="gate_30",
    treatment="gate_40",
    hypothesis=(
        "Moving the first progression gate from level 30 to level 40 lets players "
        "go deeper before they are blocked, which should increase the share of "
        "players who come back on day 1 and day 7."
    ),
    metrics=[
        MetricIn(name="retention_1", column="retention_1", type="binary", primary=True),
        MetricIn(name="retention_7", column="retention_7", type="binary", primary=True),
        MetricIn(
            name="game_rounds",
            column="sum_gamerounds",
            type="continuous",
            guardrail=True,
            winsorize_quantile=0.99,
        ),
    ],
)

_REGISTRY: dict[str, DemoDataset] = {COOKIE_CATS.id: COOKIE_CATS}


def _path(dataset: DemoDataset, settings: Settings) -> Path:
    return Path(settings.demo_data_dir) / dataset.filename


@lru_cache(maxsize=4)
def _read(path: str) -> pd.DataFrame:
    """Read and cache a demo dataset.

    These files are read-only and shipped with the image, so caching them
    turns every demo request after the first into pure computation. Keyed by
    path string because Path is not hashable across settings instances in a
    way lru_cache can rely on.
    """
    return pd.read_csv(path)


def available(settings: Settings) -> list[DemoDataset]:
    """Datasets whose file is actually present."""
    present = []
    for dataset in _REGISTRY.values():
        if _path(dataset, settings).exists():
            present.append(dataset)
        else:
            logger.warning(
                "Demo dataset %s is registered but missing at %s",
                dataset.id,
                _path(dataset, settings),
            )
    return present


def get(dataset_id: str, settings: Settings) -> DemoDataset:
    dataset = _REGISTRY.get(dataset_id)
    if dataset is None or not _path(dataset, settings).exists():
        raise DatasetNotFound(dataset_id, [d.id for d in available(settings)])
    return dataset


def load(dataset_id: str, settings: Settings) -> pd.DataFrame:
    """Return the dataframe for a bundled dataset."""
    dataset = get(dataset_id, settings)
    try:
        return _read(str(_path(dataset, settings)))
    except OSError as exc:  # pragma: no cover - only on a broken image
        logger.error("Demo dataset %s could not be read: %s", dataset_id, exc)
        raise DatasetNotFound(dataset_id, [d.id for d in available(settings)]) from exc


def describe(dataset: DemoDataset, settings: Settings) -> DatasetOut:
    """Public description, including row count and observed variants."""
    frame = load(dataset.id, settings)
    return DatasetOut(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        n_rows=len(frame),
        unit_col=dataset.unit_col,
        variant_col=dataset.variant_col,
        variants=sorted(str(v) for v in frame[dataset.variant_col].dropna().unique()),
        metrics=dataset.metrics,
        hypothesis=dataset.hypothesis,
    )
