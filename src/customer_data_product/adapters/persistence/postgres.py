from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from customer_data_product.domain.models import (
    Account,
    BatchFile,
    Customer,
    FraudEvent,
    Transaction,
)


class _ConnectionContext:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.connection = connection

    def __enter__(self) -> psycopg.Connection[Any]:
        return self.connection

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._connection = psycopg.connect(database_url, row_factory=dict_row)

    def _connect(self) -> _ConnectionContext:
        return _ConnectionContext(self._connection)

    def initialize(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text()
        with self._connect() as connection:
            connection.execute(schema)
            connection.execute(
                "ALTER TABLE batches ADD COLUMN IF NOT EXISTS "
                "snapshot_count INTEGER NOT NULL DEFAULT 0"
            )

    def create_batch(self, batch_id: str, source: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO batches (batch_id, source) VALUES (%s, %s)",
                (batch_id, source),
            )

    def get_batch(self, batch_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM batches WHERE batch_id = %s", (batch_id,)
            ).fetchone()

    def update_status(self, batch_id: str, status: str, **counts: int) -> None:
        allowed = {
            key: value
            for key, value in counts.items()
            if key
            in {
                "files_count",
                "accepted_count",
                "duplicate_count",
                "quarantined_count",
                "error_count",
                "snapshot_count",
            }
        }
        assignments = ["status = %s", "updated_at = now()"]
        values: list[object] = [status]
        for key, value in allowed.items():
            assignments.append(f"{key} = %s")
            values.append(value)
        values.append(batch_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE batches SET {', '.join(assignments)} WHERE batch_id = %s",
                values,
            )

    def add_file(self, batch_file: BatchFile) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO batch_files (file_id, batch_id, filename, storage_key)
                   VALUES (%s, %s, %s, %s)""",
                (
                    batch_file.file_id,
                    batch_file.batch_id,
                    batch_file.filename,
                    batch_file.storage_key,
                ),
            )
            connection.execute(
                "UPDATE batches SET files_count = files_count + 1, updated_at = now() "
                "WHERE batch_id = %s",
                (batch_file.batch_id,),
            )

    def list_files(self, batch_id: str) -> list[BatchFile]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM batch_files WHERE batch_id = %s ORDER BY created_at",
                (batch_id,),
            ).fetchall()
        return [
            BatchFile(r["batch_id"], r["file_id"], r["filename"], r["storage_key"])
            for r in rows
        ]

    def save_customer(self, record: Customer, batch_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """INSERT INTO customers
                   (customer_id, status, customer_type, country,
                    registered_at, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (customer_id) DO NOTHING""",
                (
                    record.customer_id,
                    record.status,
                    record.customer_type,
                    record.country,
                    record.registered_at,
                    batch_id,
                ),
            )
        return result.rowcount == 1

    def save_account(self, record: Account, batch_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """INSERT INTO accounts
                   (account_id, customer_id, account_type, opened_at,
                    credit_limit, balance, status, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (account_id) DO NOTHING""",
                (
                    record.account_id,
                    record.customer_id,
                    record.account_type,
                    record.opened_at,
                    record.credit_limit,
                    record.balance,
                    record.status,
                    batch_id,
                ),
            )
        return result.rowcount == 1

    def save_transaction(self, record: Transaction, batch_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """INSERT INTO transactions
                   (transaction_id, customer_id, account_id, event_time,
                    amount, currency, transaction_type, status, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (transaction_id) DO NOTHING""",
                (
                    record.transaction_id,
                    record.customer_id,
                    record.account_id,
                    record.event_time,
                    record.amount,
                    record.currency,
                    record.transaction_type,
                    record.status,
                    batch_id,
                ),
            )
        return result.rowcount == 1

    def save_fraud_event(self, record: FraudEvent, batch_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """INSERT INTO fraud_events
                   (event_id, customer_id, transaction_id, event_time,
                    event_type, severity, confirmed, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (event_id) DO NOTHING""",
                (
                    record.event_id,
                    record.customer_id,
                    record.transaction_id,
                    record.event_time,
                    record.event_type,
                    record.severity,
                    record.confirmed,
                    batch_id,
                ),
            )
        return result.rowcount == 1

    def publish_customer_snapshot(self, batch_id: str) -> int:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO customer_snapshots
                   SELECT c.customer_id, c.status, c.customer_type, c.country,
                          (SELECT count(*) FROM accounts a
                           WHERE a.customer_id = c.customer_id),
                          (SELECT coalesce(sum(a.credit_limit), 0)
                           FROM accounts a WHERE a.customer_id = c.customer_id),
                          (SELECT coalesce(sum(a.balance), 0)
                           FROM accounts a WHERE a.customer_id = c.customer_id),
                          (SELECT count(*) FROM transactions t
                           WHERE t.customer_id = c.customer_id),
                          (SELECT coalesce(sum(t.amount), 0) FROM transactions t
                           WHERE t.customer_id = c.customer_id
                           AND t.status = 'approved'),
                          (SELECT count(*) FROM transactions t
                           WHERE t.customer_id = c.customer_id
                           AND t.status = 'declined'),
                          (SELECT count(*) FROM fraud_events f
                           WHERE f.customer_id = c.customer_id),
                          (SELECT count(*) FROM fraud_events f
                           WHERE f.customer_id = c.customer_id
                           AND f.confirmed),
                          (SELECT max(t.event_time) FROM transactions t
                           WHERE t.customer_id = c.customer_id),
                          %s, now()
                   FROM customers c
                   ON CONFLICT (customer_id) DO UPDATE SET
                     status = EXCLUDED.status, customer_type = EXCLUDED.customer_type,
                     country = EXCLUDED.country, account_count = EXCLUDED.account_count,
                     total_credit_limit = EXCLUDED.total_credit_limit,
                     total_balance = EXCLUDED.total_balance,
                     transaction_count = EXCLUDED.transaction_count,
                     transaction_amount = EXCLUDED.transaction_amount,
                     declined_transaction_count = EXCLUDED.declined_transaction_count,
                     fraud_event_count = EXCLUDED.fraud_event_count,
                     confirmed_fraud_count = EXCLUDED.confirmed_fraud_count,
                     last_transaction_at = EXCLUDED.last_transaction_at,
                     batch_id = EXCLUDED.batch_id, updated_at = now()""",
                (batch_id,),
            )
            row = connection.execute(
                "SELECT count(*) AS count FROM customer_snapshots"
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def get_customer_snapshot(
        self, customer_id: str, as_of: datetime | None = None
    ) -> dict[str, object] | None:
        if as_of is not None:
            raise NotImplementedError("historical as_of queries are deferred")
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM customer_snapshots WHERE customer_id = %s",
                (customer_id,),
            ).fetchone()

    def get_summary(self) -> dict[str, object]:
        queries = {
            "customer_count": "SELECT count(*) AS value FROM customers",
            "account_count": "SELECT count(*) AS value FROM accounts",
            "transaction_count": "SELECT count(*) AS value FROM transactions",
            "fraud_event_count": "SELECT count(*) AS value FROM fraud_events",
            "confirmed_fraud_count": (
                "SELECT count(*) AS value FROM fraud_events WHERE confirmed"
            ),
            "quarantined_count": "SELECT count(*) AS value FROM quality_issues",
        }
        with self._connect() as connection:
            values = {
                name: int(connection.execute(query).fetchone()["value"])
                for name, query in queries.items()
            }
            latest = connection.execute(
                """SELECT batch_id, status FROM batches
                   ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
        values["last_batch_id"] = latest["batch_id"] if latest else None
        values["last_batch_status"] = latest["status"] if latest else None
        return values

    def get_distributions(self) -> dict[str, list[dict[str, object]]]:
        with self._connect() as connection:
            customer_status = connection.execute(
                """SELECT coalesce(status, 'unknown') AS label, count(*) AS count
                   FROM customers GROUP BY status ORDER BY count DESC"""
            ).fetchall()
            transaction_status = connection.execute(
                """SELECT coalesce(status, 'unknown') AS label, count(*) AS count
                   FROM transactions GROUP BY status ORDER BY count DESC"""
            ).fetchall()
        return {
            "customers_by_status": [dict(row) for row in customer_status],
            "transactions_by_status": [dict(row) for row in transaction_status],
        }

    def add_quality_issue(
        self,
        batch_id: str,
        filename: str,
        line_number: int | None,
        issue_type: str,
        detail: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO quality_issues (batch_id, filename, line_number, "
                "issue_type, detail) VALUES (%s, %s, %s, %s, %s)",
                (batch_id, filename, line_number, issue_type, detail),
            )
