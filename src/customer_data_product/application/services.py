import logging
from dataclasses import dataclass
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
        self.batches.update_status(
            batch_id, "COMPLETED", snapshot_count=snapshot_count
        )
        return snapshot_count

    def evaluate_quality(
        self, batch_id: str, result: dict[str, object]
    ) -> QualityAssessment:
        assessment = assess_quality(result, self.quality_thresholds)
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
        return assessment
