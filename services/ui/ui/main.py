"""Streamlit entry point.

Composition only: page configuration, the shared stylesheet, navigation. All
content lives in app/pages/, and none of it computes statistics - every number
shown here came from the API.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Streamlit executes this file as a script, so the service root has to be on
# the path before the app package can be imported.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from ui.pages import analyze, methodology, overview, peeking, plan  # noqa: E402
from ui.theme import CSS, register_template  # noqa: E402

st.set_page_config(
    page_title="Experiment referee",
    page_icon="🅰",
    layout="wide",
    initial_sidebar_state="expanded",
)

register_template()
st.markdown(CSS, unsafe_allow_html=True)

PAGES = [
    st.Page(overview.render, title="Overview", icon=":material/home:", default=True),
    st.Page(analyze.render, title="Analyse", icon=":material/analytics:"),
    st.Page(plan.render, title="Plan", icon=":material/calculate:"),
    st.Page(peeking.render, title="Peeking", icon=":material/visibility:"),
    st.Page(methodology.render, title="Methodology", icon=":material/menu_book:"),
]

with st.sidebar:
    st.markdown("### Experiment referee")
    st.caption("Plan an experiment before it runs, and judge it honestly once it is over.")

st.navigation(PAGES).run()
