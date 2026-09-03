"""Translation from library failures to HTTP responses.

The library raises types that say whose fault a failure is; this module is the
only place that turns them into status codes. Two rules hold throughout:

* a caller always learns enough to fix their request, and never sees a stack
  trace or an internal path;
* every response carries the request id, so a user reporting "it failed" hands
  over the one token needed to find the log line.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from abtest.exceptions import (
    ABTestError,
    ConfigurationError,
    DataValidationError,
    InsufficientDataError,
    UnsupportedMetricError,
)
from abtest.log import get_logger

logger = get_logger(__name__)

# Status codes as integers: Starlette has renamed several of these constants
# between versions, and the numbers are the part of the contract that does not
# move.
HTTP_404_NOT_FOUND = 404
HTTP_409_CONFLICT = 409
HTTP_413_PAYLOAD_TOO_LARGE = 413
HTTP_422_UNPROCESSABLE = 422
HTTP_500_INTERNAL_ERROR = 500


class PayloadTooLarge(Exception):
    """The upload exceeds the configured size or row limit."""

    def __init__(self, message: str, limit: str) -> None:
        super().__init__(message)
        self.message = message
        self.limit = limit


class DatasetNotFound(Exception):
    """A named demo dataset does not exist."""

    def __init__(self, name: str, available: list[str]) -> None:
        super().__init__(name)
        self.name = name
        self.available = available


def _validation_details(exc: RequestValidationError) -> list[dict]:
    """Reduce FastAPI validation errors to serialisable, useful fields.

    ``errors()`` includes a ``ctx`` holding the original exception object,
    which is not JSON serialisable - encoding it raised inside the error
    handler and turned a 422 into a 500. Location, message and type are what
    a client can act on anyway.
    """
    return [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]


def _payload(error: str, message: str, request: Request, **extra) -> dict:
    return {
        "error": error,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
        **extra,
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers. Order does not matter; FastAPI dispatches by type."""

    @app.exception_handler(ConfigurationError)
    async def _configuration_error(request: Request, exc: ConfigurationError):
        # The experiment definition is wrong: the caller can fix it.
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content=_payload("invalid_configuration", str(exc), request),
        )

    @app.exception_handler(DataValidationError)
    async def _data_validation_error(request: Request, exc: DataValidationError):
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content=_payload("invalid_data", str(exc), request),
        )

    @app.exception_handler(UnsupportedMetricError)
    async def _unsupported_metric(request: Request, exc: UnsupportedMetricError):
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content=_payload("unsupported_metric", str(exc), request),
        )

    @app.exception_handler(InsufficientDataError)
    async def _insufficient_data(request: Request, exc: InsufficientDataError):
        # Nothing is malformed - there is simply not enough data to answer.
        return JSONResponse(
            status_code=HTTP_409_CONFLICT,
            content=_payload("insufficient_data", str(exc), request),
        )

    @app.exception_handler(PayloadTooLarge)
    async def _payload_too_large(request: Request, exc: PayloadTooLarge):
        return JSONResponse(
            status_code=HTTP_413_PAYLOAD_TOO_LARGE,
            content=_payload("payload_too_large", exc.message, request, limit=exc.limit),
        )

    @app.exception_handler(DatasetNotFound)
    async def _dataset_not_found(request: Request, exc: DatasetNotFound):
        return JSONResponse(
            status_code=HTTP_404_NOT_FOUND,
            content=_payload(
                "dataset_not_found",
                f"No dataset named {exc.name!r}",
                request,
                available=exc.available,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError):
        # FastAPI's own body/query validation, reshaped to match the envelope
        # above so clients parse one error format rather than two.
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content=_payload(
                "invalid_request",
                "Request does not match the expected schema",
                request,
                details=_validation_details(exc),
            ),
        )

    @app.exception_handler(ABTestError)
    async def _unclassified_library_error(request: Request, exc: ABTestError):
        # A deliberate library failure that has no specific handler: still the
        # caller's business, but log it - the taxonomy may need a new type.
        logger.warning("Unclassified library error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content=_payload("invalid_request", str(exc), request),
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # Anything reaching here is a bug. Log it in full, tell the caller
        # nothing except how to identify the occurrence.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=HTTP_500_INTERNAL_ERROR,
            content=_payload(
                "internal_error",
                "The request could not be completed. Quote the request id when reporting this.",
                request,
            ),
        )
