"""Interim monitoring: what checking early costs, and how to do it safely.

Teams check running experiments daily. The problem is not the checking, it is
checking against a threshold designed to be used once. This page shows both
decisions side by side on the reader's own numbers.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import charts, components
from ui.api_client import ApiError
from ui.components import api_status, show_api_error


def _default_looks() -> pd.DataFrame:
    """A plausible run: a promising early gap that shrinks as data arrives.

    Early noise looking like a win is exactly the case a fixed threshold gets
    wrong, so it is the case worth showing by default.
    """
    return pd.DataFrame(
        {
            "label": [f"week {i}" for i in range(1, 5)],
            "n_control": [5_000, 10_000, 15_000, 20_000],
            "n_treatment": [5_000, 10_000, 15_000, 20_000],
            "conversions_control": [950, 1_900, 2_850, 3_800],
            "conversions_treatment": [1_075, 2_090, 3_030, 3_960],
        }
    )


def render() -> None:
    st.title("Peeking at a running experiment")
    st.markdown(
        '<p class="note">Testing at a fixed 0.05 threshold every time you look does '
        "not hold the error rate at 5% - it multiplies the chances of a false positive "
        "by the number of looks. Alpha spending fixes that by making early looks face a "
        "much stricter bar.</p>",
        unsafe_allow_html=True,
    )

    if not api_status():
        return

    st.subheader("The looks")
    st.caption("Cumulative totals at each check - not the increment since the previous one.")
    edited = st.data_editor(
        _default_looks(),
        num_rows="dynamic",
        width="stretch",
        column_config={
            "label": st.column_config.TextColumn("Label", max_chars=100),
            "n_control": st.column_config.NumberColumn("Units, control", min_value=1, step=100),
            "n_treatment": st.column_config.NumberColumn("Units, treatment", min_value=1, step=100),
            "conversions_control": st.column_config.NumberColumn(
                "Conversions, control", min_value=0, step=10
            ),
            "conversions_treatment": st.column_config.NumberColumn(
                "Conversions, treatment", min_value=0, step=10
            ),
        },
    )

    columns = st.columns(2)
    alpha = columns[0].select_slider("Significance level", [0.01, 0.05, 0.10], value=0.05)
    planned = columns[1].number_input(
        "Planned total sample",
        min_value=0,
        value=40_000,
        step=1_000,
        help="What the experiment was powered for. Zero uses the final look as the "
        "full sample. This sets how much alpha each look is allowed to spend.",
    )

    looks = edited.dropna().to_dict("records")
    if not looks:
        st.info("Add at least one look.")
        return

    invalid = [
        look
        for look in looks
        if look["conversions_control"] > look["n_control"]
        or look["conversions_treatment"] > look["n_treatment"]
    ]
    if invalid:
        st.error("Conversions cannot exceed units. Check the rows above.")
        return

    payload = [
        {key: (str(value) if key == "label" else int(value)) for key, value in look.items()}
        for look in looks
    ]
    try:
        result = components.get_client().sequential(
            looks=payload,
            alpha=alpha,
            planned_n_total=int(planned) or None,
        )
    except ApiError as error:
        show_api_error(error)
        return

    st.divider()
    columns = st.columns(2)
    columns[0].metric("Looks a fixed threshold would stop at", result["naive_stops"])
    columns[1].metric("Looks the boundary allows stopping at", result["sequential_stops"])

    gap = result["naive_stops"] - result["sequential_stops"]
    if gap > 0:
        st.warning(
            f"{gap} of these looks would have been called significant by a daily check "
            "while the alpha-spending boundary says to keep waiting. Those are the "
            "decisions that do not replicate."
        )
    else:
        st.success(
            "Both approaches agree on every look here - the evidence is strong enough "
            "to survive the stricter early bar."
        )

    st.plotly_chart(charts.sequential_boundary(result["looks"]), width="stretch")

    frame = pd.DataFrame(result["looks"])[
        [
            "label",
            "n_total",
            "information_fraction",
            "rate_control",
            "rate_treatment",
            "z_score",
            "p_value_fixed",
            "p_threshold_sequential",
            "stop_naive",
            "stop_sequential",
        ]
    ]
    frame.columns = [
        "Look",
        "Units",
        "Information",
        "Control",
        "Treatment",
        "z",
        "p (fixed)",
        "Threshold (sequential)",
        "Fixed stops",
        "Boundary stops",
    ]
    st.dataframe(
        frame.style.format(
            {
                "Units": "{:,.0f}",
                "Information": "{:.0%}",
                "Control": "{:.3%}",
                "Treatment": "{:.3%}",
                "z": "{:.2f}",
                "p (fixed)": "{:.4f}",
                "Threshold (sequential)": "{:.5f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "The boundary is O'Brien-Fleming alpha spending: the error budget is spent "
        "gradually, so the final look still tests at roughly the nominal level while "
        "the first one demands overwhelming evidence."
    )
