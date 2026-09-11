from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from customer_data_product.domain.models import (
    Account,
    BatchFile,
    Customer,
    FraudEvent,
    Interaction,
    Transaction,
)


class ObjectStorage(Protocol):
    def put(self, key: str, source: Iterable[bytes]) -> int: ...

    def get(self, key: str) -> Path: ...

    def list(self, prefix: str) -> list[str]: ...


class EventPublisher(Protocol):
    def publish(self, batch_id: str) -> None: ...


class BatchRepository(Protocol):
    def create_batch(self, batch_id: str, source: str) -> None: ...

    def get_batch(self, batch_id: str) -> dict[str, object] | None: ...

    def update_status(self, batch_id: str, status: str, **counts: int) -> None: ...

    def add_file(self, batch_file: BatchFile) -> None: ...

    def list_files(self, batch_id: str) -> list[BatchFile]: ...

    def publish_customer_snapshot(self, batch_id: str) -> int: ...


class WarehouseRepository(Protocol):
    def save_customer(self, record: Customer, batch_id: str) -> bool: ...

    def save_account(self, record: Account, batch_id: str) -> bool: ...

    def save_transaction(self, record: Transaction, batch_id: str) -> bool: ...

    def save_fraud_event(self, record: FraudEvent, batch_id: str) -> bool: ...

    def save_interaction(self, record: Interaction, batch_id: str) -> bool: ...

    def publish_customer_snapshot(self, batch_id: str) -> int: ...

    def get_customer_snapshot(
        self, customer_id: str, as_of: datetime | None = None
    ) -> dict[str, object] | None: ...


class DataProcessor(Protocol):
    def process_batch(
        self, batch_id: str, *, publish_snapshot: bool = True
    ) -> dict[str, int]: ...
