"""Local Airflow pipeline for the customer data product."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from airflow.sdk import dag, task

# Core source folders currently supported by the ingestion pipeline.
CORE_SOURCE_DIRECTORIES = (
    "customer_core",
    "accounts",
    "transactions",
    "fraud",
    "customer_service",
)
# File types accepted from the raw landing area.
SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl"}


def _service() -> Any:
    # Build fresh application adapters for each Airflow task process.
    from customer_data_product.adapters.events import LocalEventPublisher
    from customer_data_product.adapters.persistence.postgres import PostgresRepository
    from customer_data_product.adapters.processing.local_processor import LocalProcessor
    from customer_data_product.adapters.storage.local_filesystem import (
        LocalObjectStorage,
    )
    from customer_data_product.application.services import BatchService

    storage = LocalObjectStorage(Path(os.environ.get("LAKE_ROOT", "/opt/project/lake")))
    repository = PostgresRepository(
        os.environ.get(
            "DATABASE_URL",
            "postgresql://customer:customer@postgres:5432/customer_product",
        )
    )
    repository.initialize()
    return BatchService(
        repository,
        storage,
        LocalEventPublisher(),
        LocalProcessor(storage, repository),
    )


@dag(
    dag_id="customer_data_product_pipeline",
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["customer-data", "etl"],
)
def customer_data_product_pipeline() -> None:
    @task
    def land_raw_files() -> str:
        # Register a batch and copy supported raw files into the data lake.
        service = _service()
        batch_id = service.create("raw_dev")
        raw_root = Path(os.environ.get("RAW_ROOT", "/opt/project/raw_dev"))
        uploaded = 0
        for directory in CORE_SOURCE_DIRECTORIES:
            for path in sorted((raw_root / directory).glob("*")):
                if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                    with path.open("rb") as source:
                        service.upload_file(
                            batch_id, path.name, iter(source.readline, b"")
                        )
                    uploaded += 1
        if uploaded == 0:
            raise FileNotFoundError(f"no supported source files found in {raw_root}")
        return batch_id

    @task
    def load_warehouse(batch_id: str) -> dict[str, int]:
        # Parse, normalize, validate, and load records into warehouse tables.
        return _service().load(batch_id)

    @task
    def quality_gate(batch_id: str, result: dict[str, int]) -> str:
        # Thresholds are configurable; 1.0 preserves the prototype behavior.
        total = sum(
            result[key]
            for key in ("accepted_count", "duplicate_count", "quarantined_count")
        )
        quarantine_rate = (
            result["quarantined_count"] / total if total else 1.0
        )
        duplicate_rate = result["duplicate_count"] / total if total else 0.0
        max_quarantine_rate = float(os.environ.get("MAX_QUARANTINE_RATE", "1.0"))
        max_duplicate_rate = float(os.environ.get("MAX_DUPLICATE_RATE", "1.0"))
        if result["accepted_count"] == 0 and result["quarantined_count"] > 0:
            raise ValueError("batch contained no accepted records")
        if quarantine_rate > max_quarantine_rate:
            raise ValueError(f"quarantine rate {quarantine_rate:.2%} exceeds threshold")
        if duplicate_rate > max_duplicate_rate:
            raise ValueError(f"duplicate rate {duplicate_rate:.2%} exceeds threshold")
        return batch_id

    @task
    def publish_customer_snapshots(batch_id: str) -> int:
        # Rebuild customer-level analytical snapshots after the warehouse load.
        return _service().publish_snapshot(batch_id)

    batch_id = land_raw_files()
    loaded = load_warehouse(batch_id)
    publish_customer_snapshots(quality_gate(batch_id, loaded))


customer_data_product_pipeline()
