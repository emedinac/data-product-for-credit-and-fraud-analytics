import csv
import json
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from customer_data_product.domain.models import (
    Account,
    Customer,
    FraudEvent,
    Transaction,
)


def first(record: Any, *names: str) -> Any:
    if not isinstance(record, Mapping):
        return None
    for name in names:
        if record.get(name) not in (None, "", "NULL", "N/A"):
            return record[name]
    return None


def text(value: Any, *, upper: bool = False) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result.upper() if upper else result.lower()


def boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    formats = (
        None,
        "%m/%d/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%Y/%m/%d",
        "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            result = (
                datetime.fromisoformat(text)
                if fmt is None
                else datetime.strptime(text, fmt)
            )
            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)
            return result
        except ValueError:
            continue
    return None


def decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = first(value, "amount", "value", "minor_units")
    text = str(value).replace(",", "").strip()
    for currency in ("USD", "EUR", "GBP", "BRL", "MXN", "CAD", "ARS", "CLP", "COP"):
        text = text.replace(currency, "").strip()
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any] | None, str | None]]:
    with path.open(encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, 1):
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    yield line_number, None, "record is not an object"
                else:
                    yield line_number, value, None
            except json.JSONDecodeError as exc:
                yield line_number, None, f"invalid JSON: {exc.msg}"


def parse_customers(path: Path) -> Iterator[tuple[int, Customer | None, str | None]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for line_number, raw in enumerate(payload.get("records", []), 1):
        customer_id = first(raw, "customer_id", "customerId")
        if not customer_id:
            yield line_number, None, "missing customer identifier"
            continue
        yield (
            line_number,
            Customer(
                str(customer_id),
                text(first(raw, "status", "state")),
                text(first(raw, "customer_type", "customerType")),
                text(first(raw, "country", "country_code"), upper=True),
                parse_datetime(first(raw, "registered_at", "registration_date")),
            ),
            None,
        )


def parse_accounts(path: Path) -> Iterator[tuple[int, Account | None, str | None]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as source:
        for line_number, raw in enumerate(csv.DictReader(source), 2):
            account_id = first(raw, "ACCOUNT_ID", "account_id")
            customer_id = first(raw, "CUSTOMER", "customer_id", "customerId")
            if not account_id or not customer_id:
                yield line_number, None, "missing account or customer identifier"
                continue
            yield (
                line_number,
                Account(
                    str(account_id),
                    str(customer_id),
                    text(first(raw, "PRODUCT", "account_type")),
                    parse_datetime(first(raw, "OPEN_DATE", "opening_date")),
                    decimal(first(raw, "LIMIT", "credit_limit")),
                    decimal(first(raw, "BALANCE", "current_balance")),
                    text(first(raw, "STATE", "account_status")),
                ),
                None,
            )


def parse_transactions(
    path: Path,
) -> Iterator[tuple[int, Transaction | None, str | None]]:
    for line_number, raw, error in jsonl(path):
        if error or raw is None:
            yield line_number, None, error
            continue
        transaction_data = raw.get("transaction")
        nested: dict[str, Any] = (
            transaction_data if isinstance(transaction_data, dict) else {}
        )
        amount = decimal(first(nested, "amount"))
        amount_data = nested.get("amount")
        if not isinstance(amount_data, dict):
            amount_data = {}
        transaction_id = first(raw, "transaction_id", "transactionId")
        customer_id = first(raw, "customer_id", "customerId")
        account_id = first(raw, "account_id", "accountId")
        event_time = parse_datetime(
            first(raw, "event_time", "eventTimestamp", "timestamp")
        )
        if (
            not transaction_id
            or not customer_id
            or not account_id
            or amount is None
            or event_time is None
        ):
            yield line_number, None, "missing or invalid transaction fields"
            continue
        yield (
            line_number,
            Transaction(
                str(transaction_id),
                str(customer_id),
                str(account_id),
                event_time,
                amount,
                text(
                    first(amount_data, "currency", "ccy", "currency_code"),
                    upper=True,
                ),
                text(first(nested, "type", "transaction_type")),
                text(first(raw, "status", "state")),
            ),
            None,
        )


def parse_fraud(path: Path) -> Iterator[tuple[int, FraudEvent | None, str | None]]:
    for line_number, raw, error in jsonl(path):
        if error or raw is None:
            yield line_number, None, error
            continue
        classification = (
            raw.get("classification")
            if isinstance(raw.get("classification"), dict)
            else {}
        )
        event_id = first(raw, "event_id", "eventId")
        customer_id = first(raw, "customer_id", "customerId")
        event_time = parse_datetime(
            first(raw, "timestamp", "event_time", "eventTimestamp")
        )
        confirmed = first(classification, "confirmed")
        if not event_id or not customer_id or event_time is None:
            yield line_number, None, "missing or invalid fraud fields"
            continue
        yield (
            line_number,
            FraudEvent(
                str(event_id),
                str(customer_id),
                first(raw, "transaction_id", "transactionId"),
                event_time,
                text(first(classification, "type", "event_type")),
                text(first(classification, "severity")),
                boolean(confirmed),
            ),
            None,
        )
