"""Monitoring an experiment while it runs."""

from __future__ import annotations

from fastapi import APIRouter

from abtest.stats.sequential import sequential_analysis
from app.schemas import SequentialLookOut, SequentialRequest, SequentialResponse

router = APIRouter(prefix="/api/v1/sequential", tags=["sequential"])


@router.post("/boundaries", response_model=SequentialResponse, summary="Interim analysis")
def boundaries(request: SequentialRequest) -> SequentialResponse:
    """Evaluate interim looks against an alpha-spending boundary.

    The response reports both decisions - what a fixed 0.05 threshold would
    have said at each look, and what the boundary allows - because the gap
    between them is the point.
    """
    looks = [
        {
            "label": look.label or f"look {i}",
            "n_control": look.n_control,
            "n_treatment": look.n_treatment,
            "conversions_control": look.conversions_control,
            "conversions_treatment": look.conversions_treatment,
        }
        for i, look in enumerate(request.looks, start=1)
    ]
    frame = sequential_analysis(
        looks, alpha=request.alpha, planned_n_total=request.planned_n_total
    )
    return SequentialResponse(
        looks=[
            SequentialLookOut(
                look=int(row.look),
                label=str(row.label),
                n_total=int(row.n_total),
                information_fraction=float(row.information_fraction),
                rate_control=float(row.rate_control),
                rate_treatment=float(row.rate_treatment),
                absolute_diff=float(row.absolute_diff),
                z_score=float(row.z_score),
                p_value_fixed=float(row.p_value_fixed),
                p_threshold_sequential=float(row.p_threshold_sequential),
                z_critical=float(row.z_critical),
                stop_sequential=bool(row.stop_sequential),
                stop_naive=bool(row.stop_naive),
            )
            for row in frame.itertuples()
        ],
        naive_stops=int(frame["stop_naive"].sum()),
        sequential_stops=int(frame["stop_sequential"].sum()),
    )
