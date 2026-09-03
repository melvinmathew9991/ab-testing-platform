"""Bundled datasets the service can analyse without an upload."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.schemas import DatasetOut, ExperimentConfigIn
from app.services import datasets as demo

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetOut], summary="List demo datasets")
def list_datasets(settings: Settings = Depends(get_settings)) -> list[DatasetOut]:
    return [demo.describe(dataset, settings) for dataset in demo.available(settings)]


@router.get(
    "/{dataset_id}/config",
    response_model=ExperimentConfigIn,
    summary="Default experiment definition for a demo dataset",
)
def default_config(
    dataset_id: str, settings: Settings = Depends(get_settings)
) -> ExperimentConfigIn:
    """The definition the demo is analysed with, as a starting point for edits."""
    return demo.get(dataset_id, settings).default_config()
