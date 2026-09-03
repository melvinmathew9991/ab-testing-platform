"""HTTP client for the analysis API.

Every failure mode the network offers ends up as one exception type carrying a
message a person can act on: the API is a separate process that can be down,
cold, slow, or answering with a 4xx that already explains itself. The UI
should never have to reason about httpx.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from ui.config import Settings, get_settings

# Retried only for failures that are plausibly transient: a cold instance
# refusing connections, or a proxy returning a gateway error. A 4xx is never
# retried - the request itself is the problem.
_RETRY_STATUSES = {502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.5


@dataclass
class ApiError(Exception):
    """A failed API call, in terms the interface can show a user."""

    message: str
    status_code: int | None = None
    error_code: str | None = None
    request_id: str | None = None
    details: list[dict] | None = None
    retryable: bool = False

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.message

    @property
    def is_client_error(self) -> bool:
        """True when the user can fix this by changing their input."""
        return self.status_code is not None and 400 <= self.status_code < 500


class ApiClient:
    """Thin, synchronous client. One instance per session is enough."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url=self.settings.api_url,
            timeout=httpx.Timeout(
                self.settings.read_timeout, connect=self.settings.connect_timeout
            ),
            follow_redirects=True,
        )

    # -- plumbing ---------------------------------------------------------
    def _raise_for_response(self, response: httpx.Response) -> None:
        """Turn an error response into an ApiError, keeping the API's message."""
        if response.is_success:
            return

        request_id = response.headers.get("X-Request-ID")
        payload: dict[str, Any] = {}
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        message = payload.get("message") or response.text.strip() or "The API returned an error"
        details = payload.get("details")
        if details:
            # Schema violations list the offending fields; showing them beats
            # a generic "request does not match the expected schema".
            readable = "; ".join(
                f"{d.get('field', '?')}: {d.get('message', '')}" for d in details[:5]
            )
            message = f"{message} ({readable})"

        raise ApiError(
            message=message,
            status_code=response.status_code,
            error_code=payload.get("error"),
            request_id=payload.get("request_id") or request_id,
            details=details,
            retryable=response.status_code in _RETRY_STATUSES,
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Send a request, retrying only transient failures."""
        last_error: ApiError | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._client.request(method, path, **kwargs)
                self._raise_for_response(response)
                return response
            except httpx.ConnectError as exc:
                last_error = ApiError(
                    message=(
                        f"Cannot reach the analysis API at {self.settings.api_url}. "
                        "It may still be starting."
                    ),
                    retryable=True,
                )
                last_error.__cause__ = exc
            except httpx.TimeoutException as exc:
                last_error = ApiError(
                    message=(
                        "The API did not respond in time. Large uploads with resampling "
                        "enabled are the usual cause - try fewer permutations."
                    ),
                    retryable=False,
                )
                last_error.__cause__ = exc
                break  # a timeout means work is in flight; do not pile on
            except ApiError as exc:
                if not exc.retryable:
                    raise
                last_error = exc
            except httpx.HTTPError as exc:  # pragma: no cover - unusual transport faults
                last_error = ApiError(message=f"Network error talking to the API: {exc}")
                break

            if attempt < _MAX_ATTEMPTS and last_error and last_error.retryable:
                time.sleep(_BACKOFF_SECONDS * attempt)

        raise last_error or ApiError(message="The API call failed for an unknown reason")

    @staticmethod
    def _multipart(payload: dict, file: tuple[str, bytes] | None):
        """Build the form fields and file part the experiment endpoints expect."""
        import json

        data = {"payload": json.dumps(payload)}
        files = None
        if file is not None:
            filename, content = file
            files = {"file": (filename, content, "text/csv")}
        return data, files

    # -- endpoints --------------------------------------------------------
    def health(self) -> dict:
        return self._request("GET", "/health").json()

    def ready(self) -> dict:
        try:
            return self._request("GET", "/ready").json()
        except ApiError as exc:
            # 503 here is informative, not fatal: uploads still work.
            if exc.status_code == 503:
                return {"status": "degraded", "datasets": []}
            raise

    def datasets(self) -> list[dict]:
        return self._request("GET", "/api/v1/datasets").json()

    def dataset_config(self, dataset_id: str) -> dict:
        return self._request("GET", f"/api/v1/datasets/{dataset_id}/config").json()

    def inspect(self, filename: str, content: bytes) -> dict:
        files = {"file": (filename, content, "text/csv")}
        return self._request("POST", "/api/v1/data/inspect", files=files).json()

    def validate(
        self,
        config: dict,
        dataset_id: str | None = None,
        file: tuple[str, bytes] | None = None,
    ) -> dict:
        data, files = self._multipart({"config": config, "dataset_id": dataset_id}, file)
        return self._request("POST", "/api/v1/experiments/validate", data=data, files=files).json()

    def analyze(
        self,
        config: dict,
        dataset_id: str | None = None,
        file: tuple[str, bytes] | None = None,
        resample: bool = False,
        segment_by: list[str] | None = None,
    ) -> dict:
        payload = {
            "config": config,
            "dataset_id": dataset_id,
            "resample": resample,
            "segment_by": segment_by or [],
        }
        data, files = self._multipart(payload, file)
        return self._request("POST", "/api/v1/experiments/analyze", data=data, files=files).json()

    def report(
        self,
        config: dict,
        dataset_id: str | None = None,
        file: tuple[str, bytes] | None = None,
        resample: bool = False,
    ) -> bytes:
        payload = {"config": config, "dataset_id": dataset_id, "resample": resample}
        data, files = self._multipart(payload, file)
        return self._request("POST", "/api/v1/experiments/report", data=data, files=files).content

    def sample_size(self, **body) -> dict:
        return self._request("POST", "/api/v1/power/sample-size", json=body).json()

    def mde(self, **body) -> dict:
        return self._request("POST", "/api/v1/power/mde", json=body).json()

    def power_curve(self, **body) -> dict:
        return self._request("POST", "/api/v1/power/curve", json=body).json()

    def sequential(self, looks: list[dict], alpha: float = 0.05, planned_n_total=None) -> dict:
        body = {"looks": looks, "alpha": alpha, "planned_n_total": planned_n_total}
        return self._request("POST", "/api/v1/sequential/boundaries", json=body).json()

    def close(self) -> None:
        self._client.close()
