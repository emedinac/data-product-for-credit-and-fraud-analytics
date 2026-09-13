import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from customer_data_product.application.ports import (
    BatchRepository,
    DataProcessor,
    EventPublisher,
    ObjectStorage,
)
from customer_data_product.domain.models import BatchFile
from customer_data_product.domain.quality import (
    QualityAssessment,
    QualityThresholds,
    assess_quality,
)
from customer_data_product.observability import emit_metric

logger = logging.getLogger(__name__)


@dataclass
class BatchService:
    batches: BatchRepository
    storage: ObjectStorage
    publisher: EventPublisher
    processor: DataProcessor
    quality_thresholds: QualityThresholds = QualityThresholds()
    max_processing_attempts: int = 3

    def create(self, source: str) -> str:
        batch_id = str(uuid4())
        self.batches.create_batch(batch_id, source)
        return batch_id

    def upload_file(self, batch_id: str, filename: str, content: object) -> BatchFile:
        safe_name = filename.replace("/", "_").replace("\\", "_")
        file_id = str(uuid4())
        key = f"landing/{batch_id}/{file_id}_{safe_name}"
        self.storage.put(key, content)  # type: ignore[arg-type]
        record = BatchFile(batch_id, file_id, safe_name, key)
        self.batches.add_file(record)
        return record

    def ingest_source_record(
        self,
        source: str,
        filename: str,
        content: object,
        idempotency_key: str | None = None,
    ) -> tuple[str, dict[str, object]]:
        """Stage one source record and enqueue it through the normal pipeline."""
        batch_id = self.create(source)
        self.upload_file(batch_id, filename, content)
        job = self.enqueue_processing(batch_id, idempotency_key)
        return batch_id, job

    def enqueue_processing(
        self, batch_id: str, idempotency_key: str | None = None
    ) -> dict[str, object]:
        return self.batches.enqueue_processing(
            batch_id, idempotency_key, self.max_processing_attempts
        )

    def process(self, batch_id: str) -> dict[str, object]:
        result = self._load(batch_id, operation="process")
        assessment = self.evaluate_quality(batch_id, result)
        if assessment.status == "FAILED":
            logger.error(
                "batch_quality_failed batch_id=%s reasons=%s",
                batch_id,
                assessment.failures,
            )
            # The batch remains available for quarantine inspection. The gate
            # blocks snapshot publication, not ingestion of the raw batch.
            return result
        self.publish_snapshot(batch_id)
        logger.info(
            "batch_process_completed batch_id=%s accepted=%s quarantined=%s",
            batch_id,
            result["accepted_count"],
            result["quarantined_count"],
        )
        return result

    def load(self, batch_id: str) -> dict[str, object]:
        return self._load(batch_id, operation="load")

    def _load(self, batch_id: str, *, operation: str) -> dict[str, object]:
        logger.info("batch_%s_started batch_id=%s", operation, batch_id)
        self.publisher.publish(batch_id)
        try:
            result = self.processor.process_batch(batch_id)
        except Exception:
            self.batches.update_status(batch_id, "FAILED")
            emit_metric("processing_failure", batch_id=batch_id)
            logger.exception("batch_%s_failed batch_id=%s", operation, batch_id)
            raise
        logger.info(
            "batch_%s_completed batch_id=%s accepted=%s quarantined=%s",
            operation,
            batch_id,
            result["accepted_count"],
            result["quarantined_count"],
        )
        return result

    def publish_snapshot(self, batch_id: str) -> int:
        batch = self.batches.get_batch(batch_id)
        if batch is None or batch.get("quality_status") != "PASSED":
            raise ValueError("batch has not passed the quality gate")
        snapshot_count = self.batches.publish_customer_snapshot(batch_id)
        published_at = datetime.now(timezone.utc)
        source_event_max = batch.get("source_event_max")
        end_to_end_sla_seconds = (
            (published_at - source_event_max).total_seconds()
            if isinstance(source_event_max, datetime)
            else None
        )
        self.batches.update_status(
            batch_id,
            "COMPLETED",
            snapshot_count=snapshot_count,
            freshness_seconds=end_to_end_sla_seconds,
            processing_completed_at=published_at,
        )
        emit_metric(
            "batch_published",
            batch_id=batch_id,
            end_to_end_sla_seconds=end_to_end_sla_seconds,
        )
        if (
            end_to_end_sla_seconds is not None
            and end_to_end_sla_seconds > self.quality_thresholds.max_freshness_seconds
        ):
            emit_metric("sla_breach", batch_id=batch_id)
        return snapshot_count

    def evaluate_quality(
        self, batch_id: str, result: dict[str, object]
    ) -> QualityAssessment:
        batch = self.batches.get_batch(batch_id)
        source = batch.get("source") if batch is not None else None
        is_incremental = source in {
            "customer_system",
            "account_system",
            "transaction_system",
            "interaction_system",
            "fraud_system",
        }
        is_evaluation = source == "eval_experiment"
        assessment = assess_quality(
            result,
            self.quality_thresholds,
            check_volume=not (is_evaluation or is_incremental),
            check_freshness=not is_evaluation,
        )
        self.batches.update_status(
            batch_id,
            (
                "LOADED"
                if assessment.status == "PASSED"
                else "COMPLETED_WITH_QUALITY_ISSUES"
            ),
            quality_status=assessment.status,
            quality_failure_reasons=list(assessment.failures),
        )
        emit_metric(
            "quality_gate",
            batch_id=batch_id,
            status=assessment.status,
            failures=list(assessment.failures),
            quarantine_rate=assessment.quarantine_rate,
            duplicate_rate=assessment.duplicate_rate,
            required_field_completeness=assessment.required_field_completeness,
            referential_integrity_failure_rate=(
                assessment.referential_integrity_failure_rate
            ),
        )
        if "FRESHNESS" in assessment.failures:
            emit_metric("sla_breach", batch_id=batch_id)
        return assessment
