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
from customer_data_product.domain.fraud import HistoryBasedFraudDetector
from customer_data_product.domain.models import (
    Account,
    Customer,
    FraudEvent,
    Transaction,
)
from customer_data_product.domain.quality import distribution_shift_scores
from customer_data_product.observability import emit_metric

logger = logging.getLogger(__name__)


def _profile(
    profile: dict[str, dict[str, int]], dimension: str, value: str | None
) -> None:
    label = value or "unknown"
    values = profile.setdefault(dimension, {})
    values[label] = values.get(label, 0) + 1


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
        self.fraud_detector = HistoryBasedFraudDetector()

    def process_batch(self, batch_id: str) -> dict[str, object]:
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
        processing_started_at = datetime.now(timezone.utc)
        self.repository.update_status(
            batch_id, "PROCESSING", processing_started_at=processing_started_at
        )
        previous_profile = self.repository.get_previous_distribution_profile(batch_id)
        counts: dict[str, int] = {
            "accepted_count": 0,
            "duplicate_count": 0,
            "quarantined_count": 0,
            "error_count": 0,
            "required_field_failure_count": 0,
            "referential_integrity_failure_count": 0,
            "fraud_event_count": 0,
            "confirmed_fraud_count": 0,
            "accepted_transaction_count": 0,
        }
        distribution_profile: dict[str, dict[str, int]] = {}
        source_times: list[datetime] = []
        history_by_customer: dict[str, list[Transaction]] = {}
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
                emit_metric("quarantine_record", issue_type="UNSUPPORTED_SOURCE")
                counts["quarantined_count"] += 1
                continue
            parser, saver = handler
            records = parser(path)
            file_record_count = 0
            file_required_field_failures = 0
            for line_number, record, error in records:
                file_record_count += 1
                if error or record is None:
                    counts["error_count"] += 1
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
                    emit_metric("quarantine_record", issue_type=issue_type)
                    counts["quarantined_count"] += 1
                    if issue_type == "REQUIRED_FIELD_MISSING":
                        counts["required_field_failure_count"] += 1
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
                    history = history_by_customer.get(record.customer_id)
                    if history is None:
                        history = self.repository.list_transaction_history(
                            record.customer_id
                        )
                        history_by_customer[record.customer_id] = history
                    assessment = self.fraud_detector.assess(
                        record,
                        history,
                    )
                    record = replace(
                        record,
                        fraud_risk_score=assessment.score,
                        fraud_decision=assessment.decision,
                        fraud_risk_reasons=assessment.reasons,
                    )
                allowed_error = _allowed_value_error(record)
                if allowed_error is not None:
                    counts["quarantined_count"] += 1
                    self.repository.add_quality_issue(
                        batch_id,
                        batch_file.filename,
                        line_number,
                        "INVALID_ALLOWED_VALUE",
                        allowed_error,
                    )
                    emit_metric("quarantine_record", issue_type="INVALID_ALLOWED_VALUE")
                    continue
                try:
                    inserted = saver(record, batch_id)
                except Exception as exc:
                    counts["error_count"] += 1
                    issue_type = (
                        "REFERENTIAL_INTEGRITY_FAILURE"
                        if "foreign key" in str(exc).lower()
                        or "referential" in str(exc).lower()
                        else "DATABASE_ERROR"
                    )
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
                        issue_type,
                        str(exc),
                    )
                    emit_metric("quarantine_record", issue_type=issue_type)
                    counts["quarantined_count"] += 1
                    is_referential = (
                        "foreign key" in str(exc).lower()
                        or "referential" in str(exc).lower()
                    )
                    if is_referential:
                        counts["referential_integrity_failure_count"] += 1
                    continue
                key = "accepted_count" if inserted else "duplicate_count"
                counts[key] += 1
                if inserted and isinstance(record, Transaction):
                    history_by_customer[record.customer_id].append(record)
                    counts["accepted_transaction_count"] += 1
                    _profile(distribution_profile, "transaction_status", record.status)
                    _profile(
                        distribution_profile, "transaction_country", record.country
                    )
                    _profile(
                        distribution_profile,
                        "merchant_category",
                        record.merchant_category,
                    )
                elif inserted and isinstance(record, FraudEvent):
                    counts["fraud_event_count"] += 1
                    if record.confirmed:
                        counts["confirmed_fraud_count"] += 1
                    _profile(
                        distribution_profile, "fraud_event_type", record.event_type
                    )
                elif inserted and isinstance(record, Customer):
                    _profile(distribution_profile, "customer_status", record.status)
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
            counts[key]
            for key in ("accepted_count", "duplicate_count", "quarantined_count")
        )
        previous_total = self.repository.get_previous_total(batch_id)
        volume_change = (
            abs(total - previous_total) / previous_total if previous_total else None
        )
        result: dict[str, object] = {
            **counts,
            "total_count": total,
            "source_event_min": source_min,
            "source_event_max": source_max,
            "freshness_seconds": freshness,
            "duration_seconds": time.monotonic() - started,
            "volume_change_rate": volume_change,
            "processing_completed_at": datetime.now(timezone.utc),
        }
        shift_scores = distribution_shift_scores(distribution_profile, previous_profile)
        distribution_shift = max(shift_scores.values(), default=0.0)
        result["distribution_profile"] = distribution_profile
        result["distribution_shift_score"] = distribution_shift
        self.repository.update_status(batch_id, "LOADED", **result)
        emit_metric(
            "batch_processing",
            batch_id=batch_id,
            duration_seconds=result["duration_seconds"],
            total_count=total,
            accepted_count=counts["accepted_count"],
            accepted_transaction_count=counts["accepted_transaction_count"],
            duplicate_count=counts["duplicate_count"],
            quarantined_count=counts["quarantined_count"],
            freshness_seconds=freshness,
            quality_failures=(
                counts["required_field_failure_count"]
                + counts["referential_integrity_failure_count"]
            ),
        )
        emit_metric(
            "fraud_batch",
            batch_id=batch_id,
            fraud_event_count=counts["fraud_event_count"],
            confirmed_fraud_count=counts["confirmed_fraud_count"],
            accepted_transaction_count=counts["accepted_transaction_count"],
        )
        emit_metric(
            "distribution_shift",
            batch_id=batch_id,
            score=distribution_shift,
            by_dimension=shift_scores,
        )
        return result
