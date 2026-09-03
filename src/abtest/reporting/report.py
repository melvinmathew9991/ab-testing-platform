"""Turn an analysed experiment into a self-contained report.

The HTML report embeds its figures, so a single file can be attached to a
ticket or emailed without breaking. The Markdown report is for pull requests
and READMEs.
"""

from __future__ import annotations

import base64
import os
from html import escape

import numpy as np
import pandas as pd

from abtest.experiment import ExperimentResults
from abtest.log import get_logger

logger = get_logger(__name__)

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin:0; background:#f9f9f7; color:#0b0b0b;
  font:15px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif; }
.wrap { max-width: 940px; margin: 0 auto; padding: 40px 24px 72px; }
h1 { font-size: 28px; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 18px; margin: 40px 0 12px; letter-spacing: -0.005em; }
h3 { font-size: 14px; margin: 24px 0 8px; color:#52514e; text-transform: uppercase;
  letter-spacing: .06em; }
p  { margin: 8px 0; }
.sub { color:#52514e; margin: 0 0 24px; }
.card { background:#fcfcfb; border:1px solid rgba(11,11,11,.10); border-radius:10px;
  padding:18px 20px; margin: 16px 0; }
.banner { border-left: 4px solid var(--accent,#898781); }
.banner .verdict { font-size: 20px; font-weight: 650; margin-bottom: 4px; }
.kpis { display:flex; flex-wrap:wrap; gap:12px; margin: 16px 0; }
.kpi { flex:1 1 150px; background:#fcfcfb; border:1px solid rgba(11,11,11,.10);
  border-radius:10px; padding:14px 16px; }
.kpi .label { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:#898781; }
.kpi .value { font-size:22px; font-weight:650; margin-top:4px; letter-spacing:-0.01em; }
.kpi .note { font-size:12px; color:#52514e; margin-top:2px; }
table { border-collapse: collapse; width:100%; font-size:13.5px; background:#fcfcfb; }
.scroll { overflow-x:auto; border:1px solid rgba(11,11,11,.10); border-radius:10px; }
th { text-align:left; font-weight:600; color:#52514e; font-size:12px;
  text-transform:uppercase; letter-spacing:.04em; padding:10px 12px;
  border-bottom:1px solid #e1e0d9; white-space:nowrap; }
td { padding:9px 12px; border-bottom:1px solid #e1e0d9; white-space:nowrap; }
tr:last-child td { border-bottom:none; }
td.num { text-align:right; font-variant-numeric: tabular-nums; }
.tag { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11.5px;
  font-weight:600; }
.win  { background:rgba(12,163,12,.12); color:#006300; }
.bad  { background:rgba(208,59,59,.12); color:#a02020; }
.flat { background:rgba(137,135,129,.15); color:#52514e; }
.warn { background:rgba(250,178,25,.18); color:#7a5300; }
figure { margin: 20px 0; }
figure img { width:100%; border:1px solid rgba(11,11,11,.10); border-radius:10px; display:block; }
figcaption { font-size:12.5px; color:#52514e; margin-top:8px; }
footer { margin-top:48px; color:#898781; font-size:12.5px;
  border-top:1px solid #e1e0d9; padding-top:16px; }
code { background:#f0efec; padding:1px 5px; border-radius:4px; font-size:12.5px; }
"""

_ACCENT = {
    "ship": "#0ca30c",
    "do not ship": "#d03b3b",
    "do not ship (no evidence of improvement)": "#898781",
    "do not use this result": "#d03b3b",
}


def _img_tag(path: str) -> str:
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f'<img alt="" src="data:image/png;base64,{b64}">'


def _fmt(value, kind: str = "auto") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    if kind == "pct":
        return f"{value:+.2%}"
    if kind == "pct0":
        return f"{value:.2%}"
    if kind == "p":
        return f"{value:.4f}" if value >= 1e-4 else "<0.0001"
    if kind == "int":
        return f"{int(value):,}"
    if isinstance(value, float):
        return f"{value:,.4g}"
    return str(value)


def _metrics_table(summary: pd.DataFrame) -> str:
    head = (
        "<tr><th>Metric</th><th>Role</th><th>Control</th><th>Treatment</th>"
        "<th>Lift</th><th>95% CI</th><th>p (adj.)</th><th>Verdict</th></tr>"
    )
    rows = []
    for _, r in summary.iterrows():
        tag = {"win": "win", "regression": "bad"}.get(r["verdict"], "flat")
        rows.append(
            "<tr>"
            f"<td>{escape(str(r['metric']))}</td>"
            f"<td>{escape(str(r['role']))}</td>"
            f"<td class='num'>{_fmt(r['control'])}</td>"
            f"<td class='num'>{_fmt(r['treatment'])}</td>"
            f"<td class='num'>{_fmt(r['relative_diff'], 'pct')}</td>"
            f"<td class='num'>{_fmt(r['rel_ci_low'], 'pct')} to "
            f"{_fmt(r['rel_ci_high'], 'pct')}</td>"
            f"<td class='num'>{_fmt(r['p_adjusted'], 'p')}</td>"
            f"<td><span class='tag {tag}'>{escape(str(r['verdict']))}</span></td>"
            "</tr>"
        )
    return f"<div class='scroll'><table>{head}{''.join(rows)}</table></div>"


def _checks_table(checks: pd.DataFrame) -> str:
    head = "<tr><th>Check</th><th>Status</th><th>Detail</th></tr>"
    rows = []
    for _, r in checks.iterrows():
        cls = {"PASS": "win", "FAIL": "bad", "WARN": "warn"}[r["status"]]
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(r['check']))}</code></td>"
            f"<td><span class='tag {cls}'>{r['status']}</span></td>"
            f"<td style='white-space:normal'>{escape(str(r['message']))}</td>"
            "</tr>"
        )
    return f"<div class='scroll'><table>{head}{''.join(rows)}</table></div>"


def _frame_table(df: pd.DataFrame, pct_cols=("relative_diff", "control", "treatment")) -> str:
    head = "<tr>" + "".join(f"<th>{escape(str(c))}</th>" for c in df.columns) + "</tr>"
    rows = []
    for _, r in df.iterrows():
        cells = []
        for col in df.columns:
            v = r[col]
            if isinstance(v, (int, float, np.floating, np.integer)) and not isinstance(v, bool):
                kind = "pct" if col == "relative_diff" else ("p" if "p_" in str(col) else "auto")
                cells.append(f"<td class='num'>{_fmt(float(v), kind)}</td>")
            else:
                cells.append(f"<td>{escape(str(v))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class='scroll'><table>{head}{''.join(rows)}</table></div>"


def build_html_report(
    results: ExperimentResults,
    figures: list[tuple[str, str]] | None = None,
    output_path: str = "reports/experiment_report.html",
    narrative: dict[str, str] | None = None,
) -> str:
    """Write a standalone HTML report.

    Args:
        figures: ``(caption, png_path)`` pairs, embedded in order.
        narrative: Optional extra prose sections, ``{heading: html}``.
    """
    cfg = results.config
    summary = results.summary()
    decision = results.decision()
    accent = _ACCENT.get(decision["recommendation"], "#898781")

    primary = [o for o in results.outcomes if o.spec.primary] or results.outcomes
    p0 = primary[0]

    kpis = [
        (
            "Units analysed",
            f"{sum(results.counts.values()):,}",
            " / ".join(f"{k} {v:,}" for k, v in results.counts.items()),
        ),
        (f"{p0.spec.name} (control)", _fmt(p0.test.mean_control, "pct0"), "baseline"),
        (
            "Observed lift",
            _fmt(p0.test.relative_diff, "pct"),
            f"95% CI {_fmt(p0.test.relative_ci[0], 'pct')} to "
            f"{_fmt(p0.test.relative_ci[1], 'pct')}",
        ),
        (
            "Smallest detectable lift",
            _fmt(p0.test.mde_absolute / p0.test.mean_control, "pct0")
            if p0.test.mean_control
            else "-",
            f"at {cfg.power:.0%} power, alpha {cfg.alpha}",
        ),
    ]
    kpi_html = "".join(
        f"<div class='kpi'><div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(value)}</div>"
        f"<div class='note'>{escape(note)}</div></div>"
        for label, value, note in kpis
    )

    fig_html = ""
    for caption, path in figures or []:
        if path and os.path.exists(path):
            fig_html += (
                f"<figure>{_img_tag(path)}<figcaption>{escape(caption)}</figcaption></figure>"
            )

    extra = ""
    for heading, html in (narrative or {}).items():
        extra += f"<h2>{escape(heading)}</h2>{html}"

    segments_html = ""
    if results.segments is not None and not results.segments.empty:
        cols = [
            "dimension",
            "segment",
            "metric",
            "n_control",
            "n_treatment",
            "relative_diff",
            "p_value",
            "p_adjusted",
            "significant",
        ]
        segments_html = (
            "<h2>Segments</h2>"
            "<p class='sub'>Exploratory only. Every segment test below is part of one "
            "Benjamini-Hochberg family, so the corrected p-value already accounts for "
            "how many slices were inspected.</p>" + _frame_table(results.segments[cols])
        )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(cfg.name)} - experiment report</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>{escape(cfg.name)}</h1>
<p class="sub">{escape((cfg.hypothesis or "Experiment analysis").strip())}
&middot; generated {escape(results.run_at)}</p>

<div class="card banner" style="--accent:{accent}">
  <div class="verdict">Recommendation: {escape(decision["recommendation"])}</div>
  <div>{escape(decision["reason"])}</div>
</div>

<div class="kpis">{kpi_html}</div>

<h2>Results</h2>
{_metrics_table(summary)}
<p class="sub">Lift is treatment vs control. p-values are corrected across
{len(summary)} metrics using {escape(cfg.multiple_testing.upper())}; a metric counts as
moved only after correction.</p>

<h2>Trust checks</h2>
{_checks_table(results.checks_frame())}

{segments_html}

<h2>Figures</h2>
{fig_html}

{extra}

<footer>
Generated by the <code>abtest</code> toolkit &middot; alpha {cfg.alpha}, power {cfg.power:.0%},
seed {cfg.seed} &middot; every number here is reproducible from
<code>analysis/run_cookie_cats.py</code>.
</footer>
</div></body></html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)
    except OSError as exc:
        logger.error("Could not write HTML report to %s: %s", output_path, exc)
        raise
    logger.info("Wrote HTML report to %s (%d figures)", output_path, len(figures or []))
    return output_path


def build_markdown_report(results: ExperimentResults, output_path: str | None = None) -> str:
    """Compact Markdown summary, suitable for a PR description or README."""
    cfg = results.config
    decision = results.decision()
    summary = results.summary()

    lines = [
        f"# {cfg.name}",
        "",
        f"_{cfg.hypothesis.strip()}_" if cfg.hypothesis else "",
        "",
        f"**Recommendation: {decision['recommendation']}** ({decision['confidence']} confidence)  ",
        f"{decision['reason']}",
        "",
        "## Results",
        "",
        "| Metric | Role | Control | Treatment | Lift | 95% CI | p (adj.) | Verdict |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['metric']} | {r['role']} | {_fmt(r['control'])} | {_fmt(r['treatment'])} | "
            f"{_fmt(r['relative_diff'], 'pct')} | {_fmt(r['rel_ci_low'], 'pct')} to "
            f"{_fmt(r['rel_ci_high'], 'pct')} | {_fmt(r['p_adjusted'], 'p')} | {r['verdict']} |"
        )

    lines += ["", "## Trust checks", ""]
    for _, c in results.checks_frame().iterrows():
        lines.append(f"- **{c['status']}** `{c['check']}` - {c['message']}")

    text = "\n".join(lines) + "\n"
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text
