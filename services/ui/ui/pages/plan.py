"""Plan an experiment before it runs.

The question this page answers is a scheduling question, not a statistical
one: how long will this take, and is the effect I care about even detectable
in the traffic I have? Answering it afterwards is how underpowered
experiments get run.
"""

from __future__ import annotations

import streamlit as st

from ui import charts, components
from ui.api_client import ApiError
from ui.components import api_status, show_api_error


def _sample_size_tab() -> None:
    st.markdown(
        '<p class="note">Start from the smallest effect worth shipping - the one '
        "that would repay the work - and find out what it costs to detect.</p>",
        unsafe_allow_html=True,
    )

    columns = st.columns(4)
    baseline = (
        columns[0].number_input(
            "Baseline rate (%)",
            min_value=0.1,
            max_value=99.9,
            value=19.0,
            step=0.5,
            help="The conversion rate in control today.",
        )
        / 100
    )
    mde = (
        columns[1].number_input(
            "Smallest effect worth detecting (%)",
            min_value=0.1,
            max_value=200.0,
            value=5.0,
            step=0.5,
            help="Relative to the baseline: 5 means a 5% lift, not 5 points.",
        )
        / 100
    )
    traffic = columns[2].number_input(
        "Units per day",
        min_value=1,
        value=12_000,
        step=100,
        help="How many users enter the experiment daily, across both arms.",
    )
    power = columns[3].select_slider("Power", [0.7, 0.8, 0.9, 0.95], value=0.8)

    columns = st.columns(2)
    alpha = columns[0].select_slider("Significance level", [0.01, 0.05, 0.10], value=0.05)
    ratio = columns[1].select_slider(
        "Treatment share",
        [0.1, 0.2, 0.3, 0.5],
        value=0.5,
        format_func=lambda v: f"{v:.0%} / {1 - v:.0%}",
        help="An uneven split needs more total traffic for the same sensitivity.",
    )

    try:
        result = components.get_client().sample_size(
            baseline_rate=baseline,
            mde_relative=mde,
            alpha=alpha,
            power=power,
            ratio=ratio / (1 - ratio),
            daily_traffic=int(traffic),
        )
    except ApiError as error:
        show_api_error(error)
        return

    st.divider()
    columns = st.columns(3)
    columns[0].metric("Units per variant", f"{result['n_control']:,} / {result['n_treatment']:,}")
    columns[1].metric("Total units", f"{result['n_total']:,}")
    columns[2].metric(
        "Days to run",
        f"{result['days_required']:.1f}" if result.get("days_required") else "-",
    )

    if result.get("days_required", 0) > 60:
        st.warning(
            f"At {traffic:,} units a day this runs for {result['days_required']:.0f} days. "
            "Experiments that long collect seasonality as well as an effect - consider a "
            "larger minimum effect, or accept less power."
        )

    st.caption(
        f"Detecting a {result['mde_relative']:+.1%} relative change "
        f"({result['mde_absolute']:+.4f} absolute) on a {result['baseline_rate']:.2%} "
        f"baseline, at {result['power']:.0%} power and alpha {result['alpha']}."
    )


def _sensitivity_tab() -> None:
    st.markdown(
        '<p class="note">The mirror question, for traffic you already have: what is '
        "the smallest effect this sample could reliably have seen? A flat result on an "
        "underpowered experiment is not evidence of no effect.</p>",
        unsafe_allow_html=True,
    )

    columns = st.columns(4)
    baseline = (
        columns[0].number_input(
            "Baseline rate (%)",
            min_value=0.1,
            max_value=99.9,
            value=19.0,
            step=0.5,
            key="sens_baseline",
        )
        / 100
    )
    n_control = columns[1].number_input("Units in control", min_value=2, value=45_000, step=1_000)
    n_treatment = columns[2].number_input(
        "Units in treatment", min_value=2, value=45_000, step=1_000
    )
    power = columns[3].select_slider("Power", [0.7, 0.8, 0.9, 0.95], value=0.8, key="sens_power")

    client = components.get_client()
    try:
        result = client.mde(
            baseline_rate=baseline,
            n_control=int(n_control),
            n_treatment=int(n_treatment),
            power=power,
        )
        curve = client.power_curve(
            baseline_rate=baseline,
            n_control=int(n_control),
            n_treatment=int(n_treatment),
            max_effect_relative=max(0.05, min(1.0, result["mde_relative"] * 3)),
            points=61,
        )
    except ApiError as error:
        show_api_error(error)
        return

    st.divider()
    columns = st.columns(2)
    columns[0].metric("Smallest detectable effect", f"{result['mde_relative']:+.2%}")
    columns[1].metric("In absolute terms", f"{result['mde_absolute']:+.4f}")
    st.plotly_chart(
        charts.power_curve(
            curve["points"], target_power=power, mde_relative=result["mde_relative"]
        ),
        width="stretch",
    )
    st.caption(
        "Effects to the left of the orange line are not reliably detectable with this "
        "much traffic, however the p-value happens to land."
    )


def render() -> None:
    st.title("Plan an experiment")
    if not api_status():
        return

    before, after = st.tabs(["How much traffic do I need?", "What could this sample detect?"])
    with before:
        _sample_size_tab()
    with after:
        _sensitivity_tab()
