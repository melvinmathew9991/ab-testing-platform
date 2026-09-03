"""Every page rendered headlessly, with the API stubbed.

Streamlit fails at runtime rather than at import, so "it renders without an
exception" is a real assertion here. Each page is also checked for the thing it
exists to say, and for what it does when the API is unavailable - a broken
backend must not produce a blank screen.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

PAGE_SCRIPT = """
import sys
from pathlib import Path

import httpx
import streamlit as st

sys.path.insert(0, r"{ui_root}")
sys.path.insert(0, r"{repo_root}")

from ui import components
from ui.api_client import ApiClient
from ui.config import Settings
from ui.theme import register_template
from tests.ui.conftest import stub_api

register_template()

settings = Settings(api_url="http://api.test", connect_timeout=1.0, read_timeout=5.0)
client = ApiClient(settings)
client._client = httpx.Client(base_url=settings.api_url, transport=stub_api({overrides}))

# The pages reach the API through this one accessor, so replacing it is enough
# to run the whole interface against the stub.
components.get_client = lambda: client
st.cache_data.clear()

from ui.pages import {module}  # noqa: E402
{module}.render()
"""


def run_page(module: str, overrides: str = "None", timeout: float = 30) -> AppTest:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    script = PAGE_SCRIPT.format(
        ui_root=repo_root / "services" / "ui",
        repo_root=repo_root,
        module=module,
        overrides=overrides,
    )
    app = AppTest.from_string(script, default_timeout=timeout)
    app.run()
    return app


def text_of(app: AppTest) -> str:
    """All rendered text, for asserting on what a reader would see."""
    parts = []
    for element in app.get("markdown") + app.get("caption") + app.get("title"):
        parts.append(str(getattr(element, "value", "")))
    for element in app.get("error") + app.get("warning") + app.get("success") + app.get("info"):
        parts.append(str(getattr(element, "value", "")))
    for element in app.get("subheader") + app.get("header"):
        parts.append(str(getattr(element, "value", "")))
    return "\n".join(parts)


class TestPagesRender:
    @pytest.mark.parametrize("module", ["overview", "analyze", "plan", "peeking", "methodology"])
    def test_page_renders_without_exception(self, module):
        app = run_page(module)
        assert not app.exception, f"{module} raised: {app.exception}"

    def test_overview_shows_the_decision_and_the_numbers(self):
        app = run_page("overview")
        rendered = text_of(app)
        assert "do not ship" in rendered
        assert "retention_7" in rendered or any(
            "retention_7" in str(df.value) for df in app.get("dataframe")
        )
        assert app.get("plotly_chart")

    def test_plan_reports_traffic_and_duration(self):
        app = run_page("plan")
        metrics = {m.label: m.value for m in app.metric}
        assert "Units per variant" in metrics
        assert metrics["Total units"] == "337,156"
        assert metrics["Days to run"] == "28.1"

    def test_peeking_contrasts_the_two_decisions(self):
        app = run_page("peeking")
        metrics = {m.label: m.value for m in app.metric}
        assert metrics["Looks a fixed threshold would stop at"] == "4"
        assert metrics["Looks the boundary allows stopping at"] == "2"
        assert "would have been called significant" in text_of(app)

    def test_methodology_states_the_limits(self):
        rendered = text_of(run_page("methodology"))
        assert "will not do" in rendered.lower()
        assert "Ratio metrics" in rendered
        assert "two variants" in rendered.lower()

    def test_analyze_starts_at_the_source_step(self):
        app = run_page("analyze")
        assert "Choose the data" in text_of(app)
        assert app.radio


class TestApiFailureStates:
    """A backend that is down must produce an explanation, never a blank page."""

    UNREACHABLE = (
        '{"/ready": __import__("httpx").Response(503, json={"status": "degraded", "datasets": []})}'
    )

    def test_overview_reports_a_degraded_api(self):
        app = run_page("overview", overrides=self.UNREACHABLE)
        assert not app.exception
        assert "no demo dataset" in text_of(app).lower()

    def test_analyze_reports_a_failing_api(self):
        overrides = (
            '{"/api/v1/datasets": __import__("httpx").Response(500, '
            'json={"message": "backend on fire", "request_id": "req-1"})}'
        )
        app = run_page("analyze", overrides=overrides)
        assert not app.exception
        rendered = text_of(app)
        assert "backend on fire" in rendered
        assert "req-1" in rendered  # the id the user should quote

    def test_plan_reports_a_failing_power_endpoint(self):
        overrides = (
            '{"/api/v1/power/sample-size": __import__("httpx").Response(422, '
            'json={"message": "baseline + effect must stay within (0, 1)"})}'
        )
        app = run_page("plan", overrides=overrides)
        assert not app.exception
        assert "baseline + effect" in text_of(app)

    def test_methodology_survives_a_dead_api(self):
        overrides = '{"/health": __import__("httpx").Response(500, json={"message": "down"})}'
        app = run_page("methodology", overrides=overrides)
        assert not app.exception
        assert "not reachable" in text_of(app)
