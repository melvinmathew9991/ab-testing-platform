"""Liveness and readiness.

Cloud Run restarts an instance that stops answering /health, and holds
traffic from one whose /ready reports it cannot serve. They answer different
questions, so they are separate endpoints rather than one alias.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.config import Settings, get_settings
from app.schemas import HealthResponse
from app.services import datasets

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness")
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """The process is up. Deliberately does no work."""
    return HealthResponse(status="ok", version=settings.version, environment=settings.environment)


@router.get("/ready", summary="Readiness")
def ready(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    """The process can serve requests.

    Demo datasets are the only external thing the service depends on; if they
    are missing the API still analyses uploads, so this degrades rather than
    failing outright.
    """
    present = [d.id for d in datasets.available(settings)]
    if not present:
        response.status_code = 503
        return {"status": "degraded", "datasets": present, "detail": "No demo dataset available"}
    return {"status": "ok", "datasets": present}
