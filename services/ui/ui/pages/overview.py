"""Landing page: what the tool does, shown rather than described.

A visitor who uploads nothing should still see a real analysis of a real
experiment, because the argument for the tool is the analysis it produces.
"""

from __future__ import annotations

import streamlit as st

from ui import charts, components
from ui.api_client import ApiError
from ui.components import (
    api_status,
    checks_table,
    decision_banner,
    metrics_table,
    show_api_error,
)


@st.cache_data(ttl=3600, show_spinner=False)
def _demo_analysis() -> tuple[dict, dict]:
    """Run the bundled experiment. Cached: the inputs never change."""
    client = components.get_client()
    datasets = client.datasets()
    if not datasets:
        raise ApiError(message="No demo dataset is available on the API")
    dataset = datasets[0]
    config = client.dataset_config(dataset["id"])
    return dataset, client.analyze(config, dataset_id=dataset["id"])


def render() -> None:
    st.title("Experiment referee")
    st.markdown(
        '<p class="note">Two questions, answered properly: how much traffic an '
        "experiment needs before it starts, and whether its result can be trusted "
        "once it is over.</p>",
        unsafe_allow_html=True,
    )

    if not api_status():
        return

    with st.spinner("Running the bundled experiment..."):
        try:
            dataset, results = _demo_analysis()
        except ApiError as error:
            show_api_error(error)
            return

    st.subheader("A worked example")
    st.markdown(f'<p class="note">{dataset["description"]}</p>', unsafe_allow_html=True)
    with st.expander("The hypothesis under test"):
        st.write(dataset["hypothesis"])

    decision_banner(results["decision"])

    counts = results["counts"]
    columns = st.columns(4)
    columns[0].metric("Units analysed", f"{sum(counts.values()):,}")
    for index, (variant, count) in enumerate(counts.items(), start=1):
        if index < 3:
            columns[index].metric(variant, f"{count:,}")
    primary = [m for m in results["metrics"] if m["role"] == "primary"]
    if primary:
        headline = min(primary, key=lambda m: m["p_adjusted"])
        columns[3].metric(
            headline["metric"],
            f"{headline['relative_diff']:+.2%}" if headline["relative_diff"] else "-",
            delta=headline["verdict"],
            delta_color="off",
        )

    st.plotly_chart(charts.lift_forest(results["metrics"]), width="stretch")
    metrics_table(results["metrics"])

    st.subheader("What a naive read would have missed")
    left, middle, right = st.columns(3)
    with left:
        st.markdown("**The guardrail is one player wide**")
        st.markdown(
            '<p class="note">Raw mean rounds played differ by −2.2% between arms. '
            "Remove the single most extreme player — 49,854 rounds against a median "
            "of 16 — and the gap collapses to −0.08%. The metric is winsorized at the "
            "99th percentile before it is tested.</p>",
            unsafe_allow_html=True,
        )
    with middle:
        st.markdown("**90,000 users is not automatically enough**")
        st.markdown(
            '<p class="note">This experiment could only detect a 3.9% relative change '
            "in day-7 retention. A 2% change would have needed roughly 337,000 players. "
            "Check yours on the <b>Plan</b> page.</p>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown("**Checking daily finds answers too early**")
        st.markdown(
            '<p class="note">Replayed in random arrival order, a fixed 0.05 threshold '
            "fires at every one of eight looks — including at 12% of traffic, where the "
            "boundary demands z > 5.5. See <b>Peeking</b>.</p>",
            unsafe_allow_html=True,
        )

    st.subheader("Trust checks")
    st.markdown(
        '<p class="note">These run before any result is read. A failed critical check '
        "blocks the result instead of appearing as a footnote.</p>",
        unsafe_allow_html=True,
    )
    checks_table(results["checks"])
