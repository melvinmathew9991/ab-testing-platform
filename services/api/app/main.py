"""Application entry point.

Composition only: configuration, middleware, error handlers and routers. Any
logic that would be tempting to write here belongs in app/services/.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from abtest import __version__ as library_version
from abtest.log import configure_logging, get_logger
from app.config import get_settings
from app.errors import register_exception_handlers
from app.routers import data, datasets, experiments, health, power, sequential
from app.services import datasets as demo

logger = get_logger(__name__)

DESCRIPTION = """
Trustworthy readouts for controlled experiments.

**Plan** an experiment with `/api/v1/power/*`: how much traffic is needed to
detect an effect worth having, and what an existing sample could detect.

**Analyse** one with `/api/v1/experiments/*`: the data contract and trust
checks run first, and a failed critical check blocks the result rather than
decorating it. Metrics are corrected across the family before any of them is
called moved.

**Monitor** a running experiment with `/api/v1/sequential/boundaries`, which
reports what a naive daily check would have concluded alongside what an
alpha-spending boundary allows.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure logging once, and say what the instance can serve."""
    settings = get_settings()
    configure_logging(level=settings.log_level, json_format=settings.log_format == "json")
    available = [d.id for d in demo.available(settings)]
    logger.info(
        "%s %s starting in %s (library %s), demo datasets: %s",
        settings.app_name,
        settings.version,
        settings.environment,
        library_version,
        available or "none",
    )
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    """Build the application. A factory so tests can construct it in isolation."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=DESCRIPTION,
        lifespan=lifespan,
        # The interactive docs are the API's own documentation; keep them in
        # every environment. Nothing here is privileged.
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Tag every request so a user report maps to a log line.

        The id is generated here rather than taken from the client, but an
        upstream id is preserved when present so a trace survives the hop.
        """
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d in %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id, "duration_ms": round(duration_ms, 1)},
        )
        return response

    register_exception_handlers(app)

    for router in (health, datasets, data, experiments, power, sequential):
        app.include_router(router.router)

    return app


app = create_app()
