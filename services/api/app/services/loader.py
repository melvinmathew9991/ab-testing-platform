"""Reading and profiling uploaded data.

An upload is untrusted input: it can be too big, malformed, empty, or a
spreadsheet someone renamed to .csv. Every one of those is handled here so
that the routers only ever see a validated dataframe, and the caller gets a
message describing what to fix.
"""

from __future__ import annotations

import io

import pandas as pd
from fastapi import UploadFile

from abtest.exceptions import DataValidationError
from abtest.log import get_logger
from app.config import Settings
from app.errors import PayloadTooLarge
from app.schemas import ColumnOut, InspectResponse

logger = get_logger(__name__)

_CHUNK = 1024 * 1024
_ALLOWED_SUFFIXES = (".csv", ".txt", ".parquet")

# Column-name hints, checked in order. Heuristics only: the UI always shows the
# user which columns were chosen and lets them override.
_UNIT_HINTS = ("user_id", "userid", "unit_id", "visitor", "customer", "id")
_VARIANT_HINTS = ("variant", "version", "group", "arm", "bucket", "treatment", "experiment")


async def read_upload(file: UploadFile, settings: Settings) -> pd.DataFrame:
    """Read an uploaded file into a dataframe, enforcing the service limits.

    The size limit is enforced while streaming rather than after buffering:
    the point of the limit is to never hold the oversized payload in memory.
    """
    filename = file.filename or "upload"
    if not filename.lower().endswith(_ALLOWED_SUFFIXES):
        raise DataValidationError(
            f"Unsupported file type {filename!r}. Upload a .csv or .parquet file."
        )

    buffer = io.BytesIO()
    total = 0
    while chunk := await file.read(_CHUNK):
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise PayloadTooLarge(
                f"File exceeds the {settings.max_upload_mb:g} MB limit",
                limit=f"{settings.max_upload_mb:g} MB",
            )
        buffer.write(chunk)

    if total == 0:
        raise DataValidationError("The uploaded file is empty")

    buffer.seek(0)
    try:
        if filename.lower().endswith(".parquet"):
            frame = pd.read_parquet(buffer)
        else:
            frame = pd.read_csv(buffer)
    except UnicodeDecodeError as exc:
        raise DataValidationError(
            "The file is not valid UTF-8 text. Export it as UTF-8 CSV, or upload Parquet."
        ) from exc
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        raise DataValidationError(f"Could not parse {filename!r}: {exc}") from exc
    except MemoryError as exc:  # pragma: no cover - environment dependent
        raise PayloadTooLarge(
            "The file is too large to parse within the service memory limit",
            limit=f"{settings.max_rows:,} rows",
        ) from exc

    return validate_frame(frame, settings, source=filename)


def validate_frame(frame: pd.DataFrame, settings: Settings, source: str) -> pd.DataFrame:
    """Apply the service-level guards that apply to any dataframe."""
    if frame.empty:
        raise DataValidationError(f"{source!r} contains no rows")
    if len(frame) > settings.max_rows:
        raise PayloadTooLarge(
            f"{source!r} has {len(frame):,} rows; this service analyses up to "
            f"{settings.max_rows:,}. Aggregate or sample before uploading.",
            limit=f"{settings.max_rows:,} rows",
        )
    logger.info("Loaded %s: %d rows, %d columns", source, len(frame), frame.shape[1])
    return frame


def _is_binary(series: pd.Series) -> bool:
    """Whether a column holds only 0/1 (or the booleans that equal them)."""
    values = pd.unique(series.dropna())
    if len(values) > 2:
        return False
    # True and False hash equal to 1 and 0, so this covers booleans too.
    return set(values).issubset({0, 1})


def _pick(candidates: list[str], hints: tuple[str, ...]) -> str | None:
    """Prefer a candidate whose name matches a hint, else the first one."""
    lowered = {name: name.lower() for name in candidates}
    for hint in hints:
        for name, low in lowered.items():
            if hint in low:
                return name
    return candidates[0] if candidates else None


def inspect_frame(frame: pd.DataFrame, filename: str) -> InspectResponse:
    """Profile a dataframe so the UI can offer sensible column choices.

    Profiling runs on the whole frame but only computes what the UI shows -
    per column, one pass for uniques and one for nulls.
    """
    n_rows = len(frame)
    columns: list[ColumnOut] = []
    unit_candidates: list[str] = []
    variant_candidates: list[str] = []

    for name in frame.columns:
        series = frame[name]
        n_unique = int(series.nunique(dropna=True))
        n_missing = int(series.isna().sum())
        # A unit column identifies rows: unique, or nearly so if a few units
        # appear twice (which the data contract will report separately).
        unit_candidate = n_unique >= 0.95 * n_rows and n_rows > 1
        variant_candidate = 2 <= n_unique <= 5 and not pd.api.types.is_float_dtype(series)
        if unit_candidate:
            unit_candidates.append(str(name))
        if variant_candidate:
            variant_candidates.append(str(name))

        columns.append(
            ColumnOut(
                name=str(name),
                dtype=str(series.dtype),
                n_missing=n_missing,
                n_unique=n_unique,
                sample_values=[str(v) for v in series.dropna().unique()[:5]],
                binary_candidate=_is_binary(series),
                variant_candidate=variant_candidate,
                unit_candidate=unit_candidate,
            )
        )

    suggested_unit = _pick(unit_candidates, _UNIT_HINTS)
    # A variant column with exactly two levels is what this service can test,
    # so prefer one of those before falling back to any candidate.
    two_level = [c for c in variant_candidates if frame[c].nunique(dropna=True) == 2]
    suggested_variant = _pick(two_level or variant_candidates, _VARIANT_HINTS)
    if suggested_variant == suggested_unit:
        suggested_variant = None

    variants: list[str] = []
    if suggested_variant is not None:
        variants = sorted(str(v) for v in frame[suggested_variant].dropna().unique())

    return InspectResponse(
        filename=filename,
        n_rows=n_rows,
        n_columns=frame.shape[1],
        columns=columns,
        suggested_unit_col=suggested_unit,
        suggested_variant_col=suggested_variant,
        suggested_variants=variants,
    )
