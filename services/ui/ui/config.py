"""Frontend configuration, read from the environment.

The only thing the UI genuinely needs to be told is where the API lives; the
rest are timeouts sized for the work the API actually does.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the frontend."""

    api_url: str = "http://localhost:8000"
    # Connecting should be instant; a cold Cloud Run instance takes a few
    # seconds, so the connect timeout allows for a container start.
    connect_timeout: float = 10.0
    # A permutation analysis on a large upload is the slow path and can take
    # tens of seconds; a timeout below that would abandon work already done.
    read_timeout: float = 180.0
    max_upload_mb: float = 25.0
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        api_url=os.getenv("API_URL", "http://localhost:8000").rstrip("/"),
        connect_timeout=float(os.getenv("API_CONNECT_TIMEOUT", "10")),
        read_timeout=float(os.getenv("API_READ_TIMEOUT", "180")),
        max_upload_mb=float(os.getenv("MAX_UPLOAD_MB", "25")),
        environment=os.getenv("ENVIRONMENT", "development"),
    )
