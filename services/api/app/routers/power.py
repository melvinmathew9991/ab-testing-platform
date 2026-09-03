"""Planning an experiment before it runs."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter

from abtest.stats.power import mde_for_sample, power_curve, sample_size_proportions
from app.schemas import (
    MdeRequest,
    MdeResponse,
    PowerCurvePoint,
    PowerCurveRequest,
    PowerCurveResponse,
    SampleSizeRequest,
    SampleSizeResponse,
)

router = APIRouter(prefix="/api/v1/power", tags=["power"])


@router.post("/sample-size", response_model=SampleSizeResponse, summary="Traffic required")
def sample_size(request: SampleSizeRequest) -> SampleSizeResponse:
    """Units per variant needed to detect the effect asked for.

    When daily traffic is supplied the answer also comes back in days, which
    is the unit the decision is actually made in.
    """
    result = sample_size_proportions(
        baseline_rate=request.baseline_rate,
        mde_relative=request.mde_relative,
        mde_absolute=request.mde_absolute,
        alpha=request.alpha,
        power=request.power,
        ratio=request.ratio,
    )
    days = None
    if request.daily_traffic:
        days = round(result["n_total"] / request.daily_traffic, 1)
    return SampleSizeResponse(**result, days_required=days)


@router.post("/mde", response_model=MdeResponse, summary="Smallest detectable effect")
def mde(request: MdeRequest) -> MdeResponse:
    """What an experiment of this size could have seen."""
    return MdeResponse(
        **mde_for_sample(
            baseline_rate=request.baseline_rate,
            n_control=request.n_control,
            n_treatment=request.n_treatment,
            alpha=request.alpha,
            power=request.power,
        )
    )


@router.post("/curve", response_model=PowerCurveResponse, summary="Power curve")
def curve(request: PowerCurveRequest) -> PowerCurveResponse:
    """Detection probability across a range of true effects."""
    effects = np.linspace(0.0, request.max_effect_relative, request.points)
    frame = power_curve(
        baseline_rate=request.baseline_rate,
        effects_relative=effects,
        n_control=request.n_control,
        n_treatment=request.n_treatment,
        alpha=request.alpha,
    )
    points = [
        PowerCurvePoint(
            effect_relative=float(row.effect_relative),
            effect_absolute=float(row.effect_absolute),
            # Effects pushing the treatment rate outside (0, 1) are undefined
            # rather than zero; null says so.
            power=None if np.isnan(row.power) else float(row.power),
        )
        for row in frame.itertuples()
    ]
    return PowerCurveResponse(
        baseline_rate=request.baseline_rate,
        n_control=request.n_control,
        n_treatment=request.n_treatment or request.n_control,
        points=points,
    )
