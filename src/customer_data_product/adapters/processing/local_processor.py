import logging
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, cast

from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.adapters.processing.parser import (
    parse_accounts,
    parse_customers,
    parse_fraud,
    parse_interactions,
    parse_transactions,
)
from customer_data_product.application.ports import ObjectStorage
from customer_data_product.domain.contracts import (
    ACCOUNT_STATUSES,
    ACCOUNT_TYPES,
    CUSTOMER_STATUSES,
    CUSTOMER_TYPES,
    FRAUD_TYPES,
    TRANSACTION_STATUSES,
    TRANSACTION_TYPES,
    is_country,
    is_currency,
)
from customer_data_product.domain.currency import CurrencyPolicy
from customer_data_product.domain.models import (
    Account,
    Customer,
    FraudEvent,
    Transaction,
)
from customer_data_product.observability import emit_metric

logger = logging.getLogger(__name__)


def _count(counts: dict[str, object], key: str) -> int:
    return cast(int, counts[key])


def _increment(counts: dict[str, object], key: str) -> None:
    counts[key] = _count(counts, key) + 1


def _allowed_value_error(record: object) -> str | None:
    checks: list[tuple[str | None, frozenset[str]]] = []
    if isinstance(record, Customer):
        checks = [
            (record.status, CUSTOMER_STATUSES),
            (record.customer_type, CUSTOMER_TYPES),
        ]
        if record.country is not None and not is_country(record.country):
            return "country is not an ISO alpha-2 code"
    elif isinstance(record, Account):
        checks = [
            (record.account_type, ACCOUNT_TYPES),
            (record.status, ACCOUNT_STATUSES),
        ]
    elif isinstance(record, Transaction):
        checks = [
            (record.transaction_type, TRANSACTION_TYPES),
            (record.status, TRANSACTION_STATUSES),
        ]
        if record.currency is not None and not is_currency(record.currency):
            return "currency is not an ISO 4217 code"
        if record.country is not None and not is_country(record.country):
            return "country is not an ISO alpha-2 code"
    elif isinstance(record, FraudEvent):
        checks = [(record.event_type, FRAUD_TYPES)]
    for value, allowed in checks:
        if value is not None and value not in allowed:
            return f"value '{value}' is not in the approved v1 set"
    return None


class LocalProcessor:
    def __init__(
        self,
        storage: ObjectStorage,
        repository: PostgresRepository,
        currency_policy: CurrencyPolicy | None = None,
    ) -> None:
        self.storage = storage
        self.repository = repository
        self.currency_policy = currency_policy or CurrencyPolicy()

    def process_batch(
        self, batch_id: str
    ) -> dict[str, object]:
        started = time.monotonic()
        batch = self.repository.get_batch(batch_id)
        if batch is None:
            raise ValueError("batch not found")
        if batch["status"] == "COMPLETED":
            return {
                "total_count": cast(int, batch["total_count"]),
                "accepted_count": cast(int, batch["accepted_count"]),
                "duplicate_count": cast(int, batch["duplicate_count"]),
                "quarantined_count": cast(int, batch["quarantined_count"]),
                "error_count": cast(int, batch["error_count"]),
                "required_field_failure_count": cast(
                    int, batch["required_field_failure_count"]
                ),
                "referential_integrity_failure_count": cast(
                    int, batch["referential_integrity_failure_count"]
                ),
                "freshness_seconds": batch["freshness_seconds"],
                "volume_change_rate": batch["volume_change_rate"],
                "snapshot_count": cast(int, batch["snapshot_count"]),
            }
        self.repository.update_status(batch_id, "PROCESSING")
        processing_started_at = datetime.now(timezone.utc)
        self.repository.update_status(
            batch_id, "PROCESSING", processing_started_at=processing_started_at
        )
        counts: dict[str, object] = {
            "accepted_count": 0,
            "duplicate_count": 0,
            "quarantined_count": 0,
            "error_count": 0,
            "required_field_failure_count": 0,
            "referential_integrity_failure_count": 0,
        }
        source_times: list[datetime] = []
        parsers = {
            "customer": (parse_customers, self.repository.save_customer),
            "account": (parse_accounts, self.repository.save_account),
            "transaction": (parse_transactions, self.repository.save_transaction),
            "fraud": (parse_fraud, self.repository.save_fraud_event),
            "interaction": (parse_interactions, self.repository.save_interaction),
        }
        for batch_file in self.repository.list_files(batch_id):
            path = self.storage.get(batch_file.storage_key)
            name = batch_file.filename.lower()
            handler: tuple[Any, Any] | None = next(
                (value for source, value in parsers.items() if source in name),
                None,
            )
            if handler is None:
                emit_metric("source_schema_drift", source=batch_file.filename)
                self.repository.add_quality_issue(
                    batch_id,
                    batch_file.filename,
                    None,
                    "UNSUPPORTED_SOURCE",
                    "core source filename not recognized",
                )
                _increment(counts, "quarantined_count")
                continue
            parser, saver = handler
            records = parser(path)
            file_record_count = 0
            file_required_field_failures = 0
            for line_number, record, error in records:
                file_record_count += 1
                if error or record is None:
                    _increment(counts, "error_count")
                    issue_type = (
                        "REQUIRED_FIELD_MISSING"
                        if error and "missing" in error
                        else "INVALID_RECORD"
                    )
                    self.repository.add_quality_issue(
                        batch_id,
                        batch_file.filename,
                        line_number,
                        issue_type,
                        error or "invalid record",
                    )
                    _increment(counts, "quarantined_count")
                    if issue_type == "REQUIRED_FIELD_MISSING":
                        _increment(counts, "required_field_failure_count")
                        file_required_field_failures += 1
                    continue
                event_time = getattr(record, "event_time", None)
                if event_time is None:
                    event_time = getattr(record, "registered_at", None)
                if event_time is None:
                    event_time = getattr(record, "opened_at", None)
                if event_time is not None:
                    source_times.append(event_time)
                if isinstance(record, Transaction):
                    converted = self.currency_policy.convert(
                        record.amount, record.currency
                    )
                    if converted[0] is None:
                        emit_metric("exchange_rate_failure")
                    record = replace(
                        record,
                        amount_base_currency=converted[0],
                        exchange_rate=converted[1],
                        exchange_rate_source=converted[2],
                        exchange_rate_timestamp=converted[3],
                    )
                allowed_error = _allowed_value_error(record)
                if allowed_error is not None:
                    _increment(counts, "quarantined_count")
                    self.repository.add_quality_issue(
                        batch_id,
                        batch_file.filename,
                        line_number,
                        "INVALID_ALLOWED_VALUE",
                        allowed_error,
                    )
                    continue
                try:
                    inserted = saver(record, batch_id)
                except Exception as exc:
                    _increment(counts, "error_count")
                    logger.warning(
                        "record_rejected batch_id=%s file=%s line=%s reason=%s",
                        batch_id,
                        batch_file.filename,
                        line_number,
                        exc,
                    )
                    self.repository.add_quality_issue(
                        batch_id,
                        batch_file.filename,
                        line_number,
                        (
                            "REFERENTIAL_INTEGRITY_FAILURE"
                            if "foreign key" in str(exc).lower()
                            or "referential" in str(exc).lower()
                            else "DATABASE_ERROR"
                        ),
                        str(exc),
                    )
                    _increment(counts, "quarantined_count")
                    is_referential = (
                        "foreign key" in str(exc).lower()
                        or "referential" in str(exc).lower()
                    )
                    if is_referential:
                        _increment(counts, "referential_integrity_failure_count")
                    continue
                key = "accepted_count" if inserted else "duplicate_count"
                _increment(counts, key)
            if (
                file_record_count > 0
                and file_required_field_failures == file_record_count
            ):
                logger.error(
                    "source_schema_drift batch_id=%s file=%s",
                    batch_id,
                    batch_file.filename,
                )
                emit_metric("source_schema_drift")
        ended_at = datetime.now(timezone.utc)
        source_min = min(source_times) if source_times else None
        source_max = max(source_times) if source_times else None
        freshness = (
            (ended_at - source_max).total_seconds() if source_max is not None else None
        )
        total = sum(
            _count(counts, key)
            for key in ("accepted_count", "duplicate_count", "quarantined_count")
        )
        previous_total = self.repository.get_previous_total(batch_id)
        volume_change = (
            abs(total - previous_total) / previous_total
            if previous_total
            else None
        )
        counts["total_count"] = total
        counts["source_event_min"] = source_min
        counts["source_event_max"] = source_max
        counts["freshness_seconds"] = freshness
        counts["duration_seconds"] = time.monotonic() - started
        counts["volume_change_rate"] = volume_change
        counts["processing_completed_at"] = datetime.now(timezone.utc)
        self.repository.update_status(batch_id, "LOADED", **counts)
        emit_metric(
            "batch_processing",
            batch_id=batch_id,
            duration_seconds=counts["duration_seconds"],
            total_count=total,
            accepted_count=counts["accepted_count"],
            duplicate_count=counts["duplicate_count"],
            quarantined_count=counts["quarantined_count"],
            freshness_seconds=freshness,
            quality_failures=(
                _count(counts, "required_field_failure_count")
                + _count(counts, "referential_integrity_failure_count")
            ),
        )
        return counts
