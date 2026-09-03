"""Pieces used on more than one page.

Anything a user reads twice should read the same both times - the decision
banner, the metric table, the checks table and the way an API failure is
reported.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.api_client import ApiClient, ApiError
from ui.config import get_settings
from ui.theme import CRITICAL, GOOD, MUTED

_ACCENTS = {
    "ship": GOOD,
    "do not ship": CRITICAL,
    "do not use this result": CRITICAL,
}


@st.cache_resource
def get_client() -> ApiClient:
    """One client per server process; httpx keeps the connection pool."""
    return ApiClient(get_settings())


def show_api_error(error: ApiError) -> None:
    """Report a failed call in terms of what the user can do about it."""
    if error.is_client_error:
        st.error(f"**The request could not be processed.** {error.message}")
    else:
        st.error(
            f"**{error.message}**\n\n"
            "If this persists, the API may be restarting - wait a few seconds and retry."
        )
    if error.request_id:
        st.caption(f"Request id `{error.request_id}` - quote this when reporting the problem.")


def api_status() -> bool:
    """Show whether the API is reachable. Returns False when it is not."""
    client = get_client()
    try:
        state = client.ready()
    except ApiError as error:
        st.error(
            f"**No connection to the analysis API.** {error.message}\n\n"
            f"The interface needs the API at `{get_settings().api_url}`."
        )
        return False

    if state.get("status") == "degraded":
        st.warning(
            "The API is running but has no demo dataset available. "
            "Uploading your own data still works."
        )
    return True


def decision_banner(decision: dict) -> None:
    """The recommendation, with the reasoning that produced it."""
    accent = _ACCENTS.get(decision["recommendation"], MUTED)
    st.markdown(
        f"""<div class="banner" style="--accent:{accent}">
        <div class="verdict">Recommendation: {decision["recommendation"]}</div>
        <div class="reason">{decision["reason"]}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def metrics_table(metrics: list[dict]) -> pd.DataFrame:
    """The results table stakeholders read, formatted for display."""
    rows = []
    for metric in metrics:
        rows.append(
            {
                "Metric": metric["metric"],
                "Role": metric["role"],
                "Control": _number(metric["control"]),
                "Treatment": _number(metric["treatment"]),
                "Lift": _percent(metric["relative_diff"]),
                "95% CI": _interval(metric["rel_ci_low"], metric["rel_ci_high"]),
                "p (adj.)": _pvalue(metric["p_adjusted"]),
                "Verdict": metric["verdict"],
            }
        )
    frame = pd.DataFrame(rows)
    st.dataframe(frame, hide_index=True, width="stretch")
    return frame


def checks_table(checks: list[dict]) -> None:
    """Trust checks, failures first - they are why the table exists."""
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    ordered = sorted(checks, key=lambda c: order.get(c["status"], 3))
    frame = pd.DataFrame(
        [{"Status": c["status"], "Check": c["check"], "Detail": c["message"]} for c in ordered]
    )
    st.dataframe(frame, hide_index=True, width="stretch")


def blocking_warning(blocking: list[str]) -> None:
    """The one state where results must not be read."""
    st.error(
        "**These results cannot be used.** A critical check failed, which means the "
        "two groups are not comparable - no statistical treatment fixes that.\n\n"
        + "\n\n".join(f"- {message}" for message in blocking)
    )


def _number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.4g}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:+.2%}"


def _interval(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "-"
    return f"{low:+.2%} to {high:+.2%}"


def _pvalue(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}" if value >= 1e-4 else "<0.0001"
