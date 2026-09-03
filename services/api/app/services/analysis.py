"""The one place an experiment analysis is assembled.

Validation, analysis and report generation share the same steps up to the
point where they diverge, so they share the same code here rather than each
router repeating it - three copies of "resolve the data, cap the request,
build the config" is three chances for the caps to drift apart.
"""

from __future__ import annotations

import os
import tempfile

import pandas as pd
from fastapi import UploadFile

from abtest.data import ExperimentData
from abtest.exceptions import ConfigurationError
from abtest.experiment import Experiment, ExperimentResults
from abtest.log import get_logger
from abtest.reporting import build_html_report, plots
from app.config import Settings
from app.schemas import AnalyzeRequest, ExperimentConfigIn
from app.services import datasets, loader

logger = get_logger(__name__)


async def resolve_frame(
    file: UploadFile | None, dataset_id: str | None, settings: Settings
) -> tuple[pd.DataFrame, str]:
    """Return the dataframe to analyse, from an upload or a bundled dataset."""
    if file is not None and file.filename:
        return await loader.read_upload(file, settings), file.filename
    if dataset_id:
        frame = datasets.load(dataset_id, settings)
        return loader.validate_frame(frame, settings, source=dataset_id), dataset_id
    raise ConfigurationError(
        "Provide either a file upload or a dataset_id. "
        f"Bundled datasets: {[d.id for d in datasets.available(settings)]}"
    )


def enforce_limits(
    config: ExperimentConfigIn, settings: Settings, resample: bool = False
) -> None:
    """Reject requests whose cost is unbounded before any work starts.

    Resampling is the only part of the library whose runtime the caller
    controls directly, so it is the only part that needs a ceiling here - and
    only when it is actually going to run. A config carrying the library
    default of 10,000 permutations is not a problem for an analysis that
    never resamples.
    """
    if len(config.metrics) > settings.max_metrics:
        raise ConfigurationError(
            f"{len(config.metrics)} metrics requested; this service evaluates up to "
            f"{settings.max_metrics} in one analysis"
        )
    if not resample:
        return
    if config.n_permutations > settings.max_permutations:
        raise ConfigurationError(
            f"n_permutations is capped at {settings.max_permutations:,} in this service "
            f"(requested {config.n_permutations:,})"
        )
    if config.n_bootstrap > settings.max_bootstrap:
        raise ConfigurationError(
            f"n_bootstrap is capped at {settings.max_bootstrap:,} in this service "
            f"(requested {config.n_bootstrap:,})"
        )


def build_data(frame: pd.DataFrame, config: ExperimentConfigIn) -> tuple[ExperimentData, object]:
    """Validate the frame against the experiment definition."""
    experiment_config = config.to_config()
    data = ExperimentData.from_dataframe(frame, experiment_config)
    return data, experiment_config


def run(
    frame: pd.DataFrame, request: AnalyzeRequest, settings: Settings
) -> ExperimentResults:
    """Full analysis. Limits are enforced before any computation."""
    enforce_limits(request.config, settings, resample=request.resample)
    data, config = build_data(frame, request.config)
    experiment = Experiment(data, config)
    return experiment.run(resample=request.resample, segment_by=request.segment_by or None)


def render_report(results: ExperimentResults) -> bytes:
    """Build the self-contained HTML report, figures included.

    Figures are written to a temporary directory and embedded as data URIs by
    the report builder, so nothing survives the request - the service holds no
    state and leaves no files behind on a read-only or ephemeral filesystem.
    """
    summary = results.summary()
    with tempfile.TemporaryDirectory() as tmp:
        figures: list[tuple[str, str]] = []
        try:
            figures.append(
                (
                    "Relative change per metric with 95% confidence intervals. "
                    "Intervals crossing zero are consistent with no effect.",
                    plots.lift_forest(summary, os.path.join(tmp, "lift_forest.png")),
                )
            )
            primary = summary[summary["role"] == "primary"]
            if not primary.empty:
                figures.append(
                    (
                        "Metric levels in both variants.",
                        plots.metric_bars(primary, os.path.join(tmp, "levels.png")),
                    )
                )
        except Exception:
            # A figure is an illustration; the numbers are the deliverable.
            # Never lose the report because a chart could not be drawn.
            logger.exception("Figure generation failed; returning the report without figures")
            figures = []

        output = os.path.join(tmp, "report.html")
        build_html_report(results, figures=figures, output_path=output)
        with open(output, "rb") as handle:
            return handle.read()
