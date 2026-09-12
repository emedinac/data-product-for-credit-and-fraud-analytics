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

logger = logging.getLogger(__name__)


@dataclass
class BatchService:
    batches: BatchRepository
    storage: ObjectStorage
    publisher: EventPublisher
    processor: DataProcessor

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

    def process(self, batch_id: str) -> dict[str, int]:
        logger.info("batch_process_started batch_id=%s", batch_id)
        self.publisher.publish(batch_id)
        try:
            result = self.processor.process_batch(batch_id)
        except Exception:
            self.batches.update_status(batch_id, "FAILED")
            logger.exception("batch_process_failed batch_id=%s", batch_id)
            raise
        logger.info(
            "batch_process_completed batch_id=%s accepted=%s quarantined=%s",
            batch_id,
            result["accepted_count"],
            result["quarantined_count"],
        )
        return result

    def load(self, batch_id: str) -> dict[str, int]:
        logger.info("batch_load_started batch_id=%s", batch_id)
        self.publisher.publish(batch_id)
        try:
            result = self.processor.process_batch(batch_id, publish_snapshot=False)
        except Exception:
            self.batches.update_status(batch_id, "FAILED")
            logger.exception("batch_load_failed batch_id=%s", batch_id)
            raise
        logger.info(
            "batch_load_completed batch_id=%s accepted=%s quarantined=%s",
            batch_id,
            result["accepted_count"],
            result["quarantined_count"],
        )
        return result

    def publish_snapshot(self, batch_id: str) -> int:
        snapshot_count = self.batches.publish_customer_snapshot(batch_id)
        self.batches.update_status(
            batch_id, "COMPLETED", snapshot_count=snapshot_count
        )
        return snapshot_count
