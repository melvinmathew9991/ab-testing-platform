"""Analyse an experiment: upload, map columns, define metrics, decide.

The page is a sequence because the decisions are: you cannot choose metrics
before you know the columns, and you should not read results before the trust
checks pass. Each step keeps its state so a change late in the flow does not
force the file to be uploaded again.
"""

from __future__ import annotations

import streamlit as st

from ui import charts, components
from ui.api_client import ApiError
from ui.components import (
    api_status,
    blocking_warning,
    checks_table,
    decision_banner,
    metrics_table,
    show_api_error,
)
from ui.config import get_settings

_STATE_FILE = "analyze_file"
_STATE_INSPECT = "analyze_inspection"
_STATE_RESULTS = "analyze_results"
_STATE_CONFIG = "analyze_config"


def _reset_downstream() -> None:
    """A new file invalidates everything derived from the previous one."""
    for key in (_STATE_INSPECT, _STATE_RESULTS, _STATE_CONFIG):
        st.session_state.pop(key, None)


def _source_step(client) -> tuple[str | None, tuple[str, bytes] | None, dict | None]:
    """Choose a bundled dataset or upload a file. Returns the chosen source."""
    st.markdown('<p class="step">Step 1</p>', unsafe_allow_html=True)
    st.subheader("Choose the data")

    try:
        datasets = client.datasets()
    except ApiError as error:
        show_api_error(error)
        return None, None, None

    options = ["Upload a file"] + [d["name"] for d in datasets]
    choice = st.radio("Source", options, horizontal=True, label_visibility="collapsed")

    if choice != "Upload a file":
        dataset = next(d for d in datasets if d["name"] == choice)
        st.caption(f"{dataset['description']} ({dataset['n_rows']:,} rows)")
        return dataset["id"], None, dataset

    settings = get_settings()
    uploaded = st.file_uploader(
        f"One row per unit, CSV or Parquet, up to {settings.max_upload_mb:g} MB",
        type=["csv", "parquet"],
        on_change=_reset_downstream,
    )
    if uploaded is None:
        st.info("Upload a file, or pick the bundled dataset to see the tool working.")
        return None, None, None

    content = uploaded.getvalue()
    size_mb = len(content) / 1024 / 1024
    if size_mb > settings.max_upload_mb:
        st.error(
            f"That file is {size_mb:.1f} MB; the limit is {settings.max_upload_mb:g} MB. "
            "Aggregate to one row per unit, or sample it first."
        )
        return None, None, None

    st.session_state[_STATE_FILE] = (uploaded.name, content)
    return None, (uploaded.name, content), None


def _mapping_step(client, file, dataset) -> dict | None:
    """Map the columns. Suggestions come from the API's profile of the data."""
    st.markdown('<p class="step">Step 2</p>', unsafe_allow_html=True)
    st.subheader("Map the columns")

    if dataset is not None:
        st.caption(
            f"Unit `{dataset['unit_col']}`, variant `{dataset['variant_col']}`, "
            f"comparing `{dataset['variants'][0]}` against `{dataset['variants'][1]}`."
        )
        return {"columns": None, "dataset": dataset}

    if _STATE_INSPECT not in st.session_state:
        with st.spinner("Reading the file..."):
            try:
                st.session_state[_STATE_INSPECT] = client.inspect(file[0], file[1])
            except ApiError as error:
                show_api_error(error)
                return None

    inspection = st.session_state[_STATE_INSPECT]
    names = [c["name"] for c in inspection["columns"]]
    st.caption(f"{inspection['n_rows']:,} rows, {inspection['n_columns']} columns")

    left, right = st.columns(2)
    unit_col = left.selectbox(
        "Unit column",
        names,
        index=names.index(inspection["suggested_unit_col"])
        if inspection.get("suggested_unit_col") in names
        else 0,
        help="One row per unit. Usually a user or account id.",
    )
    variant_col = right.selectbox(
        "Variant column",
        names,
        index=names.index(inspection["suggested_variant_col"])
        if inspection.get("suggested_variant_col") in names
        else 0,
        help="The column holding the assignment.",
    )

    column = next(c for c in inspection["columns"] if c["name"] == variant_col)
    values = column["sample_values"]
    if len(values) < 2:
        st.error(
            f"`{variant_col}` has fewer than two values in the sample. "
            "Pick the column holding the variant assignment."
        )
        return None

    left, right = st.columns(2)
    control = left.selectbox("Control value", values, index=0)
    treatment = right.selectbox("Treatment value", [v for v in values if v != control], index=0)
    return {"columns": (unit_col, variant_col, control, treatment), "inspection": inspection}


def _metrics_step(mapping, dataset) -> list[dict] | None:
    """Define what is being measured, and which metrics decide the launch."""
    st.markdown('<p class="step">Step 3</p>', unsafe_allow_html=True)
    st.subheader("Define the metrics")

    if dataset is not None:
        st.caption("Using the definition this dataset ships with.")
        with st.expander("Metric definitions"):
            st.dataframe(dataset["metrics"], hide_index=True, width="stretch")
        return dataset["metrics"]

    inspection = mapping["inspection"]
    unit_col, variant_col = mapping["columns"][0], mapping["columns"][1]
    candidates = [c for c in inspection["columns"] if c["name"] not in (unit_col, variant_col)]
    if not candidates:
        st.error("No columns left to measure once the unit and variant are taken.")
        return None

    default = candidates[0]["name"]
    chosen = st.multiselect(
        "Metric columns",
        [c["name"] for c in candidates],
        default=[default],
        help="Each becomes one metric. Binary columns are detected automatically.",
    )
    if not chosen:
        st.info("Choose at least one metric column.")
        return None

    metrics = []
    for name in chosen:
        column = next(c for c in candidates if c["name"] == name)
        with st.expander(f"`{name}`", expanded=len(chosen) == 1):
            columns = st.columns(4)
            metric_type = columns[0].selectbox(
                "Type",
                ["binary", "continuous"],
                index=0 if column["binary_candidate"] else 1,
                key=f"type_{name}",
            )
            role = columns[1].selectbox(
                "Role", ["primary", "secondary", "guardrail"], key=f"role_{name}"
            )
            direction = columns[2].selectbox(
                "Better when it",
                ["increase", "decrease"],
                key=f"dir_{name}",
                help="A guardrail moving the wrong way is reported as a regression.",
            )
            winsorize = None
            if metric_type == "continuous":
                cap = columns[3].checkbox(
                    "Cap at p99",
                    value=True,
                    key=f"cap_{name}",
                    help="Stops a handful of extreme units driving the mean. "
                    "The cap is computed on both arms together.",
                )
                winsorize = 0.99 if cap else None

            metrics.append(
                {
                    "name": name,
                    "column": name,
                    "type": metric_type,
                    "direction": direction,
                    "primary": role == "primary",
                    "guardrail": role == "guardrail",
                    "winsorize_quantile": winsorize,
                }
            )

    if not any(m["primary"] for m in metrics):
        st.warning(
            "No primary metric selected. Without one there is nothing for the "
            "recommendation to be based on."
        )
    return metrics


def _options_step(mapping, dataset) -> dict:
    """Thresholds and extras. Defaults are the ones the tool argues for."""
    st.markdown('<p class="step">Step 4</p>', unsafe_allow_html=True)
    st.subheader("Options")

    columns = st.columns(4)
    alpha = columns[0].select_slider("Significance level", [0.01, 0.05, 0.10], value=0.05)
    correction = columns[1].selectbox(
        "Multiple testing",
        ["bh", "bonferroni", "none"],
        format_func={
            "bh": "Benjamini-Hochberg",
            "bonferroni": "Bonferroni",
            "none": "None",
        }.get,
        help="Testing several metrics at once inflates the false positive rate.",
    )
    resample = columns[2].checkbox(
        "Resampling",
        value=False,
        help="Adds bootstrap intervals and permutation tests for continuous "
        "metrics. Slower, and the honest choice when a metric is heavy-tailed.",
    )

    segment_by: list[str] = []
    if dataset is None and mapping.get("inspection"):
        unit_col, variant_col = mapping["columns"][0], mapping["columns"][1]
        options = [
            c["name"]
            for c in mapping["inspection"]["columns"]
            if c["name"] not in (unit_col, variant_col) and 2 <= c["n_unique"] <= 20
        ]
        segment_by = columns[3].multiselect(
            "Segment by",
            options,
            help="Pre-assignment attributes only. Splitting on something the "
            "treatment changed compares groups the treatment helped define.",
        )
    return {
        "alpha": alpha,
        "multiple_testing": correction,
        "resample": resample,
        "segment_by": segment_by,
    }


def _build_config(name, mapping, metrics, options, dataset) -> dict:
    if dataset is not None:
        unit_col = dataset["unit_col"]
        variant_col = dataset["variant_col"]
        control, treatment = dataset["variants"][0], dataset["variants"][1]
    else:
        unit_col, variant_col, control, treatment = mapping["columns"]

    return {
        "name": name,
        "unit_col": unit_col,
        "variant_col": variant_col,
        "control": control,
        "treatment": treatment,
        "metrics": metrics,
        "alpha": options["alpha"],
        "multiple_testing": options["multiple_testing"],
        "n_permutations": 2000,
        "n_bootstrap": 2000,
    }


def _render_results(results: dict, config: dict, dataset_id, file, resample) -> None:
    st.divider()
    st.subheader("Results")

    if results.get("blocking_failures"):
        blocking_warning(results["blocking_failures"])
    decision_banner(results["decision"])

    tabs = st.tabs(["Metrics", "Trust checks", "Segments", "Report"])
    with tabs[0]:
        st.plotly_chart(charts.lift_forest(results["metrics"]), width="stretch")
        metrics_table(results["metrics"])
        primary = [m for m in results["metrics"] if m["role"] == "primary"]
        if primary:
            st.plotly_chart(charts.metric_levels(primary), width="stretch")

        resampled = [m for m in results["metrics"] if m.get("permutation_p_value")]
        for metric in resampled:
            st.caption(
                f"`{metric['metric']}`: permutation p = {metric['permutation_p_value']:.4f} "
                f"against the t-test's {metric['p_value']:.4f}; bootstrap interval "
                f"{metric['bootstrap_ci_low']:+.4g} to {metric['bootstrap_ci_high']:+.4g}."
            )

    with tabs[1]:
        checks_table(results["checks"])

    with tabs[2]:
        segments = results.get("segments") or []
        if not segments:
            st.info(
                "No segment breakdown was requested. Segment results are exploratory: "
                "their p-values are corrected across every slice inspected."
            )
        else:
            metric_names = sorted({s["metric"] for s in segments})
            chosen = st.selectbox("Metric", metric_names)
            st.plotly_chart(charts.segment_forest(segments, chosen), width="stretch")

    with tabs[3]:
        st.markdown(
            '<p class="note">A single self-contained HTML file with the figures '
            "embedded - attachable to a ticket without breaking.</p>",
            unsafe_allow_html=True,
        )
        if st.button("Build the report"):
            with st.spinner("Rendering..."):
                try:
                    html = components.get_client().report(
                        config, dataset_id=dataset_id, file=file, resample=resample
                    )
                except ApiError as error:
                    show_api_error(error)
                else:
                    st.download_button(
                        "Download report",
                        data=html,
                        file_name=f"{config['name'][:50].replace(' ', '_')}_report.html",
                        mime="text/html",
                    )


def render() -> None:
    st.title("Analyse an experiment")
    if not api_status():
        return

    client = components.get_client()
    dataset_id, file, dataset = _source_step(client)
    if dataset_id is None and file is None:
        return

    mapping = _mapping_step(client, file, dataset)
    if mapping is None:
        return

    metrics = _metrics_step(mapping, dataset)
    if not metrics:
        return

    options = _options_step(mapping, dataset)

    st.divider()
    name = st.text_input(
        "Experiment name",
        value=dataset["name"] if dataset else "Untitled experiment",
        max_chars=200,
    )
    config = _build_config(name, mapping, metrics, options, dataset)

    left, right = st.columns([1, 3])
    if left.button("Check the data", width="stretch"):
        with st.spinner("Running trust checks..."):
            try:
                validation = client.validate(config, dataset_id=dataset_id, file=file)
            except ApiError as error:
                show_api_error(error)
            else:
                if validation["usable"]:
                    st.success("The data passes every critical check.")
                else:
                    st.error("A critical check failed. Results from this data cannot be used.")
                checks_table(validation["checks"])
                for issue in validation["issues"]:
                    st.warning(issue)

    if right.button("Analyse", type="primary", width="stretch"):
        with st.spinner("Analysing..."):
            try:
                st.session_state[_STATE_RESULTS] = client.analyze(
                    config,
                    dataset_id=dataset_id,
                    file=file,
                    resample=options["resample"],
                    segment_by=options["segment_by"],
                )
                st.session_state[_STATE_CONFIG] = config
            except ApiError as error:
                show_api_error(error)

    if st.session_state.get(_STATE_RESULTS):
        _render_results(
            st.session_state[_STATE_RESULTS],
            st.session_state.get(_STATE_CONFIG, config),
            dataset_id,
            file,
            options["resample"],
        )
