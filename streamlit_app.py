"""Small local viewer for the generated raw-data ground truth."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

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


def find_raw_root() -> Path:
    configured = Path(os.getenv("DATA_ROOT", "raw_dev"))
    return configured if configured.is_dir() else Path("dev_raw")


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


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


def show_bar_table(
    values: dict[str, int | float],
    *,
    total: int | float | None = None,
    percent: bool = False,
    prediction_total: int | None = None,
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
            "ground_truth": f"{value:.2%}" if percent else value,
                "bar": share * 100 if show_percentage else share,
        })
        if prediction_total is not None:
            rows[-1]["configured rate"] = rows[-1].pop("ground_truth")
        if percent and prediction_total is not None:
            predicted = round(float(value) * prediction_total)
            rows[-1]["expected at configured rate"] = (
                f"{predicted:,}/{prediction_total:,} ({value:.2%})"
            )
        if percent and observed_counts is not None:
            observed = observed_counts.get(label)
            rows[-1]["observed"] = (
                "—"
                if observed is None or prediction_total is None
                else f"{observed:,}/{prediction_total:,} "
                f"({observed / prediction_total:.2%})"
            )
        if not percent and total is not None:
            rows[-1]["count / total"] = f"{value:g}/{total:g}"
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "bar": st.column_config.ProgressColumn(
                "distribution",
                min_value=0,
                max_value=100 if show_percentage else 1,
                format="%.2f%%" if show_percentage else "%g",
            )
        },
    )


def show_found_vs_global(found: dict[str, int], global_cases: dict[str, int]) -> None:
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
            textposition="auto",
            marker_color="#4C78A8",
        ),
        go.Bar(
            name="global",
            y=labels,
            x=global_percent,
            orientation="h",
            text=[f"{global_cases[label]:,} (100%)" for label in labels],
            textposition="auto",
            marker_color="#D9E2F3",
        ),
    ])
    figure.update_layout(
        barmode="group",
        height=300,
        margin={"l": 0, "r": 0, "t": 10, "b": 10},
        xaxis={"title": "share of global cases", "range": [0, 110], "ticksuffix": "%"},
        yaxis={"title": None},
        legend={"orientation": "h", "y": 1.12},
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


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


def render_overview(data: dict[str, Any]) -> None:
    manifest = data["manifest"]
    quality = data["quality"]
    st.subheader("Ground-truth overview")
    columns = st.columns(4)
    columns[0].metric("Logical records", f"{manifest['requested_logical_records']:,}")
    columns[1].metric("Customers", f"{manifest['customer_count']:,}")
    columns[2].metric("Records checked", f"{quality['total_count']:,}")
    columns[3].metric(
        "Expected quarantined", f"{quality['expected_quarantined_count']:,}"
    )

    failures = {
        "required field failures": quality["required_field_failure_count"],
        "invalid records": quality["invalid_record_count"],
        "referential integrity failures": quality[
            "referential_integrity_failure_count"
        ],
        "future events": quality["future_event_count"],
    }
    st.caption("Quality failure counts")
    show_bar_table(failures, total=quality["total_count"])


def render_distributions(data: dict[str, Any]) -> None:
    quality = data["quality"]
    st.subheader("Distributions")
    left, right = st.columns(2)
    with left:
        st.caption("Detected / found vs global generated cases")
        dashboard = quality["dashboard_reference"]
        records_by_domain = quality["all_generated_cases"]["records_by_domain"]
        found = {
            "customers": dashboard["customer_count"],
            "accounts": dashboard["account_count"],
            "transactions": dashboard["transaction_count"],
            "fraud events": dashboard["fraud_event_count"],
        }
        global_cases = {
            "customers": records_by_domain["customer_core"],
            "accounts": records_by_domain["accounts"],
            "transactions": records_by_domain["transactions"],
            "fraud events": records_by_domain["fraud"],
        }
        show_found_vs_global(found, global_cases)
        st.caption("Detected / found vs global generated scenarios")
        global_scenarios = quality["all_generated_cases"]["scenario_counts"]
        found_scenarios = Counter(
            scenario.get("label", "unknown") for scenario in data["scenarios"]
        )
        scenario_labels = {
            "fraud": "fraud",
            "anomaly": "anomaly",
            "duplicate_payment": "duplicate",
        }
        show_found_vs_global(
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
            "do not mean that every generated issue was detected. Expected cases "
            "use the 7,317-record observation base; observed cases come from the "
            "quality ground truth."
        )
        show_bar_table(
            data["manifest"]["quality_parameters"],
            percent=True,
            prediction_total=quality["total_count"],
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


def render_fraud(quality: dict[str, Any]) -> None:
    st.subheader("Fraud detection ground truth")
    metrics = fraud_metrics(quality)
    st.caption(
        "Metrics are recomputed with scikit-learn from the labelled cases and "
        "misclassifications."
    )
    show_bar_table(metrics, percent=True)

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
    st.plotly_chart(
        matrix_figure, width="stretch", config={"displayModeBar": False}
    )
    st.caption("Misclassified scenarios")
    st.dataframe(
        quality["misclassification"]["misclassified_scenarios"],
        hide_index=True,
        width="stretch",
    )


st.set_page_config(page_title="Raw data ground truth", layout="wide")
st.title("Raw data ground truth")
st.caption(
    "Quality expectations, distributions, and fraud-detection checks from "
    "raw_dev/metadata"
)

raw_root = find_raw_root()
try:
    ground_truth = load_ground_truth(raw_root)
except (FileNotFoundError, json.JSONDecodeError) as error:
    st.error(f"Could not load ground truth from {raw_root}: {error}")
    st.stop()

render_overview(ground_truth)
render_distributions(ground_truth)
render_sources(ground_truth["sources"])
render_fraud(ground_truth["quality"])
