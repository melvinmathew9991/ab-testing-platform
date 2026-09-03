"""Fixtures for the frontend tests.

The UI is tested against a stub API rather than a live one: what these tests
protect is how the interface behaves when the API answers, and how it behaves
when it does not. Both need to be reproducible, and a real service makes
neither so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

UI_ROOT = Path(__file__).resolve().parents[2] / "services" / "ui"
if str(UI_ROOT) not in sys.path:
    sys.path.insert(0, str(UI_ROOT))

from ui.api_client import ApiClient  # noqa: E402
from ui.config import Settings  # noqa: E402

METRICS = [
    {
        "metric": "retention_7",
        "role": "primary",
        "method": "two-proportion z-test",
        "n_control": 44_700,
        "n_treatment": 45_489,
        "control": 0.1902,
        "treatment": 0.1820,
        "absolute_diff": -0.0082,
        "relative_diff": -0.0431,
        "ci_low": -0.0133,
        "ci_high": -0.0031,
        "rel_ci_low": -0.0698,
        "rel_ci_high": -0.0164,
        "p_value": 0.00155,
        "p_adjusted": 0.00466,
        "significant": True,
        "verdict": "regression",
        "mde_absolute": 0.00726,
        "power_observed": 0.886,
        "prob_better": 0.001,
        "expected_loss": 0.0082,
    },
    {
        "metric": "game_rounds",
        "role": "guardrail",
        "method": "Welch's t-test",
        "n_control": 44_700,
        "n_treatment": 45_489,
        "control": 49.14,
        "treatment": 48.85,
        "absolute_diff": -0.28,
        "relative_diff": -0.0057,
        "ci_low": -1.38,
        "ci_high": 0.82,
        "rel_ci_low": -0.0281,
        "rel_ci_high": 0.0166,
        "p_value": 0.615,
        "p_adjusted": 0.615,
        "significant": False,
        "verdict": "flat",
        "mde_absolute": 1.57,
        "power_observed": 0.073,
        "prob_better": None,
        "expected_loss": None,
    },
]

CHECKS = [
    {
        "check": "sample_ratio_mismatch",
        "status": "PASS",
        "severity": "critical",
        "message": "Split 49.563%/50.437% vs expected 50.0%/50.0%",
    },
    {
        "check": "assignment_integrity",
        "status": "PASS",
        "severity": "warning",
        "message": "No unit appears in both variants",
    },
]

ANALYSIS = {
    "experiment": "Cookie Cats - first gate at level 30 vs level 40",
    "run_at": "2026-09-03 12:00 UTC",
    "counts": {"gate_30": 44_700, "gate_40": 45_489},
    "decision": {
        "recommendation": "do not ship",
        "confidence": "high",
        "reason": "retention_7 moved -4.31% against the hypothesis (p=0.0047)",
    },
    "metrics": METRICS,
    "checks": CHECKS,
    "segments": [],
    "blocking_failures": [],
}

DATASET = {
    "id": "cookie_cats",
    "name": "Cookie Cats - first gate at level 30 vs level 40",
    "description": "90,189 mobile game players randomised between two gate positions.",
    "n_rows": 90_189,
    "unit_col": "userid",
    "variant_col": "version",
    "variants": ["gate_30", "gate_40"],
    "metrics": [
        {"name": "retention_7", "column": "retention_7", "type": "binary", "primary": True}
    ],
    "hypothesis": "Moving the gate later should improve retention.",
}


def stub_api(overrides: dict | None = None) -> httpx.MockTransport:
    """A transport answering the endpoints the UI calls.

    ``overrides`` maps a path to either a response or a callable, so a test
    can make one endpoint fail while the rest behave.
    """
    overrides = overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in overrides:
            override = overrides[path]
            return override(request) if callable(override) else override

        routes = {
            "/health": {"status": "ok", "version": "1.0.0", "environment": "test"},
            "/ready": {"status": "ok", "datasets": ["cookie_cats"]},
            "/api/v1/datasets": [DATASET],
            "/api/v1/datasets/cookie_cats/config": {
                "name": DATASET["name"],
                "unit_col": "userid",
                "variant_col": "version",
                "control": "gate_30",
                "treatment": "gate_40",
                "metrics": DATASET["metrics"],
            },
            "/api/v1/experiments/analyze": ANALYSIS,
            "/api/v1/experiments/validate": {
                "experiment": DATASET["name"],
                "counts": ANALYSIS["counts"],
                "checks": CHECKS,
                "issues": [],
                "usable": True,
            },
            "/api/v1/power/sample-size": {
                "n_control": 168_578,
                "n_treatment": 168_578,
                "n_total": 337_156,
                "baseline_rate": 0.19,
                "mde_absolute": 0.0038,
                "mde_relative": 0.02,
                "alpha": 0.05,
                "power": 0.8,
                "days_required": 28.1,
            },
            "/api/v1/power/mde": {
                "mde_absolute": 0.00738,
                "mde_relative": 0.0388,
                "n_control": 44_700,
                "n_treatment": 45_489,
                "alpha": 0.05,
                "power": 0.8,
            },
            "/api/v1/power/curve": {
                "baseline_rate": 0.19,
                "n_control": 44_700,
                "n_treatment": 45_489,
                "points": [
                    {
                        "effect_relative": i / 100,
                        "effect_absolute": 0.19 * i / 100,
                        "power": min(1.0, 0.05 + i / 12),
                    }
                    for i in range(0, 12)
                ],
            },
            "/api/v1/sequential/boundaries": {
                "looks": [
                    {
                        "look": i,
                        "label": f"week {i}",
                        "n_total": 10_000 * i,
                        "information_fraction": i / 4,
                        "rate_control": 0.19,
                        "rate_treatment": 0.205,
                        "absolute_diff": 0.015,
                        "z_score": 2.4 + i * 0.2,
                        "p_value_fixed": 0.01,
                        "p_threshold_sequential": [0.0001, 0.005, 0.02, 0.05][i - 1],
                        "z_critical": [3.92, 2.77, 2.26, 1.96][i - 1],
                        "stop_sequential": i >= 3,
                        "stop_naive": True,
                    }
                    for i in range(1, 5)
                ],
                "naive_stops": 4,
                "sequential_stops": 2,
            },
        }
        if path in routes:
            return httpx.Response(200, json=routes[path])
        if path == "/api/v1/experiments/report":
            return httpx.Response(
                200,
                content=b"<!doctype html><html>report</html>",
                headers={"content-type": "text/html"},
            )
        if path == "/api/v1/data/inspect":
            return httpx.Response(200, json=INSPECTION)
        return httpx.Response(404, json={"error": "not_found", "message": f"no route {path}"})

    return httpx.MockTransport(handler)


INSPECTION = {
    "filename": "experiment.csv",
    "n_rows": 5_000,
    "n_columns": 4,
    "columns": [
        {
            "name": "user_id",
            "dtype": "int64",
            "n_missing": 0,
            "n_unique": 5_000,
            "sample_values": ["1", "2", "3"],
            "binary_candidate": False,
            "variant_candidate": False,
            "unit_candidate": True,
        },
        {
            "name": "variant",
            "dtype": "object",
            "n_missing": 0,
            "n_unique": 2,
            "sample_values": ["A", "B"],
            "binary_candidate": False,
            "variant_candidate": True,
            "unit_candidate": False,
        },
        {
            "name": "converted",
            "dtype": "int64",
            "n_missing": 0,
            "n_unique": 2,
            "sample_values": ["0", "1"],
            "binary_candidate": True,
            "variant_candidate": True,
            "unit_candidate": False,
        },
        {
            "name": "country",
            "dtype": "object",
            "n_missing": 0,
            "n_unique": 3,
            "sample_values": ["US", "FR", "JP"],
            "binary_candidate": False,
            "variant_candidate": True,
            "unit_candidate": False,
        },
    ],
    "suggested_unit_col": "user_id",
    "suggested_variant_col": "variant",
    "suggested_variants": ["A", "B"],
}


@pytest.fixture
def settings() -> Settings:
    return Settings(api_url="http://api.test", connect_timeout=1.0, read_timeout=5.0)


@pytest.fixture
def client(settings) -> ApiClient:
    """A client wired to the stub transport."""
    api = ApiClient(settings)
    api._client = httpx.Client(base_url=settings.api_url, transport=stub_api())
    return api


def client_with(overrides: dict, settings: Settings | None = None) -> ApiClient:
    """A client whose stub fails on the given paths."""
    settings = settings or Settings(
        api_url="http://api.test", connect_timeout=1.0, read_timeout=5.0
    )
    api = ApiClient(settings)
    api._client = httpx.Client(base_url=settings.api_url, transport=stub_api(overrides))
    return api
