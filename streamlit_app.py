"""Streamlit viewer for pipeline monitoring and ground-truth validation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import httpx
import plotly.graph_objects as go
import streamlit as st
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
)

from customer_data_product.settings import get_settings

QUALITY_THRESHOLDS = {
    "quarantine": 0.05,
    "duplicates": 0.05,
    "referential": 0.0,
    "completeness": 0.99,
}
PLOT_CONFIG = {"displayModeBar": False}
APP_SETTINGS = get_settings()


def find_raw_root() -> Path:
    configured = APP_SETTINGS.raw_root
    return configured if configured.is_dir() else Path("dev_raw")


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return cast(dict[str, Any], json.load(file))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_ground_truth(raw_root: Path) -> dict[str, Any]:
    metadata = raw_root / "metadata"
    return {
        "manifest": read_json(metadata / "manifest.json"),
        "quality": read_json(metadata / "quality_ground_truth.json"),
        "sources": read_json(metadata / "source_systems.json"),
        "scenarios": read_jsonl(raw_root / "ground_truth" / "scenario_labels.jsonl"),
    }


def backend_get(path: str) -> tuple[Any | None, str | None]:
    backend_url = APP_SETTINGS.backend_url.rstrip("/")
    api_key = APP_SETTINGS.backend_api_key or APP_SETTINGS.api_key
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        response = httpx.get(f"{backend_url}{path}", headers=headers, timeout=5)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as error:
        return None, str(error)


def format_event_freshness(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    future = seconds < 0
    remaining = int(abs(seconds))
    days, remaining = divmod(remaining, 86_400)
    hours, remaining = divmod(remaining, 3_600)
    minutes, remaining_seconds = divmod(remaining, 60)
    parts: list[str] = []
    for value, unit in (
        (days, "d"),
        (hours, "h"),
        (minutes, "m"),
        (remaining_seconds, "s"),
    ):
        if value or not parts:
            parts.append(f"{value}{unit}")
    age = " ".join(parts)
    return f"FUTURE +{age}" if future else f"{age} old"


def render_entity_counts(
    values: dict[str, int | None],
    *,
    title: str,
    primary_label: str = "ground truth",
    comparison: dict[str, int | None] | None = None,
    comparison_label: str = "comparison",
) -> None:
    """Show the shared entity counts used for production/GT comparison."""
    labels = list(values)
    figure = go.Figure()
    for name, source, color in [
        (primary_label, values, "#4C78A8"),
        (comparison_label, comparison, "#D9E2F3"),
    ]:
        if source is None:
            continue
        bar_values = [source.get(label) for label in labels]
        figure.add_bar(
            name=name,
            x=labels,
            y=bar_values,
            text=["—" if value is None else f"{value:,}" for value in bar_values],
            textposition="auto",
            marker_color=color,
        )
    if comparison is not None:
        figure.update_layout(barmode="group")
    figure.update_layout(
        title=title,
        height=320,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        yaxis={"title": "records"},
    )
    st.plotly_chart(figure, width="stretch", config=PLOT_CONFIG)


def render_production_dashboard() -> None:
    """Display live API and pipeline results, without ground-truth data."""
    st.caption("Live data from the API and the latest processed batch.")
    health, health_error = backend_get("/health")
    ready, ready_error = backend_get("/ready")
    summary, summary_error = backend_get("/v1/summary")
    quality, quality_error = backend_get("/v1/quality/summary")
    distributions, _ = backend_get("/v1/summary/distributions")

    status_top = st.columns(2)
    status_top[0].metric(
        "API health", "OK" if health and health.get("status") == "ok" else "DOWN"
    )
    status_top[1].metric(
        "Database", "READY" if ready and ready.get("status") == "ready" else "DOWN"
    )
    status_bottom = st.columns(2)
    status_bottom[0].metric(
        "Access control",
        "API key configured"
        if APP_SETTINGS.backend_api_key or APP_SETTINGS.api_key
        else "Not configured",
    )
    status_bottom[1].metric(
        "Batch status", quality.get("batch_status", "UNKNOWN") if quality else "UNKNOWN"
    )
    if health is None or ready is None:
        st.warning(
            "Live backend checks unavailable. "
            f"Health: {health_error or 'unknown'}; "
            f"Readiness: {ready_error or 'unknown'}"
        )
    if summary is None or quality is None:
        st.info(
            "Start the API and process a batch to populate production results. "
            f"{summary_error or quality_error or ''}"
        )
        return

    if quality.get("quality_status") == "PASSED":
        st.success("Quality gate passed for the latest batch.")
    else:
        reasons = quality.get("quality_failure_reasons", [])
        st.error("Quality gate failed: " + ", ".join(reasons or ["unknown reason"]))

    totals = st.columns(4)
    for column, label, key in zip(
        totals,
        [
            "Customers",
            "Accounts",
            "Transactions",
            "Interactions",
        ],
        [
            "customer_count",
            "account_count",
            "transaction_count",
            "interaction_count",
        ],
    ):
        column.metric(label, f"{summary[key]:,}")

    render_entity_counts(
        {
            "total records": quality["total_count"],
            "customers": summary["customer_count"],
            "accounts": summary["account_count"],
            "transactions": summary["transaction_count"],
            "interactions": summary["interaction_count"],
        },
        title="Production counts for GT comparison",
        primary_label="pipeline",
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Latest ingestion outcome")
        ingestion = {
            "accepted": quality["accepted_count"],
            "duplicates": quality["duplicate_count"],
            "quarantined": quality["quarantined_count"],
        }
        figure = go.Figure(
            go.Bar(
                x=list(ingestion),
                y=list(ingestion.values()),
                text=[f"{value:,}" for value in ingestion.values()],
                textposition="auto",
                marker_color=["#2E8B57", "#E09F3E", "#C94C4C"],
            )
        )
        figure.update_layout(height=300, margin={"l": 0, "r": 0, "t": 10, "b": 0})
        st.plotly_chart(figure, width="stretch", config=PLOT_CONFIG)
    with right:
        st.subheader("Quality gate vs thresholds")
        checks = {
            "quarantine": (
                quality["quarantine_rate"],
                QUALITY_THRESHOLDS["quarantine"],
            ),
            "duplicates": (
                quality["duplicate_rate"],
                QUALITY_THRESHOLDS["duplicates"],
            ),
            "referential": (
                quality["referential_integrity_failure_rate"],
                QUALITY_THRESHOLDS["referential"],
            ),
            "completeness": (
                quality["required_field_completeness"],
                QUALITY_THRESHOLDS["completeness"],
            ),
        }
        figure = go.Figure()
        figure.add_bar(
            name="observed",
            x=list(checks),
            y=[value * 100 for value, _ in checks.values()],
            text=[f"{value:.2%}" for value, _ in checks.values()],
            textposition="auto",
        )
        figure.add_bar(
            name="threshold",
            x=list(checks),
            y=[value * 100 for _, value in checks.values()],
            text=[f"{value:.2%}" for _, value in checks.values()],
            textposition="auto",
            marker_color="#D9E2F3",
        )
        figure.update_layout(
            barmode="group",
            height=300,
            margin={"l": 0, "r": 0, "t": 10, "b": 0},
            yaxis={"title": "percent", "ticksuffix": "%"},
        )
        st.plotly_chart(figure, width="stretch", config=PLOT_CONFIG)

    st.subheader("Freshness and processing")
    freshness_top = st.columns(3)
    freshness_top[0].metric("Batch ID", quality.get("batch_id") or "—")
    freshness_top[1].metric("Updated", quality.get("updated_at") or "—")
    freshness_top[2].metric(
        "Event freshness", format_event_freshness(quality.get("freshness_seconds"))
    )
    freshness_bottom = st.columns(3)
    freshness_bottom[0].metric(
        "Source event max", quality.get("source_event_max") or "—"
    )
    freshness_bottom[1].metric(
        "Duration",
        f"{quality['duration_seconds']:.1f}s"
        if quality.get("duration_seconds") is not None
        else "—",
    )
    freshness_bottom[2].metric(
        "Volume change",
        f"{quality['volume_change_rate']:.2%}"
        if quality.get("volume_change_rate") is not None
        else "—",
    )

    if distributions:
        left, right = st.columns(2)
        for column, title, key in [
            (left, "Customers by status", "customers_by_status"),
            (right, "Transactions by status", "transactions_by_status"),
        ]:
            with column:
                figure = go.Figure(
                    go.Bar(
                        x=[item["label"] for item in distributions[key]],
                        y=[item["count"] for item in distributions[key]],
                        text=[item["count"] for item in distributions[key]],
                        textposition="auto",
                    )
                )
                figure.update_layout(title=title, height=300)
                st.plotly_chart(figure, width="stretch", config=PLOT_CONFIG)

    with st.expander("Batch lineage"):
        batch_id = quality.get("batch_id")
        lineage, lineage_error = (
            backend_get(f"/v1/batches/{batch_id}/lineage")
            if batch_id
            else (None, "no latest batch")
        )
        if lineage:
            st.write(
                f"Source: `{lineage['source']}` · Status: `{lineage['status']}` · "
                f"Batch: `{lineage['batch_id']}`"
            )
            st.dataframe(lineage["files"], hide_index=True, width="stretch")
        else:
            st.info(f"Lineage unavailable: {lineage_error}")


def render_metric_table(
    values: dict[str, int | float],
    *,
    total: int | float | None = None,
    percent: bool = False,
    observed_total: int | None = None,
    observed_counts: dict[str, int | None] | None = None,
) -> None:
    rows = []
    denominator = 1.0 if percent else total
    if denominator is None:
        denominator = max((float(value) for value in values.values()), default=1.0)
    show_percentage = percent or total is not None
    for label, value in values.items():
        numeric = float(value)
        share = numeric / denominator if denominator else 0.0
        rows.append({
            "label": label,
            "value": f"{value:.2%}" if percent else value,
            "bar": share * 100 if show_percentage else share,
        })
        if observed_total is not None:
            rows[-1].pop("bar")
            rows[-1]["configured rate"] = rows[-1].pop("value")
        if percent and observed_counts is not None:
            observed = observed_counts.get(label)
            rows[-1]["ground-truth observed"] = (
                "—"
                if observed is None or observed_total is None
                else f"{observed:,}/{observed_total:,} "
                f"({observed / observed_total:.2%})"
            )
        if not percent and total is not None:
            rows[-1]["count / total"] = f"{value:g}/{total:g}"
    column_config = (
        {
            "bar": st.column_config.ProgressColumn(
                "distribution",
                min_value=0,
                max_value=100 if show_percentage else 1,
                format="%.2f%%" if show_percentage else "%g",
            )
        }
        if observed_total is None
        else {}
    )
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config=column_config,
    )


def render_found_vs_global(found: dict[str, int], global_cases: dict[str, int]) -> None:
    labels = list(found)
    found_percent = [
        found[label] / global_cases[label] * 100 if global_cases[label] else 0
        for label in labels
    ]
    global_percent = [100.0] * len(labels)
    found_text = [
        f"{found[label]:,}/{global_cases[label]:,} ({value:.2f}%)"
        for label, value in zip(labels, found_percent)
    ]
    figure = go.Figure([
        go.Bar(
            name="found",
            y=labels,
            x=found_percent,
            orientation="h",
            text=found_text,
            textposition="outside",
            marker_color="#4C78A8",
        ),
        go.Bar(
            name="global",
            y=labels,
            x=global_percent,
            orientation="h",
            text=[f"{global_cases[label]:,} (100%)" for label in labels],
            textposition="outside",
            marker_color="#D9E2F3",
        ),
    ])
    figure.update_layout(
        barmode="group",
        height=300,
        margin={"l": 0, "r": 0, "t": 10, "b": 10},
        xaxis={
            "title": "share of global cases",
            "range": [0, 110],
            "ticksuffix": "%",
        },
        yaxis={"title": None},
        legend={"orientation": "h", "y": 1.12},
    )
    st.plotly_chart(figure, width="stretch", config=PLOT_CONFIG)


def fraud_metrics(quality: dict[str, Any]) -> dict[str, float]:
    y_true, y_pred = fraud_labels(quality)

    return {
        "precision": precision_score(
            y_true, y_pred, pos_label="fraud", zero_division=0
        ),
        "recall": recall_score(y_true, y_pred, pos_label="fraud", zero_division=0),
        "f1_score": f1_score(y_true, y_pred, pos_label="fraud", zero_division=0),
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "specificity": recall_score(
            y_true, y_pred, pos_label="not_fraud", zero_division=0
        ),
        "matthews_corrcoef": matthews_corrcoef(y_true, y_pred),
    }


def fraud_labels(quality: dict[str, Any]) -> tuple[list[str], list[str]]:
    metrics = quality["classification_metrics"]
    misclassified = quality["misclassification"]
    supports = {
        label: int(metrics[label]["support"]) for label in ("fraud", "not_fraud")
    }
    missed_by_label = misclassified.get("misclassified_by_label", {})
    y_true: list[str] = []
    y_pred: list[str] = []
    for label, support in supports.items():
        misses = int(missed_by_label.get(label, 0))
        y_true.extend([label] * support)
        y_pred.extend(["not_fraud" if label == "fraud" else "fraud"] * misses)
        y_pred.extend([label] * (support - misses))
    return y_true, y_pred


def render_ground_truth_ingestion(quality: dict[str, Any]) -> None:
    st.subheader("Ground-truth ingestion outcome")
    reference = quality["dashboard_reference"]
    total = int(quality["total_count"])
    expected = {
        "accepted": total - int(quality["expected_quarantined_count"]),
        "duplicates": int(reference["duplicate_count"]),
        "quarantined": int(quality["expected_quarantined_count"]),
    }
    observed = {
        "accepted": int(reference["accepted_count"]),
        "duplicates": int(reference["duplicate_count"]),
        "quarantined": int(reference["quarantined_count"]),
    }
    figure = go.Figure()
    for name, values, color in [
        ("expected", expected, "#D9E2F3"),
        ("ground-truth observed", observed, "#4C78A8"),
    ]:
        figure.add_bar(
            name=name,
            x=list(values),
            y=list(values.values()),
            text=[f"{value:,}" for value in values.values()],
            textposition="auto",
            marker_color=color,
        )
    figure.update_layout(
        barmode="group",
        height=320,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        yaxis={"title": "records"},
    )
    st.plotly_chart(figure, width="stretch", config=PLOT_CONFIG)


def render_ground_truth_quality_gate(quality: dict[str, Any]) -> None:
    st.subheader("Ground-truth quality gate vs thresholds")
    total = int(quality["total_count"])
    reference = quality["dashboard_reference"]
    observed = {
        "quarantine rate": quality["expected_quarantined_count"] / total,
        "duplicate rate": reference["duplicate_count"] / total,
        "referential failures": quality["referential_integrity_failure_count"] / total,
        "field completeness": 1 - quality["required_field_failure_count"] / total,
    }
    thresholds = {
        "quarantine rate": QUALITY_THRESHOLDS["quarantine"],
        "duplicate rate": QUALITY_THRESHOLDS["duplicates"],
        "referential failures": QUALITY_THRESHOLDS["referential"],
        "field completeness": QUALITY_THRESHOLDS["completeness"],
    }
    figure = go.Figure()
    figure.add_bar(
        name="ground-truth observed",
        x=list(observed),
        y=[value * 100 for value in observed.values()],
        text=[f"{value:.2%}" for value in observed.values()],
        textposition="auto",
        marker_color="#4C78A8",
    )
    figure.add_bar(
        name="expected threshold",
        x=list(thresholds),
        y=[value * 100 for value in thresholds.values()],
        text=[f"{value:.2%}" for value in thresholds.values()],
        textposition="auto",
        marker_color="#D9E2F3",
    )
    figure.update_layout(
        barmode="group",
        height=320,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        yaxis={"title": "percent", "ticksuffix": "%"},
    )
    st.plotly_chart(figure, width="stretch", config=PLOT_CONFIG)


def render_overview(data: dict[str, Any]) -> None:
    manifest = data["manifest"]
    quality = data["quality"]
    st.subheader("Ground-truth overview")
    columns = st.columns(3)
    columns[0].metric("Logical records", f"{manifest['requested_logical_records']:,}")
    columns[1].metric("Customers", f"{manifest['customer_count']:,}")
    columns[2].metric("Records checked", f"{quality['total_count']:,}")

    failures = {
        "required field failures": quality["required_field_failure_count"],
        "invalid records": quality["invalid_record_count"],
        "referential integrity failures": quality[
            "referential_integrity_failure_count"
        ],
        "future events": quality["future_event_count"],
    }
    st.caption("Quality failure counts")
    render_metric_table(failures, total=quality["total_count"])


def render_distributions(data: dict[str, Any]) -> None:
    quality = data["quality"]
    st.subheader("Distributions")
    left, right = st.columns(2)
    with left:
        st.caption("Detected scenarios vs generated scenarios")
        global_scenarios = quality["all_generated_cases"]["scenario_counts"]
        found_scenarios = Counter(
            scenario.get("label", "unknown") for scenario in data["scenarios"]
        )
        scenario_labels = {
            "fraud": "fraud",
            "anomaly": "anomaly",
            "duplicate_payment": "duplicate",
        }
        render_found_vs_global(
            {
                scenario: found_scenarios.get(
                    scenario_labels.get(scenario, scenario), 0
                )
                for scenario in global_scenarios
            },
            global_scenarios,
        )
    with right:
        st.caption("Generator-injected issue rates — configuration, not results")
        st.info(
            "These rates control how often the generator injects each issue. They "
            "are stochastic inputs applied by source, record, or field; they are "
            "not exact global quotas. Ground-truth observed values come from the "
            "quality ground truth, not the live pipeline."
        )
        render_metric_table(
            data["manifest"]["quality_parameters"],
            percent=True,
            observed_total=quality["total_count"],
            observed_counts={
                "duplicate_rate": quality["dashboard_reference"]["duplicate_count"],
                "missing_rate": quality["required_field_failure_count"],
                "malformed_rate": quality["invalid_record_count"],
                "unknown_id_rate": quality["referential_integrity_failure_count"],
            },
        )


def render_sources(sources: dict[str, dict[str, Any]]) -> None:
    st.subheader("Source systems")
    rows = [
        {
            "source": name,
            "domain": details["domain"],
            "formats": ", ".join(details["format"]),
            "owner": details["owner"],
            "identifier": details["identifier"],
            "PII": details["contains_pii"],
            "SLA": details["expected_sla"],
        }
        for name, details in sources.items()
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def render_ground_truth_scenarios(data: dict[str, Any]) -> None:
    scenarios = data["scenarios"]
    st.subheader("Ground-truth scenarios")
    summary = st.columns(3)
    summary[0].metric("Total cases", f"{len(scenarios):,}")
    summary[1].metric(
        "Confirmed cases",
        f"{sum(bool(case.get('confirmed')) for case in scenarios):,}",
    )
    summary[2].metric(
        "Unconfirmed cases",
        f"{sum(not bool(case.get('confirmed')) for case in scenarios):,}",
    )

    labels = Counter(case.get("label", "unknown") for case in scenarios)
    subtypes = Counter(
        case.get("subtype", "unknown") or "unknown" for case in scenarios
    )
    st.dataframe(
        [{"label": label, "cases": count} for label, count in labels.items()],
        hide_index=True,
        width="stretch",
    )
    render_entity_counts(dict(subtypes), title="GT cases by subtype")

    with st.expander("Scenario labels"):
        st.dataframe(
            [
                {
                    "scenario_id": case.get("scenario_id"),
                    "label": case.get("label"),
                    "subtype": case.get("subtype"),
                    "confirmed": case.get("confirmed", False),
                }
                for case in scenarios
            ],
            hide_index=True,
            width="stretch",
        )


def render_fraud(quality: dict[str, Any]) -> None:
    st.subheader("Fraud detection ground truth")
    st.info(
        "This is a labelled evaluation set from the ground truth, not the live "
        "number of fraud events persisted by the production pipeline."
    )
    metrics = fraud_metrics(quality)
    st.caption(
        "Metrics are recomputed with scikit-learn from the labelled cases and "
        "misclassifications."
    )
    render_metric_table(metrics, percent=True)

    y_true, y_pred = fraud_labels(quality)
    matrix = confusion_matrix(y_true, y_pred, labels=["fraud", "not_fraud"])
    total = len(y_true)
    misclassified = quality["misclassification"]
    summary_rows = []
    for label in ["fraud", "not_fraud"]:
        actual = sum(value == label for value in y_true)
        predicted = sum(value == label for value in y_pred)
        summary_rows.append({
            "label": label,
            "ground_truth": f"{actual}/{total} ({actual / total:.2%})",
            "predicted": f"{predicted}/{total} ({predicted / total:.2%})",
            "misclassified": (
                f"{misclassified['misclassified_by_label'].get(label, 0)}/{total}"
            ),
            "false_positive": str(int(matrix[1, 0])) if label == "fraud" else "—",
            "false_negative": str(int(matrix[0, 1])) if label == "fraud" else "—",
        })
    total_misclassified = int(misclassified["misclassified_cases"])
    summary_rows.append({
        "label": "misclassified",
        "ground_truth": "—",
        "predicted": "—",
        "misclassified": (
            f"{total_misclassified}/{total} " f"({total_misclassified / total:.2%})"
        ),
        "false_positive": str(int(matrix[1, 0])),
        "false_negative": str(int(matrix[0, 1])),
    })
    st.caption("Ground truth vs predicted cases")
    st.dataframe(summary_rows, hide_index=True, width="stretch")

    st.caption(
        "Binary fraud classification confusion matrix — scenarios are shown "
        "separately below (rows = actual, columns = predicted)."
    )
    matrix_figure = go.Figure(
        go.Heatmap(
            z=matrix,
            x=["Predicted fraud", "Predicted not fraud"],
            y=["Actual fraud", "Actual not fraud"],
            text=matrix,
            texttemplate="%{text}",
            textfont={"size": 22},
            colorscale=[[0, "#F3F6FA"], [1, "#2F6690"]],
            showscale=False,
            hovertemplate="%{y}<br>%{x}: %{z}<extra></extra>",
        )
    )
    matrix_figure.update_layout(
        height=320,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        xaxis={"side": "top"},
    )
    st.plotly_chart(matrix_figure, width="stretch", config=PLOT_CONFIG)
    st.caption("Misclassified scenarios")
    st.dataframe(
        quality["misclassification"]["misclassified_scenarios"],
        hide_index=True,
        width="stretch",
    )


def render_ground_truth_reference(ground_truth: dict[str, Any]) -> None:
    render_overview(ground_truth)
    dashboard_reference = ground_truth["quality"]["dashboard_reference"]
    pipeline_summary, _ = backend_get("/v1/summary")
    pipeline_quality, _ = backend_get("/v1/quality/summary")
    render_entity_counts(
        {
            "total records": ground_truth["quality"]["total_count"],
            "customers": dashboard_reference["customer_count"],
            "accounts": dashboard_reference["account_count"],
            "transactions": dashboard_reference["transaction_count"],
            "interactions": None,
        },
        title="Ground-truth counts for production comparison",
        comparison=(
            {
                "total records": pipeline_quality.get("total_count"),
                "customers": pipeline_summary.get("customer_count"),
                "accounts": pipeline_summary.get("account_count"),
                "transactions": pipeline_summary.get("transaction_count"),
                "interactions": pipeline_summary.get("interaction_count"),
            }
            if pipeline_summary and pipeline_quality
            else None
        ),
        comparison_label="pipeline",
    )
    ground_truth_left, ground_truth_right = st.columns(2)
    with ground_truth_left:
        render_ground_truth_ingestion(ground_truth["quality"])
    with ground_truth_right:
        render_ground_truth_quality_gate(ground_truth["quality"])
    render_distributions(ground_truth)
    render_ground_truth_scenarios(ground_truth)
    render_sources(ground_truth["sources"])
    render_fraud(ground_truth["quality"])


st.set_page_config(page_title="Customer Data Product", layout="wide")
st.title("Customer Data Product")
st.caption("Operational monitoring and ground-truth validation.")

ground_truth_enabled = APP_SETTINGS.enable_ground_truth
tab_labels = ["Production results"]
if ground_truth_enabled:
    tab_labels.append("Ground-truth reference")
tabs = st.tabs(tab_labels)

with tabs[0]:
    render_production_dashboard()

if ground_truth_enabled:
    raw_root = find_raw_root()
    try:
        ground_truth = load_ground_truth(raw_root)
    except (FileNotFoundError, json.JSONDecodeError) as error:
        with tabs[1]:
            st.error(f"Could not load ground truth from {raw_root}: {error}")
    else:
        with tabs[1]:
            render_ground_truth_reference(ground_truth)
