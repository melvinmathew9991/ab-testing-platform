"""The API client, especially what it does when the API misbehaves.

Every one of these failures is one a user will eventually see, so each has to
arrive as a sentence they can act on rather than a transport exception.
"""

from __future__ import annotations

import httpx
import pytest

from tests.ui.conftest import client_with
from ui.api_client import ApiClient, ApiError
from ui.config import Settings


class TestSuccessPaths:
    def test_health(self, client):
        assert client.health()["status"] == "ok"

    def test_datasets_and_config(self, client):
        [dataset] = client.datasets()
        assert dataset["id"] == "cookie_cats"
        assert client.dataset_config("cookie_cats")["control"] == "gate_30"

    def test_analyze_returns_the_decision(self, client):
        result = client.analyze({"name": "x"}, dataset_id="cookie_cats")
        assert result["decision"]["recommendation"] == "do not ship"
        assert len(result["metrics"]) == 2

    def test_report_returns_bytes(self, client):
        assert client.report({"name": "x"}, dataset_id="cookie_cats").startswith(b"<!doctype")

    def test_power_endpoints(self, client):
        assert client.sample_size(baseline_rate=0.19, mde_relative=0.02)["n_total"] == 337_156
        assert client.mde(baseline_rate=0.19, n_control=44_700)["mde_relative"] > 0
        assert client.power_curve(baseline_rate=0.19, n_control=44_700)["points"]

    def test_sequential(self, client):
        result = client.sequential(
            looks=[
                {
                    "n_control": 10,
                    "n_treatment": 10,
                    "conversions_control": 1,
                    "conversions_treatment": 2,
                }
            ]
        )
        assert result["naive_stops"] >= result["sequential_stops"]

    def test_upload_is_sent_as_multipart(self, client):
        assert client.inspect("experiment.csv", b"a,b\n1,2\n")["n_rows"] == 5_000


class TestFailureHandling:
    def test_client_error_keeps_the_api_message(self):
        api = client_with(
            {
                "/api/v1/experiments/analyze": httpx.Response(
                    422,
                    json={
                        "error": "invalid_data",
                        "message": "Missing required columns: ['retention_7']",
                        "request_id": "abc123",
                    },
                )
            }
        )
        with pytest.raises(ApiError) as caught:
            api.analyze({"name": "x"}, dataset_id="cookie_cats")

        error = caught.value
        assert "Missing required columns" in error.message
        assert error.status_code == 422
        assert error.request_id == "abc123"
        assert error.is_client_error
        assert not error.retryable

    def test_schema_details_are_folded_into_the_message(self):
        api = client_with(
            {
                "/api/v1/power/sample-size": httpx.Response(
                    422,
                    json={
                        "error": "invalid_request",
                        "message": "Request does not match the expected schema",
                        "details": [{"field": "body.baseline_rate", "message": "must be > 0"}],
                    },
                )
            }
        )
        with pytest.raises(ApiError) as caught:
            api.sample_size(baseline_rate=-1)
        assert "baseline_rate" in caught.value.message

    def test_server_error_is_marked_retryable(self):
        api = client_with({"/health": httpx.Response(503, json={"message": "starting"})})
        with pytest.raises(ApiError) as caught:
            api.health()
        assert caught.value.retryable
        assert not caught.value.is_client_error

    def test_transient_failure_is_retried_then_succeeds(self):
        attempts = {"n": 0}

        def flaky(request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            if attempts["n"] < 3:
                return httpx.Response(503, json={"message": "cold start"})
            return httpx.Response(200, json={"status": "ok", "version": "1", "environment": "t"})

        api = client_with({"/health": flaky})
        assert api.health()["status"] == "ok"
        assert attempts["n"] == 3

    def test_unreachable_api_is_explained_not_raised_as_transport(self):
        settings = Settings(api_url="http://api.test", connect_timeout=0.1, read_timeout=0.5)
        api = ApiClient(settings)

        def refuse(request):
            raise httpx.ConnectError("connection refused", request=request)

        api._client = httpx.Client(base_url=settings.api_url, transport=httpx.MockTransport(refuse))
        with pytest.raises(ApiError) as caught:
            api.health()
        assert "Cannot reach the analysis API" in caught.value.message
        assert caught.value.retryable

    def test_timeout_is_not_retried(self):
        attempts = {"n": 0}

        def slow(request):
            attempts["n"] += 1
            raise httpx.ReadTimeout("too slow", request=request)

        api = client_with({})
        api._client = httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(slow))
        with pytest.raises(ApiError) as caught:
            api.analyze({"name": "x"}, dataset_id="cookie_cats")

        assert "did not respond in time" in caught.value.message
        assert attempts["n"] == 1  # work may still be in flight; do not pile on

    def test_non_json_error_body_still_produces_a_message(self):
        api = client_with({"/health": httpx.Response(500, text="upstream exploded")})
        with pytest.raises(ApiError) as caught:
            api.health()
        assert caught.value.message

    def test_degraded_readiness_is_reported_not_raised(self):
        api = client_with(
            {"/ready": httpx.Response(503, json={"status": "degraded", "datasets": []})}
        )
        assert api.ready()["status"] == "degraded"
