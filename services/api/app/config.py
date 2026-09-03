"""Service configuration, read from the environment.

Every limit here exists because the service is exposed to the internet on a
free tier with a fixed monthly compute grant: an unbounded upload or an
unbounded permutation count is not a performance concern, it is the whole
month's budget. Defaults are sized for the demo workload (a 90k-row CSV is
about 1.5 MB) and can be raised per deployment without a code change.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_demo_dir() -> Path:
    """Where demo data lives when DEMO_DATA_DIR is not set.

    Searching upwards for the directory works in a checkout (where the app
    sits three levels below the repository root) and in the container (where
    it sits directly under /app), instead of assuming a fixed depth that only
    one of the two satisfies.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "raw"
        if candidate.is_dir():
            return candidate
    return Path("data") / "raw"


class Settings(BaseSettings):
    """Runtime configuration. Field names map to upper-case env variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "A/B Testing API"
    version: str = "1.0.0"
    environment: str = Field(default="development", description="development | production")

    log_level: str = "INFO"
    log_format: str = Field(default="text", description="text | json")

    # Cloud Run rejects request bodies above roughly 32 MiB, so the cap stays
    # below that: a request we cannot receive should fail with our message
    # rather than the platform's.
    max_upload_mb: float = 25.0
    max_rows: int = 1_000_000
    max_metrics: int = 20
    # Resampling is the only unbounded cost in the library; 20k permutations on
    # a 90k-row dataset is roughly 40 seconds, which is the ceiling worth
    # allowing inside a request.
    max_permutations: int = 20_000
    max_bootstrap: int = 20_000

    demo_data_dir: Path = Field(default_factory=_default_demo_dir)
    cors_origins: str = Field(
        default="*",
        description="Comma-separated allowed origins; set to the UI URL in production",
    )

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, overridable in tests via dependency_overrides."""
    return Settings()
