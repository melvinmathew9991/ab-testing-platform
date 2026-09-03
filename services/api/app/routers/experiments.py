"""Validating and analysing an experiment.

All three endpoints accept the same multipart request: a JSON ``payload``
field plus an optional file. One request shape covers both an upload and a
bundled dataset, so the client has one code path and the service has one set
of limits to enforce.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from abtest.checks import run_all_checks
from abtest.exceptions import ConfigurationError
from abtest.log import get_logger
from app.config import Settings, get_settings
from app.schemas import AnalyzeRequest, AnalyzeResponse, CheckOut, ValidateResponse
from app.services import analysis

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

_PAYLOAD_DESCRIPTION = (
    "JSON matching AnalyzeRequest: the experiment definition, an optional "
    "dataset_id when no file is uploaded, and the analysis options."
)


def _parse(payload: str) -> AnalyzeRequest:
    """Parse the JSON form field into a validated request.

    Form fields arrive as strings, so this is where malformed JSON is caught -
    with a message naming the field, since a client sending the wrong shape
    cannot otherwise see which part the server rejected.
    """
    try:
        return AnalyzeRequest.model_validate_json(payload)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"The payload field is not valid JSON: {exc}") from exc
    except ValueError as exc:
        raise ConfigurationError(
            f"The payload field does not match AnalyzeRequest: {exc}"
        ) from exc


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Run the data contract and trust checks only",
)
async def validate(
    payload: str = Form(..., description=_PAYLOAD_DESCRIPTION),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
) -> ValidateResponse:
    """Check whether the data can be analysed, without analysing it.

    Cheap enough to run while someone is still choosing columns, and it is the
    step that catches a broken split before anyone reads a result.
    """
    request = _parse(payload)
    frame, _ = await analysis.resolve_frame(file, request.dataset_id, settings)
    analysis.enforce_limits(request.config, settings)

    data, config = analysis.build_data(frame, request.config)
    checks = run_all_checks(data)
    blocking = [c for c in checks if not c.passed and c.severity == "critical"]

    return ValidateResponse(
        experiment=config.name,
        counts=data.counts(),
        checks=[CheckOut.from_check(c) for c in checks],
        issues=data.issues,
        usable=not blocking,
    )


@router.post("/analyze", response_model=AnalyzeResponse, summary="Analyse an experiment")
async def analyze(
    payload: str = Form(..., description=_PAYLOAD_DESCRIPTION),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    """Run the full analysis and return the decision with its evidence.

    A failed critical check does not fail the request: the response carries
    the checks and a recommendation not to use the result, because "your data
    is broken, here is why" is the answer, not an error.
    """
    request = _parse(payload)
    frame, source = await analysis.resolve_frame(file, request.dataset_id, settings)
    results = analysis.run(frame, request, settings)
    logger.info(
        "Analysed %s from %s: %s",
        results.config.name,
        source,
        results.decision()["recommendation"],
    )
    return AnalyzeResponse.from_results(results)


@router.post(
    "/report",
    summary="Analyse and return a self-contained HTML report",
    response_class=Response,
    responses={
        200: {"content": {"text/html": {}}, "description": "Standalone HTML report"}
    },
)
async def report(
    payload: str = Form(..., description=_PAYLOAD_DESCRIPTION),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
) -> Response:
    """The same analysis, rendered as a single downloadable file."""
    request = _parse(payload)
    frame, _ = await analysis.resolve_frame(file, request.dataset_id, settings)
    results = analysis.run(frame, request, settings)
    html = analysis.render_report(results)

    stem = results.config.name[:60].replace(" ", "_").replace("/", "-")
    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{stem}_report.html"'},
    )
