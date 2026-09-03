"""Design tokens and the shared Plotly template.

The same palette the printed report uses, so a chart on screen and the same
chart in a downloaded report are recognisably one system. Colour identity is
fixed to the variant - control is always blue, treatment always orange - and
never to which one happened to win.

Values are taken verbatim from the validated reference palette: categorical
slots one and two, the fixed status colours, and the chart chrome inks.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# Categorical identity
CONTROL = "#2a78d6"
TREATMENT = "#eb6834"

# Status, reserved: never reused as a series colour
GOOD = "#0ca30c"
WARNING = "#fab219"
CRITICAL = "#d03b3b"

# Chrome and ink
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

FONT = "Segoe UI, system-ui, -apple-system, sans-serif"

#: Verdict to colour. Grey for "no detectable effect" is deliberate: a flat
#: result is not a failure, and colouring it as one would mislead.
VERDICT_COLOURS = {"win": GOOD, "regression": CRITICAL, "flat": MUTED}


def register_template() -> None:
    """Register and select the project's Plotly template."""
    template = go.layout.Template()
    template.layout = go.Layout(
        font={"family": FONT, "size": 13, "color": INK},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=[CONTROL, TREATMENT],
        margin={"l": 60, "r": 30, "t": 50, "b": 50},
        xaxis={
            "gridcolor": GRID,
            "linecolor": AXIS,
            "zerolinecolor": AXIS,
            "tickfont": {"color": INK_SECONDARY},
            "title": {"font": {"color": INK_SECONDARY, "size": 12}},
        },
        yaxis={
            "gridcolor": GRID,
            "linecolor": AXIS,
            "zerolinecolor": AXIS,
            "tickfont": {"color": INK_SECONDARY},
            "title": {"font": {"color": INK_SECONDARY, "size": 12}},
        },
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hoverlabel={"font": {"family": FONT, "size": 12}, "bgcolor": SURFACE},
        title={"font": {"size": 15, "color": INK}, "x": 0, "xanchor": "left"},
    )
    pio.templates["abtest"] = template
    pio.templates.default = "abtest"


CSS = f"""
<style>
  .stApp {{ background: {PAGE}; }}
  .block-container {{ padding-top: 2.2rem; max-width: 1100px; }}
  .banner {{
    background: {SURFACE}; border: 1px solid rgba(11,11,11,.10);
    border-left: 4px solid var(--accent, {MUTED});
    border-radius: 10px; padding: 16px 20px; margin: 8px 0 20px;
  }}
  .banner .verdict {{ font-size: 20px; font-weight: 650; margin-bottom: 4px; }}
  .banner .reason {{ color: {INK_SECONDARY}; font-size: 14px; }}
  .tag {{
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 11.5px; font-weight: 600;
  }}
  .tag-pass {{ background: rgba(12,163,12,.12); color: #006300; }}
  .tag-fail {{ background: rgba(208,59,59,.12); color: #a02020; }}
  .tag-warn {{ background: rgba(250,178,25,.18); color: #7a5300; }}
  .note {{ color: {INK_SECONDARY}; font-size: 13.5px; }}
  .step {{ font-size: 12px; letter-spacing: .06em; text-transform: uppercase;
           color: {MUTED}; margin-bottom: -6px; }}
</style>
"""
