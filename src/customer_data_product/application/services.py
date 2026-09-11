from dataclasses import dataclass
from uuid import uuid4

from customer_data_product.application.ports import (
    BatchRepository,
    DataProcessor,
    EventPublisher,
    ObjectStorage,
)
from customer_data_product.domain.models import BatchFile


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
        self.publisher.publish(batch_id)
        result = self.processor.process_batch(batch_id)
        return result

    def load(self, batch_id: str) -> dict[str, int]:
        self.publisher.publish(batch_id)
        return self.processor.process_batch(batch_id, publish_snapshot=False)

    def publish_snapshot(self, batch_id: str) -> int:
        snapshot_count = self.batches.publish_customer_snapshot(batch_id)
        self.batches.update_status(
            batch_id, "COMPLETED", snapshot_count=snapshot_count
        )
        return snapshot_count
