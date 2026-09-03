"""Inspecting an uploaded file before an experiment is defined."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.config import Settings, get_settings
from app.schemas import InspectResponse
from app.services import loader

router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.post("/inspect", response_model=InspectResponse, summary="Profile an uploaded file")
async def inspect(
    file: UploadFile = File(..., description="CSV or Parquet, one row per unit"),
    settings: Settings = Depends(get_settings),
) -> InspectResponse:
    """Return columns, types and candidate unit/variant columns.

    This is what lets the UI offer a column mapping instead of asking someone
    to type column names correctly.
    """
    frame = await loader.read_upload(file, settings)
    return loader.inspect_frame(frame, file.filename or "upload")
