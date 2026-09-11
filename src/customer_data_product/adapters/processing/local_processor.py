from typing import Any

from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.adapters.processing.parser import (
    parse_accounts,
    parse_customers,
    parse_fraud,
    parse_transactions,
)
from customer_data_product.adapters.storage.local_filesystem import LocalObjectStorage


class LocalProcessor:
    def __init__(
        self, storage: LocalObjectStorage, repository: PostgresRepository
    ) -> None:
        self.storage = storage
        self.repository = repository

    def process_batch(
        self, batch_id: str, *, publish_snapshot: bool = True
    ) -> dict[str, int]:
        batch = self.repository.get_batch(batch_id)
        if batch is None:
            raise ValueError("batch not found")
        self.repository.update_status(batch_id, "PROCESSING")
        counts = {
            "accepted_count": 0,
            "duplicate_count": 0,
            "quarantined_count": 0,
            "error_count": 0,
        }
        for batch_file in self.repository.list_files(batch_id):
            path = self.storage.get(batch_file.storage_key)
            name = batch_file.filename.lower()
            records: Any
            saver: Any
            if "customer" in name:
                records = parse_customers(path)
                saver = self.repository.save_customer
            elif "account" in name:
                records = parse_accounts(path)
                saver = self.repository.save_account
            elif "transaction" in name:
                records = parse_transactions(path)
                saver = self.repository.save_transaction
            elif "fraud" in name:
                records = parse_fraud(path)
                saver = self.repository.save_fraud_event
            else:
                self.repository.add_quality_issue(
                    batch_id,
                    batch_file.filename,
                    None,
                    "UNSUPPORTED_SOURCE",
                    "core source filename not recognized",
                )
                counts["quarantined_count"] += 1
                continue
            for line_number, record, error in records:
                if error or record is None:
                    self.repository.add_quality_issue(
                        batch_id,
                        batch_file.filename,
                        line_number,
                        "INVALID_RECORD",
                        error or "invalid record",
                    )
                    counts["quarantined_count"] += 1
                    continue
                try:
                    inserted = saver(record, batch_id)
                except Exception as exc:
                    self.repository.add_quality_issue(
                        batch_id,
                        batch_file.filename,
                        line_number,
                        "REFERENTIAL_OR_DATABASE_ERROR",
                        str(exc),
                    )
                    counts["quarantined_count"] += 1
                    continue
                counts["accepted_count" if inserted else "duplicate_count"] += 1
        if publish_snapshot:
            counts["snapshot_count"] = self.repository.publish_customer_snapshot(
                batch_id
            )
            status = "COMPLETED"
        else:
            status = "LOADED"
        self.repository.update_status(batch_id, status, **counts)
        return counts
