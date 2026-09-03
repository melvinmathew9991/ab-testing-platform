"""Fixtures for the API tests.

The service is exercised through the real application - routers, middleware
and error handlers included - because most of what these tests protect is
what happens at the boundary, not inside the handlers.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[2] / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.conftest import make_data  # noqa: E402


@pytest.fixture
def demo_dir(tmp_path_factory) -> Path:
    """A demo dataset directory holding a small stand-in for Cookie Cats.

    Using a generated file rather than the real download keeps the API tests
    runnable on a clean checkout, and keeps them fast.
    """
    directory = tmp_path_factory.mktemp("demo_data")
    frame = make_data(n=4_000, lift=0.10, seed=5).rename(
        columns={"user_id": "userid", "variant": "version"}
    )
    frame["version"] = frame["version"].map({"A": "gate_30", "B": "gate_40"})
    frame["retention_1"] = frame["converted"]
    frame["retention_7"] = (frame["converted"] & (frame["revenue"] > 20)).astype(int)
    frame["sum_gamerounds"] = frame["revenue"].round().astype(int)
    frame[["userid", "version", "retention_1", "retention_7", "sum_gamerounds"]].to_csv(
        directory / "cookie_cats.csv", index=False
    )
    return directory


@pytest.fixture
def settings(demo_dir) -> Settings:
    return Settings(
        environment="test",
        demo_data_dir=demo_dir,
        max_upload_mb=1.0,
        max_rows=50_000,
        max_permutations=1_000,
        max_bootstrap=1_000,
    )


@pytest.fixture
def client(settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def experiment_config() -> dict:
    """A valid experiment definition for the generated demo dataset."""
    return {
        "name": "gate placement",
        "unit_col": "userid",
        "variant_col": "version",
        "control": "gate_30",
        "treatment": "gate_40",
        "metrics": [
            {"name": "retention_1", "column": "retention_1", "type": "binary", "primary": True},
            {
                "name": "game_rounds",
                "column": "sum_gamerounds",
                "type": "continuous",
                "guardrail": True,
                "winsorize_quantile": 0.99,
            },
        ],
    }


@pytest.fixture
def csv_upload():
    """Factory returning a (filename, buffer, mimetype) tuple for multipart posts."""

    def _make(frame, filename: str = "experiment.csv"):
        buffer = io.BytesIO()
        frame.to_csv(buffer, index=False)
        buffer.seek(0)
        return (filename, buffer, "text/csv")

    return _make


def payload(config: dict, **options) -> dict:
    """Build the multipart form field the experiment endpoints expect."""
    return {"payload": json.dumps({"config": config, **options})}
