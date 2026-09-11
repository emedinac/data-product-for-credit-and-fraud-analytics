import csv
import io
import json
from collections import Counter
from datetime import date, datetime, time, timezone
from typing import Any

import httpx
import streamlit as st

from customer_data_product.settings import get_settings

BACKEND_URL = get_settings().backend_url.rstrip("/")
ENABLE_GROUND_TRUTH = get_settings().enable_ground_truth

CUSTOMER_STATUSES = ["active", "inactive", "blocked", "closed"]
CUSTOMER_TYPES = ["individual", "premium", "business"]
ACCOUNT_TYPES = ["credit_card", "personal_loan", "payment_account"]
ACCOUNT_STATUSES = ["active", "blocked", "closed", "pending"]
TRANSACTION_TYPES = ["purchase", "withdrawal", "transfer", "payment", "refund"]
TRANSACTION_STATUSES = ["approved", "declined", "reversed"]
FRAUD_TYPES = [
    "suspicious_transaction",
    "account_takeover",
    "card_stolen",
    "identity_risk",
    "chargeback",
]
FRAUD_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> dict[str, Any]:
    try:
        response = httpx.request(
            method,
            f"{BACKEND_URL}{path}",
            json=json_body,
            files=files,
            timeout=120,
        )
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise RuntimeError(f"{response.status_code}: {detail}")
        return response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Backend unavailable: {exc}") from exc


def iso_datetime(value: date, hour: int, minute: int) -> str:
    return datetime.combine(value, time(hour, minute), tzinfo=timezone.utc).isoformat()


def observation_file(kind: str, values: dict[str, Any]) -> tuple[str, bytes, str]:
    if kind == "Customer":
        payload = {"batch": {"record_count": 1}, "records": [values]}
        return (
            "customer_observation.json",
            json.dumps(payload).encode(),
            "application/json",
        )
    if kind == "Account":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "ACCOUNT_ID",
                "CUSTOMER",
                "PRODUCT",
                "OPEN_DATE",
                "LIMIT",
                "BALANCE",
                "STATE",
            ],
        )
        writer.writeheader()
        writer.writerow(values)
        return "account_observation.csv", output.getvalue().encode(), "text/csv"
    if kind == "Transaction":
        payload = {
            "event_type": "transaction",
            "transaction_id": values["transaction_id"],
            "customer_id": values["customer_id"],
            "account_id": values["account_id"],
            "event_time": values["event_time"],
            "transaction": {
                "type": values["type"],
                "amount": {
                    "currency": values["currency"],
                    "amount": values["amount"],
                },
            },
            "status": values["status"],
        }
        return (
            "transaction_observation.jsonl",
            (json.dumps(payload) + "\n").encode(),
            "application/jsonl",
        )
    payload = {
        "event_type": "fraud_event",
        "event_id": values["event_id"],
        "customer_id": values["customer_id"],
        "transaction_id": values["transaction_id"] or None,
        "timestamp": values["timestamp"],
        "classification": {
            "type": values["type"],
            "severity": values["severity"],
            "confirmed": values["confirmed"],
        },
    }
    return (
        "fraud_observation.jsonl",
        (json.dumps(payload) + "\n").encode(),
        "application/jsonl",
    )


def submit_observation(kind: str, values: dict[str, Any]) -> dict[str, Any]:
    batch = request(
        "POST",
        "/v1/batches",
        json_body={"source": "streamlit_observation"},
    )
    filename, content, content_type = observation_file(kind, values)
    request(
        "POST",
        f"/v1/batches/{batch['batch_id']}/files",
        files={"file": (filename, content, content_type)},
    )
    return request("POST", f"/v1/batches/{batch['batch_id']}/process")


def render_observation_form() -> None:
    st.subheader("Add a data observation")
    kind = st.selectbox(
        "Observation type", ["Customer", "Account", "Transaction", "Fraud event"]
    )
    with st.form("observation_form"):
        values: dict[str, Any] = {}
        if kind == "Customer":
            values["customer_id"] = st.text_input("Customer ID")
            values["status"] = st.selectbox("Status", CUSTOMER_STATUSES)
            values["customer_type"] = st.selectbox(
                "Customer type", CUSTOMER_TYPES
            )
            values["country"] = st.text_input(
                "Country", value="US", max_chars=2
            ).upper()
            registered = st.date_input("Registration date", value=date.today())
            values["registered_at"] = registered.isoformat()
        elif kind == "Account":
            values["ACCOUNT_ID"] = st.text_input("Account ID")
            values["CUSTOMER"] = st.text_input("Customer ID")
            values["PRODUCT"] = st.selectbox("Account type", ACCOUNT_TYPES)
            opened = st.date_input("Opening date", value=date.today())
            values["OPEN_DATE"] = opened.isoformat()
            values["LIMIT"] = st.number_input(
                "Credit limit", min_value=0.0, value=0.0
            )
            values["BALANCE"] = st.number_input("Balance", value=0.0)
            values["STATE"] = st.selectbox("Account status", ACCOUNT_STATUSES)
        elif kind == "Transaction":
            values["transaction_id"] = st.text_input("Transaction ID")
            values["customer_id"] = st.text_input("Customer ID")
            values["account_id"] = st.text_input("Account ID")
            event_date = st.date_input("Transaction date", value=date.today())
            hour = st.number_input("Hour", min_value=0, max_value=23, value=12)
            minute = st.number_input("Minute", min_value=0, max_value=59, value=0)
            values["event_time"] = iso_datetime(event_date, hour, minute)
            values["amount"] = st.number_input(
                "Amount", min_value=0.0, value=0.0
            )
            values["currency"] = st.text_input(
                "Currency", value="USD", max_chars=3
            ).upper()
            values["type"] = st.selectbox("Transaction type", TRANSACTION_TYPES)
            values["status"] = st.selectbox(
                "Transaction status", TRANSACTION_STATUSES
            )
        else:
            values["event_id"] = st.text_input("Fraud event ID")
            values["customer_id"] = st.text_input("Customer ID")
            values["transaction_id"] = st.text_input("Transaction ID (optional)")
            event_date = st.date_input("Event date", value=date.today())
            values["timestamp"] = event_date.isoformat()
            values["type"] = st.selectbox("Fraud type", FRAUD_TYPES)
            values["severity"] = st.selectbox("Severity", FRAUD_SEVERITIES)
            values["confirmed"] = st.checkbox("Confirmed fraud")

        submitted = st.form_submit_button("Submit observation")
        if submitted:
            try:
                result = submit_observation(kind, values)
                st.success("Observation processed")
                st.json(result)
            except RuntimeError as exc:
                st.error(str(exc))


def render_dashboard() -> None:
    try:
        summary = request("GET", "/v1/summary")
        distributions = request("GET", "/v1/summary/distributions")
        quality = request("GET", "/v1/quality?limit=500")
    except RuntimeError as exc:
        st.error(str(exc))
        return

    st.subheader("Current data")
    metrics = [
        ("Customers", summary["customer_count"]),
        ("Accounts", summary["account_count"]),
        ("Transactions", summary["transaction_count"]),
        ("Fraud events", summary["fraud_event_count"]),
        ("Confirmed fraud", summary["confirmed_fraud_count"]),
        ("Accepted / loaded", summary["latest_accepted_count"]),
        ("Duplicates", summary["latest_duplicate_count"]),
        ("Quarantined", summary["latest_quarantined_count"]),
    ]
    columns = st.columns(3)
    for index, (label, value) in enumerate(metrics):
        columns[index % 3].metric(label, value)

    left, right = st.columns(2)
    with left:
        st.caption("Customers by status")
        st.bar_chart(
            {
                item["label"]: item["count"]
                for item in distributions["customers_by_status"]
            }
        )
    with right:
        st.caption("Transactions by status")
        st.bar_chart(
            {
                item["label"]: item["count"]
                for item in distributions["transactions_by_status"]
            }
        )

    st.subheader("Data ingestion status")
    quality_types = ["All"] + sorted(
        {issue["issue_type"] for issue in quality}
    )
    selected_type = st.selectbox("Quality status", quality_types)
    selected_quality = (
        quality
        if selected_type == "All"
        else [issue for issue in quality if issue["issue_type"] == selected_type]
    )
    st.caption(
        "Accepted means loaded into the product. Quarantined means rejected "
        "for validation or reference errors. Duplicates were already loaded."
    )
    st.dataframe(selected_quality, width="stretch")


def render_ground_truth() -> None:
    st.subheader("GTs")
    try:
        ground_truth = request("GET", "/v1/ground-truth")
    except RuntimeError as exc:
        st.error(str(exc))
        return

    st.info(ground_truth["description"])
    st.caption(f"Source: {ground_truth['source']}")
    columns = st.columns(3)
    columns[0].metric("Total cases", ground_truth["total"])
    columns[1].metric("Found", ground_truth["evidence_found"])
    columns[2].metric("Missing", ground_truth["evidence_missing"])

    records = ground_truth["records"]
    evidence_scope = st.selectbox(
        "Cases to display",
        ["Missing", "Found", "All"],
        help="This selection controls the charts and samples below.",
    )
    if evidence_scope == "Missing":
        records = [record for record in records if not record["evidence_found"]]
    elif evidence_scope == "Found":
        records = [record for record in records if record["evidence_found"]]

    labels_by_type = dict(Counter(record["label"] for record in records))
    subtypes = dict(
        Counter(record["subtype"] for record in records if record["subtype"])
    )

    left, right = st.columns(2)
    with left:
        st.caption(f"Labels — {evidence_scope}")
        st.bar_chart(labels_by_type)
    with right:
        st.caption(f"Fraud/anomaly subtypes — {evidence_scope}")
        st.bar_chart(subtypes)

    st.caption("Find ground-truth cases")
    subtype_options = sorted(
        {record["subtype"] for record in records if record["subtype"]}
    )
    subtype = st.selectbox("Subtype", ["All"] + subtype_options)
    search = st.text_input("Search scenario ID or label")
    if subtype != "All":
        records = [record for record in records if record["subtype"] == subtype]
    if search:
        term = search.lower()
        records = [
            record
            for record in records
            if term in record["scenario_id"].lower()
            or term in record["label"].lower()
        ]
    display_records = []
    for record in records:
        display_record = dict(record)
        display_record["status"] = (
            "Found" if display_record.pop("evidence_found") else "Missing"
        )
        display_records.append(display_record)
    st.write(f"Matching cases: {len(records)}")
    st.dataframe(display_records, width="stretch")


st.set_page_config(page_title="Customer Data Product", layout="wide")
st.title("Customer Data Product")
st.caption(f"Backend: {BACKEND_URL}")

if st.button("Refresh dashboard"):
    st.rerun()

if ENABLE_GROUND_TRUTH:
    render_ground_truth()
    st.divider()
render_dashboard()
st.divider()
render_observation_form()
