"""Endpoint behaviour, success paths and failure paths alike.

Failure paths get more attention than success paths here: the service is
exposed to uploads it did not create, and the promise is that a bad request
comes back with something the caller can act on rather than a stack trace or
a 500.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.api.conftest import payload
from tests.conftest import make_data


class TestHealth:
    def test_health_reports_the_version(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ready_lists_available_datasets(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        assert "cookie_cats" in response.json()["datasets"]

    def test_ready_degrades_when_no_dataset_is_present(self, client, settings, tmp_path):
        settings.demo_data_dir = tmp_path  # simulate a broken image
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"

    def test_every_response_carries_a_request_id(self, client):
        response = client.get("/health")
        assert response.headers["X-Request-ID"]

    def test_an_upstream_request_id_is_preserved(self, client):
        response = client.get("/health", headers={"X-Request-ID": "trace-abc"})
        assert response.headers["X-Request-ID"] == "trace-abc"


class TestDatasets:
    def test_list_returns_the_bundled_dataset(self, client):
        response = client.get("/api/v1/datasets")
        assert response.status_code == 200
        [dataset] = response.json()
        assert dataset["id"] == "cookie_cats"
        assert dataset["n_rows"] > 0
        assert set(dataset["variants"]) == {"gate_30", "gate_40"}

    def test_default_config_is_usable_as_sent(self, client):
        config = client.get("/api/v1/datasets/cookie_cats/config").json()
        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(config, dataset_id="cookie_cats"),
        )
        assert response.status_code == 200

    def test_unknown_dataset_returns_404_with_alternatives(self, client):
        response = client.get("/api/v1/datasets/nope/config")
        assert response.status_code == 404
        body = response.json()
        assert body["error"] == "dataset_not_found"
        assert "cookie_cats" in body["available"]


class TestInspect:
    def test_profiles_columns_and_suggests_a_mapping(self, client, csv_upload):
        frame = make_data(n=500, seed=1)
        response = client.post("/api/v1/data/inspect", files={"file": csv_upload(frame)})
        assert response.status_code == 200
        body = response.json()

        assert body["n_rows"] == 500
        assert body["suggested_unit_col"] == "user_id"
        assert body["suggested_variant_col"] == "variant"
        assert body["suggested_variants"] == ["A", "B"]
        converted = next(c for c in body["columns"] if c["name"] == "converted")
        assert converted["binary_candidate"] is True

    def test_rejects_a_file_type_it_cannot_read(self, client, csv_upload):
        frame = make_data(n=10)
        response = client.post(
            "/api/v1/data/inspect", files={"file": csv_upload(frame, "notes.docx")}
        )
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_data"

    def test_rejects_an_empty_file(self, client):
        response = client.post(
            "/api/v1/data/inspect", files={"file": ("empty.csv", b"", "text/csv")}
        )
        assert response.status_code == 422

    def test_rejects_unparseable_content(self, client):
        junk = b"\x00\x01\x02 not a csv \xff\xfe"
        response = client.post(
            "/api/v1/data/inspect", files={"file": ("broken.csv", junk, "text/csv")}
        )
        assert response.status_code == 422

    def test_rejects_an_upload_over_the_size_limit(self, client, settings):
        oversized = b"col\n" + b"x\n" * (settings.max_upload_bytes // 2 + 1024)
        response = client.post(
            "/api/v1/data/inspect", files={"file": ("big.csv", oversized, "text/csv")}
        )
        assert response.status_code == 413
        assert response.json()["error"] == "payload_too_large"

    def test_rejects_more_rows_than_the_service_analyses(self, client, settings, csv_upload):
        settings.max_rows = 100
        response = client.post(
            "/api/v1/data/inspect", files={"file": csv_upload(make_data(n=500))}
        )
        assert response.status_code == 413
        assert "rows" in response.json()["limit"]


class TestValidate:
    def test_reports_checks_without_analysing(self, client, experiment_config):
        response = client.post(
            "/api/v1/experiments/validate",
            data=payload(experiment_config, dataset_id="cookie_cats"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["usable"] is True
        assert {c["check"] for c in body["checks"]} >= {
            "sample_ratio_mismatch",
            "assignment_integrity",
        }

    def test_a_broken_split_marks_the_data_unusable(self, client, experiment_config, csv_upload):
        frame = make_data(n=6_000, seed=2, variant_ratio=0.68).rename(
            columns={"user_id": "userid", "variant": "version"}
        )
        frame["version"] = frame["version"].map({"A": "gate_30", "B": "gate_40"})
        frame["retention_1"] = frame["converted"]
        frame["sum_gamerounds"] = frame["revenue"].round().astype(int)

        response = client.post(
            "/api/v1/experiments/validate",
            data=payload(experiment_config),
            files={"file": csv_upload(frame)},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["usable"] is False
        srm = next(c for c in body["checks"] if c["check"] == "sample_ratio_mismatch")
        assert srm["status"] == "FAIL"


class TestAnalyze:
    def test_analyses_a_bundled_dataset(self, client, experiment_config):
        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(experiment_config, dataset_id="cookie_cats"),
        )
        assert response.status_code == 200
        body = response.json()

        assert set(body["counts"]) == {"gate_30", "gate_40"}
        assert sum(body["counts"].values()) == 4_000
        assert {m["metric"] for m in body["metrics"]} == {"retention_1", "game_rounds"}
        assert body["decision"]["recommendation"]
        retention = next(m for m in body["metrics"] if m["metric"] == "retention_1")
        assert retention["p_adjusted"] >= retention["p_value"] - 1e-12
        assert retention["prob_better"] is not None

    def test_analyses_an_upload(self, client, experiment_config, csv_upload):
        uploaded = make_data(n=5_000, lift=0.2, seed=3).rename(
            columns={"user_id": "userid", "variant": "version"}
        )
        uploaded["version"] = uploaded["version"].map({"A": "gate_30", "B": "gate_40"})
        uploaded["retention_1"] = uploaded["converted"]
        uploaded["sum_gamerounds"] = uploaded["revenue"].round().astype(int)

        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(experiment_config),
            files={"file": csv_upload(uploaded)},
        )
        assert response.status_code == 200
        assert response.json()["metrics"][0]["n_control"] > 0

    def test_resampling_adds_permutation_and_bootstrap_results(
        self, client, experiment_config, csv_upload
    ):
        config = dict(experiment_config, n_permutations=200, n_bootstrap=200)
        frame = make_data(n=2_000, seed=4).rename(
            columns={"user_id": "userid", "variant": "version"}
        )
        frame["version"] = frame["version"].map({"A": "gate_30", "B": "gate_40"})
        frame["retention_1"] = frame["converted"]
        frame["sum_gamerounds"] = frame["revenue"].round().astype(int)

        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(config, resample=True),
            files={"file": csv_upload(frame)},
        )
        assert response.status_code == 200
        rounds = next(m for m in response.json()["metrics"] if m["metric"] == "game_rounds")
        assert rounds["permutation_p_value"] is not None
        assert rounds["bootstrap_ci_low"] is not None

    def test_broken_data_returns_a_result_that_says_so(
        self, client, experiment_config, csv_upload
    ):
        """A failed critical check is an answer, not an error."""
        frame = make_data(n=4_000, seed=6, variant_ratio=0.7).rename(
            columns={"user_id": "userid", "variant": "version"}
        )
        frame["version"] = frame["version"].map({"A": "gate_30", "B": "gate_40"})
        frame["retention_1"] = frame["converted"]
        frame["sum_gamerounds"] = frame["revenue"].round().astype(int)

        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(experiment_config),
            files={"file": csv_upload(frame)},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["blocking_failures"]
        assert body["decision"]["recommendation"] == "do not use this result"

    def test_missing_column_is_reported_with_the_column_name(
        self, client, experiment_config, csv_upload
    ):
        frame = make_data(n=200).rename(columns={"user_id": "userid", "variant": "version"})
        frame["version"] = frame["version"].map({"A": "gate_30", "B": "gate_40"})
        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(experiment_config),
            files={"file": csv_upload(frame)},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "invalid_data"
        assert "retention_1" in body["message"]

    def test_neither_file_nor_dataset_is_a_clear_error(self, client, experiment_config):
        response = client.post("/api/v1/experiments/analyze", data=payload(experiment_config))
        assert response.status_code == 422
        assert "dataset_id" in response.json()["message"]

    def test_malformed_payload_json_names_the_field(self, client):
        response = client.post(
            "/api/v1/experiments/analyze", data={"payload": "{not json"}
        )
        assert response.status_code == 422
        assert "payload" in response.json()["message"]

    def test_invalid_configuration_is_rejected_before_any_work(self, client, experiment_config):
        bad = dict(experiment_config, control="gate_30", treatment="gate_30")
        response = client.post(
            "/api/v1/experiments/analyze", data=payload(bad, dataset_id="cookie_cats")
        )
        assert response.status_code == 422

    def test_duplicate_metric_names_are_rejected(self, client, experiment_config):
        bad = dict(experiment_config)
        bad["metrics"] = [
            {"name": "same", "column": "retention_1", "type": "binary"},
            {"name": "same", "column": "retention_7", "type": "binary"},
        ]
        response = client.post(
            "/api/v1/experiments/analyze", data=payload(bad, dataset_id="cookie_cats")
        )
        assert response.status_code == 422
        assert "Duplicate metric names" in response.json()["message"]

    def test_permutation_count_is_capped(self, client, experiment_config, settings):
        config = dict(experiment_config, n_permutations=settings.max_permutations + 1)
        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(config, dataset_id="cookie_cats", resample=True),
        )
        assert response.status_code == 422
        assert "capped" in response.json()["message"]

    def test_unknown_segment_dimension_lists_the_columns(self, client, experiment_config):
        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(experiment_config, dataset_id="cookie_cats", segment_by=["nope"]),
        )
        assert response.status_code == 422
        assert "Available columns" in response.json()["message"]

    def test_a_zero_baseline_metric_serialises_as_null(self, client, csv_upload):
        """NaN is not valid JSON; the wire format uses null for undefined."""
        frame = make_data(n=1_000, seed=7).rename(
            columns={"user_id": "userid", "variant": "version"}
        )
        frame["version"] = frame["version"].map({"A": "gate_30", "B": "gate_40"})
        frame["never"] = 0

        config = {
            "name": "zero baseline",
            "unit_col": "userid",
            "variant_col": "version",
            "control": "gate_30",
            "treatment": "gate_40",
            "metrics": [{"name": "never", "column": "never", "type": "binary", "primary": True}],
        }
        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(config),
            files={"file": csv_upload(frame)},
        )
        assert response.status_code == 200
        assert response.json()["metrics"][0]["relative_diff"] is None


class TestReport:
    def test_returns_a_self_contained_html_attachment(self, client, experiment_config):
        response = client.post(
            "/api/v1/experiments/report",
            data=payload(experiment_config, dataset_id="cookie_cats"),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "attachment" in response.headers["content-disposition"]

        html = response.text
        assert "<!doctype html>" in html.lower()
        assert "data:image/png;base64" in html  # figures embedded, not linked
        assert "http://" not in html

    def test_report_rejects_the_same_bad_input_as_analyze(self, client, experiment_config):
        bad = dict(experiment_config, alpha=1.5)
        response = client.post(
            "/api/v1/experiments/report", data=payload(bad, dataset_id="cookie_cats")
        )
        assert response.status_code == 422


class TestPower:
    def test_sample_size_translates_into_days(self, client):
        response = client.post(
            "/api/v1/power/sample-size",
            json={"baseline_rate": 0.19, "mde_relative": 0.05, "daily_traffic": 10_000},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["n_total"] == body["n_control"] + body["n_treatment"]
        assert body["days_required"] == pytest.approx(body["n_total"] / 10_000, rel=0.01)

    def test_sample_size_requires_an_effect(self, client):
        response = client.post("/api/v1/power/sample-size", json={"baseline_rate": 0.19})
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_request"

    def test_baseline_outside_zero_to_one_is_rejected(self, client):
        response = client.post(
            "/api/v1/power/sample-size", json={"baseline_rate": 1.4, "mde_relative": 0.05}
        )
        assert response.status_code == 422

    def test_effect_that_pushes_past_certainty_is_rejected(self, client):
        response = client.post(
            "/api/v1/power/sample-size", json={"baseline_rate": 0.9, "mde_relative": 0.5}
        )
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_configuration"

    def test_mde_is_the_inverse_of_sample_size(self, client):
        size = client.post(
            "/api/v1/power/sample-size", json={"baseline_rate": 0.2, "mde_relative": 0.05}
        ).json()
        mde = client.post(
            "/api/v1/power/mde",
            json={"baseline_rate": 0.2, "n_control": size["n_control"]},
        ).json()
        assert mde["mde_relative"] == pytest.approx(0.05, abs=0.005)

    def test_curve_is_monotonic_and_starts_at_alpha(self, client):
        response = client.post(
            "/api/v1/power/curve",
            json={"baseline_rate": 0.2, "n_control": 5_000, "points": 25},
        )
        assert response.status_code == 200
        powers = [p["power"] for p in response.json()["points"]]
        assert powers[0] == pytest.approx(0.05, abs=0.01)
        # Deliberately offset pairing, so the lengths differ by one.
        assert all(b >= a - 1e-9 for a, b in zip(powers, powers[1:]))  # noqa: B905

    def test_curve_point_limit_is_enforced(self, client):
        response = client.post(
            "/api/v1/power/curve",
            json={"baseline_rate": 0.2, "n_control": 5_000, "points": 5_000},
        )
        assert response.status_code == 422


class TestSequential:
    def _looks(self, n: int = 4) -> list[dict]:
        return [
            {
                "label": f"week {i}",
                "n_control": 1_000 * i,
                "n_treatment": 1_000 * i,
                "conversions_control": 200 * i,
                "conversions_treatment": 230 * i,
            }
            for i in range(1, n + 1)
        ]

    def test_reports_both_decisions_per_look(self, client):
        response = client.post(
            "/api/v1/sequential/boundaries", json={"looks": self._looks()}
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["looks"]) == 4
        assert body["naive_stops"] >= body["sequential_stops"]
        first = body["looks"][0]
        assert first["z_critical"] > 1.96  # early looks face a stricter bar

    def test_rejects_impossible_conversion_counts(self, client):
        looks = self._looks(1)
        looks[0]["conversions_control"] = looks[0]["n_control"] + 1
        response = client.post("/api/v1/sequential/boundaries", json={"looks": looks})
        assert response.status_code == 422

    def test_requires_at_least_one_look(self, client):
        response = client.post("/api/v1/sequential/boundaries", json={"looks": []})
        assert response.status_code == 422


class TestContract:
    def test_openapi_schema_is_served(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/v1/experiments/analyze" in paths
        assert "/api/v1/power/sample-size" in paths

    def test_docs_render(self, client):
        assert client.get("/docs").status_code == 200

    def test_unknown_route_is_a_clean_404(self, client):
        assert client.get("/api/v1/nope").status_code == 404

    def test_no_response_leaks_internal_paths(self, client, experiment_config):
        bad = dict(experiment_config, alpha=2.0)
        response = client.post(
            "/api/v1/experiments/analyze", data=payload(bad, dataset_id="cookie_cats")
        )
        body = json.dumps(response.json())
        assert "Traceback" not in body
        assert "site-packages" not in body
        assert "services\\api" not in body and "services/api" not in body

    def test_unexpected_failure_returns_a_request_id_and_no_detail(
        self, client, experiment_config, monkeypatch
    ):
        """The 500 path: the caller gets an id, the log gets the traceback."""
        from app.services import analysis

        def explode(*args, **kwargs):
            raise RuntimeError("database on fire")

        monkeypatch.setattr(analysis, "run", explode)
        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(experiment_config, dataset_id="cookie_cats"),
        )
        assert response.status_code == 500
        body = response.json()
        assert body["error"] == "internal_error"
        assert body["request_id"]
        assert "database on fire" not in json.dumps(body)


class TestNumericSafety:
    def test_all_response_floats_are_json_safe(self, client, experiment_config, csv_upload):
        """Guards against NaN or Infinity reaching a JSON parser."""
        frame = make_data(n=800, seed=8).rename(
            columns={"user_id": "userid", "variant": "version"}
        )
        frame["version"] = frame["version"].map({"A": "gate_30", "B": "gate_40"})
        frame["retention_1"] = frame["converted"]
        frame["sum_gamerounds"] = np.zeros(len(frame), dtype=int)  # zero variance

        response = client.post(
            "/api/v1/experiments/analyze",
            data=payload(experiment_config),
            files={"file": csv_upload(frame)},
        )
        assert response.status_code == 200
        raw = response.text
        assert "NaN" not in raw and "Infinity" not in raw
