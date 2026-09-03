"""Interactive figures, built from API responses.

Each function answers one question and does no computation beyond formatting -
every number here was produced by the API. Hover is the default on every
chart: a reader who wants the exact interval should not have to squint at an
axis.
"""

from __future__ import annotations

import plotly.graph_objects as go

from ui.theme import (
    AXIS,
    CONTROL,
    GOOD,
    INK_SECONDARY,
    MUTED,
    SURFACE,
    TREATMENT,
    VERDICT_COLOURS,
    WARNING,
)


def _empty(message: str) -> go.Figure:
    """A chart with nothing to draw still has to say why."""
    figure = go.Figure()
    figure.add_annotation(text=message, showarrow=False, font={"size": 13, "color": INK_SECONDARY})
    figure.update_layout(xaxis={"visible": False}, yaxis={"visible": False}, height=180)
    return figure


def lift_forest(metrics: list[dict]) -> go.Figure:
    """Relative change per metric with its confidence interval.

    The line at zero is the decision line: an interval crossing it is
    consistent with no effect, whatever the point estimate looks like.
    """
    plottable = [
        m
        for m in metrics
        if m.get("relative_diff") is not None
        and m.get("rel_ci_low") is not None
        and m.get("rel_ci_high") is not None
    ]
    if not plottable:
        return _empty("No metric has a relative interval to plot (every baseline is zero)")

    figure = go.Figure()
    for metric in reversed(plottable):
        colour = VERDICT_COLOURS.get(metric["verdict"], MUTED)
        low, high, point = metric["rel_ci_low"], metric["rel_ci_high"], metric["relative_diff"]
        label = f"{metric['metric']}<br><span style='font-size:11px'>{metric['role']}</span>"

        figure.add_trace(
            go.Scatter(
                x=[low, high],
                y=[label, label],
                mode="lines",
                line={"color": colour, "width": 3},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[point],
                y=[label],
                mode="markers",
                marker={
                    "color": colour,
                    "size": 13,
                    "line": {"color": SURFACE, "width": 2},
                },
                showlegend=False,
                customdata=[[metric["p_adjusted"], low, high, metric["verdict"]]],
                hovertemplate=(
                    "<b>%{y}</b><br>lift %{x:+.2%}<br>"
                    "95%% CI %{customdata[1]:+.2%} to %{customdata[2]:+.2%}<br>"
                    "adjusted p %{customdata[0]:.4f} - %{customdata[3]}<extra></extra>"
                ),
            )
        )

    figure.add_vline(x=0, line={"color": AXIS, "width": 1.5})
    figure.update_layout(
        height=120 + 70 * len(plottable),
        xaxis={"title": "Relative change vs control (95% CI)", "tickformat": "+.0%"},
        yaxis={"showgrid": False},
        showlegend=False,
    )
    return figure


def metric_levels(metrics: list[dict]) -> go.Figure:
    """Absolute level of each metric in both arms."""
    if not metrics:
        return _empty("No metrics to show")

    names = [m["metric"] for m in metrics]
    figure = go.Figure(
        [
            go.Bar(
                name="Control",
                x=names,
                y=[m["control"] for m in metrics],
                marker_color=CONTROL,
                hovertemplate="Control %{x}: %{y:.4g}<extra></extra>",
            ),
            go.Bar(
                name="Treatment",
                x=names,
                y=[m["treatment"] for m in metrics],
                marker_color=TREATMENT,
                hovertemplate="Treatment %{x}: %{y:.4g}<extra></extra>",
            ),
        ]
    )
    figure.update_layout(
        barmode="group",
        bargap=0.35,
        bargroupgap=0.06,
        height=380,
        yaxis={"title": "Metric value"},
        xaxis={"showgrid": False},
    )
    return figure


def power_curve(
    points: list[dict],
    target_power: float = 0.80,
    mde_relative: float | None = None,
    observed_effect: float | None = None,
) -> go.Figure:
    """Detection probability as a function of the true effect."""
    usable = [p for p in points if p.get("power") is not None]
    if not usable:
        return _empty("No power could be computed for this range of effects")

    figure = go.Figure(
        go.Scatter(
            x=[p["effect_relative"] for p in usable],
            y=[p["power"] for p in usable],
            mode="lines",
            line={"color": CONTROL, "width": 3},
            hovertemplate="effect %{x:+.1%} -> %{y:.0%} chance of detecting<extra></extra>",
            showlegend=False,
        )
    )
    figure.add_hline(
        y=target_power,
        line={"color": MUTED, "width": 1, "dash": "dash"},
        annotation_text=f"target power {target_power:.0%}",
        annotation_position="top left",
        annotation_font={"size": 11, "color": MUTED},
    )
    if mde_relative is not None:
        figure.add_vline(
            x=mde_relative,
            line={"color": TREATMENT, "width": 2},
            annotation_text=f"MDE {mde_relative:+.1%}",
            annotation_position="bottom right",
            annotation_font={"size": 11, "color": TREATMENT},
        )
    if observed_effect is not None:
        figure.add_vline(
            x=abs(observed_effect),
            line={"color": INK_SECONDARY, "width": 1.5, "dash": "dot"},
            annotation_text=f"observed {observed_effect:+.2%}",
            annotation_position="top right",
            annotation_font={"size": 11, "color": INK_SECONDARY},
        )
    figure.update_layout(
        height=400,
        xaxis={"title": "True relative effect", "tickformat": ".0%"},
        yaxis={"title": "Probability of detecting it", "tickformat": ".0%", "range": [0, 1.02]},
    )
    return figure


def sequential_boundary(looks: list[dict]) -> go.Figure:
    """Observed z-score at each look against the alpha-spending boundary."""
    if not looks:
        return _empty("Add at least one look")

    fractions = [look["information_fraction"] for look in looks]
    critical = [look["z_critical"] for look in looks]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=fractions,
            y=critical,
            mode="lines",
            line={"color": MUTED, "width": 2, "dash": "dash"},
            name="Sequential boundary",
            hovertemplate="at %{x:.0%} of the sample, stop only beyond z=%{y:.2f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=fractions,
            y=[-c for c in critical],
            mode="lines",
            line={"color": MUTED, "width": 2, "dash": "dash"},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    for value in (1.96, -1.96):
        figure.add_hline(y=value, line={"color": AXIS, "width": 1.5})

    figure.add_trace(
        go.Scatter(
            x=fractions,
            y=[look["z_score"] for look in looks],
            mode="lines+markers",
            line={"color": CONTROL, "width": 3},
            marker={"size": 11, "line": {"color": SURFACE, "width": 2}},
            name="Observed z",
            customdata=[
                [look["label"], look["p_value_fixed"], look["p_threshold_sequential"]]
                for look in looks
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>z %{y:.2f}<br>"
                "fixed-horizon p %{customdata[1]:.4f}<br>"
                "sequential threshold %{customdata[2]:.4f}<extra></extra>"
            ),
        )
    )

    premature = [look for look in looks if look["stop_naive"] and not look["stop_sequential"]]
    if premature:
        figure.add_trace(
            go.Scatter(
                x=[look["information_fraction"] for look in premature],
                y=[look["z_score"] for look in premature],
                mode="markers",
                marker={
                    "size": 22,
                    "color": "rgba(0,0,0,0)",
                    "line": {"color": WARNING, "width": 2},
                },
                name="A daily check would have stopped here",
                hovertemplate="A fixed 0.05 threshold would have called this look<extra></extra>",
            )
        )

    figure.update_layout(
        height=430,
        xaxis={"title": "Share of the planned sample collected", "tickformat": ".0%"},
        yaxis={"title": "z-score"},
    )
    return figure


def segment_forest(segments: list[dict], metric: str) -> go.Figure:
    """Per-segment relative change for one metric, after correction."""
    rows = [s for s in segments if s["metric"] == metric and s.get("relative_diff") is not None]
    if not rows:
        return _empty(f"No segment results for {metric}")

    figure = go.Figure()
    for row in reversed(rows):
        colour = (
            GOOD
            if row["significant"] and row["relative_diff"] > 0
            else (VERDICT_COLOURS["regression"] if row["significant"] else MUTED)
        )
        label = f"{row['dimension']} = {row['segment']}"
        figure.add_trace(
            go.Scatter(
                x=[row["relative_diff"]],
                y=[label],
                mode="markers",
                marker={"color": colour, "size": 12, "line": {"color": SURFACE, "width": 2}},
                showlegend=False,
                customdata=[[row["p_adjusted"], row["n_control"], row["n_treatment"]]],
                hovertemplate=(
                    "<b>%{y}</b><br>lift %{x:+.2%}<br>"
                    "adjusted p %{customdata[0]:.4f}<br>"
                    "n %{customdata[1]:,} / %{customdata[2]:,}<extra></extra>"
                ),
            )
        )
    figure.add_vline(x=0, line={"color": AXIS, "width": 1.5})
    figure.update_layout(
        height=120 + 42 * len(rows),
        xaxis={"title": "Relative change vs control", "tickformat": "+.0%"},
        yaxis={"showgrid": False},
        showlegend=False,
    )
    return figure
