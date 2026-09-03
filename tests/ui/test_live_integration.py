"""End-to-end: the real interface against a real API.

The stubbed page tests prove the interface handles the responses it was told
to expect. They cannot prove those are the responses the API actually sends -
a renamed field passes both suites and breaks the product. This one runs the
pages against a live service.

Skipped when no API is reachable, so it never blocks a checkout or CI without
one; run it with the stack up:

    docker compose up -d
    API_URL=http://localhost:8000 pytest tests/ui/test_live_integration.py
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _api_available() -> bool:
    try:
        return httpx.get(f"{API_URL}/health", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _api_available(), reason=f"No API reachable at {API_URL}"
)

LIVE_SCRIPT = """
import sys
sys.path.insert(0, r"{ui_root}")

import streamlit as st
from ui.theme import register_template

register_template()
st.cache_data.clear()

from ui.pages import {module}  # noqa: E402
{module}.render()
"""


def run_live(module: str, timeout: float = 120) -> AppTest:
    script = LIVE_SCRIPT.format(ui_root=REPO_ROOT / "services" / "ui", module=module)
    app = AppTest.from_string(script, default_timeout=timeout)
    app.run()
    return app


def _text(app: AppTest) -> str:
    parts = []
    for kind in ("markdown", "caption", "title", "subheader", "error", "warning", "info"):
        parts += [str(getattr(element, "value", "")) for element in app.get(kind)]
    return "\n".join(parts)


class TestAgainstALiveApi:
    def test_overview_runs_the_real_experiment(self):
        app = run_live("overview")
        assert not app.exception, app.exception

        rendered = _text(app)
        # The published result for this dataset: day-7 retention regresses.
        assert "do not ship" in rendered
        metrics = {m.label: m.value for m in app.metric}
        assert metrics["Units analysed"] == "90,189"
        assert app.get("plotly_chart")

    def test_plan_uses_real_power_calculations(self):
        app = run_live("plan")
        assert not app.exception, app.exception
        metrics = {m.label: m.value for m in app.metric}
        # 19% baseline, 5% relative lift, 80% power - a closed-form answer.
        assert metrics["Total units"] == "54,548"

    def test_peeking_uses_real_boundaries(self):
        app = run_live("peeking")
        assert not app.exception, app.exception
        metrics = {m.label: m.value for m in app.metric}
        assert int(metrics["Looks a fixed threshold would stop at"]) >= int(
            metrics["Looks the boundary allows stopping at"]
        )

    def test_methodology_reports_the_live_api_version(self):
        app = run_live("methodology")
        assert not app.exception, app.exception
        assert "API version" in _text(app)
