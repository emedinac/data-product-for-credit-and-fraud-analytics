# ruff: noqa: E501

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from customer_data_product.domain.models import (
    Account,
    BatchFile,
    Customer,
    FraudEvent,
    Interaction,
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
    def __init__(self, database_url: str, base_currency: str = "USD") -> None:
        self.database_url = database_url
        self.base_currency = base_currency.upper()
        self._connection = psycopg.connect(database_url, row_factory=dict_row)

    def _connect(self) -> _ConnectionContext:
        return _ConnectionContext(self._connection)

    def check_connection(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1")

    def record_access_audit(
        self,
        *,
        actor_subject: str,
        consumer: str | None,
        action: str,
        resource: str,
        outcome: str,
        roles: set[str],
    ) -> None:
        """Append access metadata only; requests and responses may contain PII."""
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO access_audit
                   (actor_subject, consumer, action, resource, outcome, roles)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    actor_subject,
                    consumer,
                    action,
                    resource,
                    outcome,
                    sorted(roles),
                ),
            )

    def initialize(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text()
        migration_dir = Path(__file__).with_name("migrations")
        with self._connect() as connection:
            connection.execute(schema)
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )"""
            )
            for migration in sorted(migration_dir.glob("*.sql")):
                version = migration.name
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                ).fetchone()
                if applied is None:
                    connection.execute(migration.read_text())
                    connection.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (version,),
                    )
            connection.execute(
                "ALTER TABLE batches ADD COLUMN IF NOT EXISTS "
                "snapshot_count INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute(
                "ALTER TABLE batches ADD COLUMN IF NOT EXISTS "
                "distribution_profile JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
            connection.execute(
                "ALTER TABLE batches ADD COLUMN IF NOT EXISTS "
                "distribution_shift_score DOUBLE PRECISION"
            )
            connection.execute(
                "ALTER TABLE customer_snapshots ADD COLUMN IF NOT EXISTS "
                "interaction_count INTEGER NOT NULL DEFAULT 0"
            )
            for column, definition in (
                ("amount_base_currency", "NUMERIC"),
                ("exchange_rate", "NUMERIC"),
                ("exchange_rate_source", "TEXT"),
                ("exchange_rate_timestamp", "TIMESTAMPTZ"),
            ):
                connection.execute(
                    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS "
                    f"{column} {definition}"
                )
            connection.execute(
                "ALTER TABLE customer_snapshots ADD COLUMN IF NOT EXISTS "
                "transaction_amount_currency TEXT NOT NULL DEFAULT 'USD'"
            )
            for column, definition in (
                ("arrived_at", "TIMESTAMPTZ NOT NULL DEFAULT now()"),
                ("processing_started_at", "TIMESTAMPTZ"),
                ("processing_completed_at", "TIMESTAMPTZ"),
            ):
                connection.execute(
                    "ALTER TABLE batches ADD COLUMN IF NOT EXISTS "
                    f"{column} {definition}"
                )
            for column, definition in (
                ("effective_at", "TIMESTAMPTZ"),
                ("as_of_time", "TIMESTAMPTZ NOT NULL DEFAULT now()"),
            ):
                connection.execute(
                    "ALTER TABLE customer_snapshots ADD COLUMN IF NOT EXISTS "
                    f"{column} {definition}"
                )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS customer_snapshot_history (
                    snapshot_id BIGSERIAL PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                    effective_at TIMESTAMPTZ,
                    as_of_time TIMESTAMPTZ NOT NULL,
                    snapshot JSONB NOT NULL,
                    UNIQUE (customer_id, batch_id)
                )"""
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

    def get_previous_total(self, batch_id: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT total_count FROM batches
                   WHERE batch_id <> %s AND total_count > 0
                     AND status IN (
                         'COMPLETED', 'LOADED', 'COMPLETED_WITH_QUALITY_ISSUES',
                         'QUALITY_FAILED'
                     )
                   ORDER BY updated_at DESC LIMIT 1""",
                (batch_id,),
            ).fetchone()
        return int(row["total_count"]) if row is not None else None

    def get_previous_distribution_profile(
        self, batch_id: str
    ) -> dict[str, dict[str, int]] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT distribution_profile FROM batches
                   WHERE batch_id <> %s AND total_count > 0
                     AND distribution_profile <> '{}'::jsonb
                     AND status IN (
                         'COMPLETED', 'LOADED', 'COMPLETED_WITH_QUALITY_ISSUES',
                         'QUALITY_FAILED'
                     )
                   ORDER BY updated_at DESC LIMIT 1""",
                (batch_id,),
            ).fetchone()
        return row["distribution_profile"] if row is not None else None

    def update_status(self, batch_id: str, status: str, **counts: object) -> None:
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
                "total_count",
                "required_field_failure_count",
                "referential_integrity_failure_count",
                "source_event_min",
                "source_event_max",
                "freshness_seconds",
                "duration_seconds",
                "volume_change_rate",
                "quality_status",
                "quality_failure_reasons",
                "distribution_profile",
                "distribution_shift_score",
                "processing_started_at",
                "processing_completed_at",
            }
        }
        assignments = ["status = %s", "updated_at = now()"]
        values: list[object] = [status]
        for key, value in allowed.items():
            assignments.append(f"{key} = %s")
            values.append(Jsonb(value) if key == "distribution_profile" else value)
        values.append(batch_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE batches SET {', '.join(assignments)} WHERE batch_id = %s",
                values,
            )

    def enqueue_processing(
        self, batch_id: str, idempotency_key: str | None, max_attempts: int
    ) -> dict[str, object]:
        with self._connect() as connection:
            batch = connection.execute(
                """SELECT status, files_count FROM batches
                   WHERE batch_id = %s FOR UPDATE""",
                (batch_id,),
            ).fetchone()
            if batch is None:
                raise ValueError("batch not found")
            if int(batch["files_count"]) == 0:
                raise ValueError("batch has no files")
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM processing_jobs WHERE idempotency_key = %s",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    if existing["batch_id"] != batch_id:
                        raise ValueError("idempotency key belongs to another batch")
                    return dict(existing)
            existing = connection.execute(
                "SELECT * FROM processing_jobs WHERE batch_id = %s", (batch_id,)
            ).fetchone()
            if existing is not None:
                return dict(existing)
            if batch["status"] == "COMPLETED":
                raise ValueError("batch has already completed")
            job_id = str(uuid4())
            row = connection.execute(
                """INSERT INTO processing_jobs
                   (job_id, batch_id, idempotency_key, max_attempts)
                   VALUES (%s, %s, %s, %s) RETURNING *""",
                (job_id, batch_id, idempotency_key, max_attempts),
            ).fetchone()
            connection.execute(
                """UPDATE batches SET status = 'QUEUED', updated_at = now()
                   WHERE batch_id = %s""",
                (batch_id,),
            )
        assert row is not None
        return dict(row)

    def claim_processing_job(self, lease_seconds: int) -> dict[str, object] | None:
        expired = datetime.now(timezone.utc) - timedelta(seconds=lease_seconds)
        lock_token = str(uuid4())
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM processing_jobs
                   WHERE (status IN ('QUEUED', 'RETRYING') AND available_at <= now())
                      OR (status = 'PROCESSING' AND locked_at < %s)
                   ORDER BY available_at, created_at
                   FOR UPDATE SKIP LOCKED LIMIT 1""",
                (expired,),
            ).fetchone()
            if row is None:
                return None
            claimed = connection.execute(
                """UPDATE processing_jobs
                   SET status = 'PROCESSING', attempts = attempts + 1,
                       locked_at = now(), lock_token = %s, updated_at = now()
                   WHERE job_id = %s RETURNING *""",
                (lock_token, row["job_id"]),
            ).fetchone()
            connection.execute(
                """UPDATE batches SET status = 'PROCESSING', updated_at = now()
                   WHERE batch_id = %s""",
                (row["batch_id"],),
            )
        return dict(claimed) if claimed is not None else None

    def complete_processing_job(self, job_id: str, lock_token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE processing_jobs SET status = 'COMPLETED', locked_at = NULL,
                   lock_token = NULL, updated_at = now()
                   WHERE job_id = %s AND lock_token = %s""",
                (job_id, lock_token),
            )

    def fail_processing_job(
        self, job_id: str, lock_token: str, error: str, retry_delay_seconds: int
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM processing_jobs WHERE job_id = %s FOR UPDATE", (job_id,)
            ).fetchone()
            if row is None or row["lock_token"] != lock_token:
                return False
            retry = int(row["attempts"]) < int(row["max_attempts"])
            status = "RETRYING" if retry else "FAILED"
            connection.execute(
                """UPDATE processing_jobs
                   SET status = %s,
                       available_at = now() + %s * interval '1 second',
                       locked_at = NULL, lock_token = NULL, last_error = %s,
                       updated_at = now()
                   WHERE job_id = %s""",
                (status, retry_delay_seconds if retry else 0, error[:4000], job_id),
            )
            connection.execute(
                """UPDATE batches SET status = %s, updated_at = now()
                   WHERE batch_id = %s""",
                (status, row["batch_id"]),
            )
        return retry

    def processing_queue_depth(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT count(*) AS depth FROM processing_jobs
                   WHERE status IN ('QUEUED', 'RETRYING') AND available_at <= now()"""
            ).fetchone()
        return int(row["depth"] if row is not None else 0)

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
                   (customer_id, first_name, last_name, date_of_birth, status,
                    customer_type, country, city, registered_at, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (customer_id) DO UPDATE SET
                     first_name = EXCLUDED.first_name,
                     last_name = EXCLUDED.last_name,
                     date_of_birth = EXCLUDED.date_of_birth,
                     status = EXCLUDED.status,
                     customer_type = EXCLUDED.customer_type,
                     country = EXCLUDED.country,
                     city = EXCLUDED.city,
                     registered_at = EXCLUDED.registered_at,
                     batch_id = EXCLUDED.batch_id""",
                (
                    record.customer_id,
                    record.first_name,
                    record.last_name,
                    record.date_of_birth,
                    record.status,
                    record.customer_type,
                    record.country,
                    record.city,
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
                   ON CONFLICT (account_id) DO UPDATE SET
                     customer_id = EXCLUDED.customer_id,
                     account_type = EXCLUDED.account_type,
                     opened_at = EXCLUDED.opened_at,
                     credit_limit = EXCLUDED.credit_limit,
                     balance = EXCLUDED.balance,
                     status = EXCLUDED.status,
                     batch_id = EXCLUDED.batch_id""",
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
                    amount, currency, amount_base_currency, exchange_rate,
                    exchange_rate_source, exchange_rate_timestamp,
                    transaction_type, status, merchant_id, merchant_category,
                    country, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s)
                   ON CONFLICT (transaction_id) DO NOTHING""",
                (
                    record.transaction_id,
                    record.customer_id,
                    record.account_id,
                    record.event_time,
                    record.amount,
                    record.currency,
                    record.amount_base_currency,
                    record.exchange_rate,
                    record.exchange_rate_source,
                    record.exchange_rate_timestamp,
                    record.transaction_type,
                    record.status,
                    record.merchant_id,
                    record.merchant_category,
                    record.country,
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

    def save_interaction(self, record: Interaction, batch_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                """INSERT INTO interactions
                   (interaction_id, customer_id, event_time, channel,
                    interaction_type, resolution, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (interaction_id) DO NOTHING""",
                (
                    record.interaction_id,
                    record.customer_id,
                    record.event_time,
                    record.channel,
                    record.interaction_type,
                    record.resolution,
                    batch_id,
                ),
            )
        return result.rowcount == 1

    def publish_customer_snapshot(self, batch_id: str) -> int:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO customer_snapshots
                   (customer_id, first_name, last_name, date_of_birth, status,
                    customer_type, country, city, account_count, total_credit_limit,
                    total_balance, transaction_count,
                   transaction_amount, transaction_amount_currency,
                   declined_transaction_count,
                   fraud_event_count, confirmed_fraud_count, interaction_count,
                    last_transaction_at, customer_since, customer_age_band,
                    transaction_count_7d, transaction_count_30d,
                    transaction_count_90d, transaction_amount_7d,
                    transaction_amount_30d, transaction_amount_90d,
                    average_transaction_amount_30d,
                    declined_transaction_count_30d, decline_rate_30d,
                    distinct_merchant_count_30d, distinct_country_count_30d,
                    fraud_event_count_90d, confirmed_fraud_count_90d,
                    days_since_last_transaction, customer_tenure_days,
                    credit_utilization, delinquent_account_count, has_delinquency,
                    portfolio_segment, batch_id, updated_at, effective_at,
                    as_of_time)
                   SELECT c.customer_id, c.first_name, c.last_name, c.date_of_birth,
                          c.status, c.customer_type, c.country, c.city,
                          accounts.account_count, accounts.total_credit_limit,
                          accounts.total_balance, transactions.transaction_count,
                          transactions.transaction_amount, %s,
                          transactions.declined_transaction_count,
                          fraud.fraud_event_count, fraud.confirmed_fraud_count,
                          (SELECT count(*) FROM interactions i
                           WHERE i.customer_id = c.customer_id
                             AND i.event_time <= cutoff.as_of_time),
                          transactions.last_transaction_at, c.registered_at,
                          CASE
                            WHEN c.date_of_birth IS NULL THEN NULL
                            WHEN extract(year FROM age(cutoff.as_of_time, c.date_of_birth)) < 25 THEN 'under_25'
                            WHEN extract(year FROM age(cutoff.as_of_time, c.date_of_birth)) < 35 THEN '25_34'
                            WHEN extract(year FROM age(cutoff.as_of_time, c.date_of_birth)) < 45 THEN '35_44'
                            WHEN extract(year FROM age(cutoff.as_of_time, c.date_of_birth)) < 55 THEN '45_54'
                            WHEN extract(year FROM age(cutoff.as_of_time, c.date_of_birth)) < 65 THEN '55_64'
                            ELSE '65_plus'
                          END,
                          transactions.transaction_count_7d,
                          transactions.transaction_count_30d,
                          transactions.transaction_count_90d,
                          transactions.transaction_amount_7d,
                          transactions.transaction_amount_30d,
                          transactions.transaction_amount_90d,
                          transactions.average_transaction_amount_30d,
                          transactions.declined_transaction_count_30d,
                          transactions.decline_rate_30d,
                          transactions.distinct_merchant_count_30d,
                          transactions.distinct_country_count_30d,
                          fraud.fraud_event_count_90d,
                          fraud.confirmed_fraud_count_90d,
                          CASE WHEN transactions.last_transaction_at IS NULL THEN NULL
                               ELSE greatest(0, extract(day FROM cutoff.as_of_time - transactions.last_transaction_at))::integer
                          END,
                          CASE WHEN c.registered_at IS NULL THEN NULL
                               ELSE greatest(0, extract(day FROM cutoff.as_of_time - c.registered_at))::integer
                          END,
                          accounts.credit_utilization,
                          accounts.delinquent_account_count,
                          accounts.delinquent_account_count > 0,
                          CASE
                            WHEN accounts.delinquent_account_count > 0 THEN 'delinquent'
                            WHEN transactions.transaction_count_90d = 0 THEN 'inactive'
                            WHEN accounts.credit_utilization >= 0.75 THEN 'high_utilization'
                            WHEN accounts.credit_utilization > 0 THEN 'revolving'
                            ELSE 'no_credit'
                          END,
                          %s, now(), cutoff.as_of_time, now()
                   FROM customers c
                   CROSS JOIN LATERAL (
                     SELECT coalesce(source_event_max, now()) AS as_of_time
                     FROM batches WHERE batch_id = %s
                   ) cutoff
                   CROSS JOIN LATERAL (
                     SELECT count(*)::integer AS account_count,
                            coalesce(sum(credit_limit), 0) AS total_credit_limit,
                            coalesce(sum(balance), 0) AS total_balance,
                            count(*) FILTER (WHERE status IN ('delinquent', 'past_due'))::integer AS delinquent_account_count,
                            coalesce(sum(balance) / nullif(sum(credit_limit), 0), NULL) AS credit_utilization
                     FROM accounts WHERE customer_id = c.customer_id
                   ) accounts
                   CROSS JOIN LATERAL (
                     SELECT count(*)::integer AS transaction_count,
                            coalesce(sum(amount_base_currency) FILTER (WHERE status = 'approved'), 0) AS transaction_amount,
                            count(*) FILTER (WHERE status = 'declined')::integer AS declined_transaction_count,
                            max(event_time) AS last_transaction_at,
                            count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '7 days')::integer AS transaction_count_7d,
                            count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days')::integer AS transaction_count_30d,
                            count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '90 days')::integer AS transaction_count_90d,
                            coalesce(sum(amount_base_currency) FILTER (WHERE event_time > cutoff.as_of_time - interval '7 days' AND status = 'approved'), 0) AS transaction_amount_7d,
                            coalesce(sum(amount_base_currency) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days' AND status = 'approved'), 0) AS transaction_amount_30d,
                            coalesce(sum(amount_base_currency) FILTER (WHERE event_time > cutoff.as_of_time - interval '90 days' AND status = 'approved'), 0) AS transaction_amount_90d,
                            avg(amount_base_currency) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days' AND status = 'approved') AS average_transaction_amount_30d,
                            count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days' AND status = 'declined')::integer AS declined_transaction_count_30d,
                            count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days' AND status IN ('approved', 'declined'))::numeric / nullif(count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days' AND status IN ('approved', 'declined')), 0) AS decline_rate_30d,
                            count(DISTINCT merchant_id) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days' AND merchant_id IS NOT NULL)::integer AS distinct_merchant_count_30d,
                            count(DISTINCT country) FILTER (WHERE event_time > cutoff.as_of_time - interval '30 days' AND country IS NOT NULL)::integer AS distinct_country_count_30d
                     FROM transactions
                     WHERE customer_id = c.customer_id
                       AND event_time <= cutoff.as_of_time
                       AND coalesce(status, '') <> 'reversed'
                   ) transactions
                   CROSS JOIN LATERAL (
                     SELECT count(*)::integer AS fraud_event_count,
                            count(*) FILTER (WHERE confirmed)::integer AS confirmed_fraud_count,
                            count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '90 days')::integer AS fraud_event_count_90d,
                            count(*) FILTER (WHERE event_time > cutoff.as_of_time - interval '90 days' AND confirmed)::integer AS confirmed_fraud_count_90d
                     FROM fraud_events
                     WHERE customer_id = c.customer_id
                       AND event_time <= cutoff.as_of_time
                   ) fraud
                   ON CONFLICT (customer_id) DO UPDATE SET
                     first_name = EXCLUDED.first_name, last_name = EXCLUDED.last_name,
                     date_of_birth = EXCLUDED.date_of_birth,
                     status = EXCLUDED.status, customer_type = EXCLUDED.customer_type,
                     country = EXCLUDED.country, city = EXCLUDED.city,
                     account_count = EXCLUDED.account_count,
                     total_credit_limit = EXCLUDED.total_credit_limit,
                     total_balance = EXCLUDED.total_balance,
                     transaction_count = EXCLUDED.transaction_count,
                     transaction_amount = EXCLUDED.transaction_amount,
                     transaction_amount_currency = EXCLUDED.transaction_amount_currency,
                     declined_transaction_count = EXCLUDED.declined_transaction_count,
                     fraud_event_count = EXCLUDED.fraud_event_count,
                     confirmed_fraud_count = EXCLUDED.confirmed_fraud_count,
                     interaction_count = EXCLUDED.interaction_count,
                     last_transaction_at = EXCLUDED.last_transaction_at,
                     customer_since = EXCLUDED.customer_since,
                     customer_age_band = EXCLUDED.customer_age_band,
                     transaction_count_7d = EXCLUDED.transaction_count_7d,
                     transaction_count_30d = EXCLUDED.transaction_count_30d,
                     transaction_count_90d = EXCLUDED.transaction_count_90d,
                     transaction_amount_7d = EXCLUDED.transaction_amount_7d,
                     transaction_amount_30d = EXCLUDED.transaction_amount_30d,
                     transaction_amount_90d = EXCLUDED.transaction_amount_90d,
                     average_transaction_amount_30d = EXCLUDED.average_transaction_amount_30d,
                     declined_transaction_count_30d = EXCLUDED.declined_transaction_count_30d,
                     decline_rate_30d = EXCLUDED.decline_rate_30d,
                     distinct_merchant_count_30d = EXCLUDED.distinct_merchant_count_30d,
                     distinct_country_count_30d = EXCLUDED.distinct_country_count_30d,
                     fraud_event_count_90d = EXCLUDED.fraud_event_count_90d,
                     confirmed_fraud_count_90d = EXCLUDED.confirmed_fraud_count_90d,
                     days_since_last_transaction = EXCLUDED.days_since_last_transaction,
                     customer_tenure_days = EXCLUDED.customer_tenure_days,
                     credit_utilization = EXCLUDED.credit_utilization,
                     delinquent_account_count = EXCLUDED.delinquent_account_count,
                     has_delinquency = EXCLUDED.has_delinquency,
                     portfolio_segment = EXCLUDED.portfolio_segment,
                     batch_id = EXCLUDED.batch_id,
                     updated_at = now(), effective_at = EXCLUDED.effective_at,
                     as_of_time = now()""",
                (self.base_currency, batch_id, batch_id),
            )
            connection.execute(
                """INSERT INTO customer_snapshot_history
                   (customer_id, batch_id, effective_at, as_of_time, snapshot)
                   SELECT customer_id, batch_id, effective_at, as_of_time,
                          to_jsonb(customer_snapshots)
                   FROM customer_snapshots
                   ON CONFLICT (customer_id, batch_id) DO NOTHING"""
            )
            row = connection.execute(
                "SELECT count(*) AS count FROM customer_snapshots"
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def get_customer_snapshot(
        self, customer_id: str, as_of: datetime | None = None
    ) -> dict[str, object] | None:
        with self._connect() as connection:
            if as_of is not None:
                row = connection.execute(
                    """SELECT snapshot FROM customer_snapshot_history
                       WHERE customer_id = %s AND as_of_time <= %s
                       ORDER BY as_of_time DESC LIMIT 1""",
                    (customer_id, as_of),
                ).fetchone()
                return row["snapshot"] if row is not None else None
            return connection.execute(
                "SELECT * FROM customer_snapshots WHERE customer_id = %s",
                (customer_id,),
            ).fetchone()

    def list_customer_snapshots(
        self, as_of: datetime | None = None, limit: int = 100
    ) -> list[dict[str, object]]:
        with self._connect() as connection:
            if as_of is not None:
                rows = connection.execute(
                    """SELECT DISTINCT ON (customer_id) snapshot
                       FROM customer_snapshot_history
                       WHERE as_of_time <= %s
                       ORDER BY customer_id, as_of_time DESC
                       LIMIT %s""",
                    (as_of, limit),
                ).fetchall()
                return [row["snapshot"] for row in rows]
            return connection.execute(
                """SELECT * FROM customer_snapshots
                   ORDER BY customer_id LIMIT %s""",
                (limit,),
            ).fetchall()

    def get_summary(self) -> dict[str, object]:
        queries = {
            "customer_count": "SELECT count(*) AS value FROM customers",
            "account_count": "SELECT count(*) AS value FROM accounts",
            "transaction_count": "SELECT count(*) AS value FROM transactions",
            "fraud_event_count": "SELECT count(*) AS value FROM fraud_events",
            "confirmed_fraud_count": (
                "SELECT count(*) AS value FROM fraud_events WHERE confirmed"
            ),
            "interaction_count": "SELECT count(*) AS value FROM interactions",
            "quarantined_count": "SELECT count(*) AS value FROM quality_issues",
        }
        with self._connect() as connection:
            values: dict[str, object] = {}
            for name, query in queries.items():
                row = connection.execute(query).fetchone()
                values[name] = int(row["value"]) if row is not None else 0
            latest = connection.execute(
                """SELECT batch_id, status, accepted_count, duplicate_count,
                          quarantined_count, updated_at FROM batches
                   ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
        values["last_batch_id"] = latest["batch_id"] if latest else None
        values["last_batch_status"] = latest["status"] if latest else None
        values["last_batch_updated_at"] = latest["updated_at"] if latest else None
        values["latest_accepted_count"] = int(latest["accepted_count"]) if latest else 0
        values["latest_duplicate_count"] = (
            int(latest["duplicate_count"]) if latest else 0
        )
        values["latest_quarantined_count"] = (
            int(latest["quarantined_count"]) if latest else 0
        )
        return values

    def get_analytics_summary(self) -> dict[str, object]:
        """Return the small set of aggregates most analytics consumers need."""
        with self._connect() as connection:
            current = connection.execute(
                """WITH cutoff AS (
                         SELECT coalesce(
                             (SELECT source_event_max FROM batches
                              WHERE status IN ('COMPLETED', 'LOADED')
                              ORDER BY updated_at DESC LIMIT 1), now()
                         ) AS value
                       ), activity AS (
                         SELECT t.customer_id,
                                count(*) FILTER (
                                    WHERE t.event_time > cutoff.value - interval '30 days'
                                ) AS current_count,
                                count(*) FILTER (
                                    WHERE t.event_time > cutoff.value - interval '60 days'
                                      AND t.event_time <= cutoff.value - interval '30 days'
                                ) AS previous_count
                         FROM transactions t CROSS JOIN cutoff
                         WHERE t.event_time <= cutoff.value
                           AND coalesce(t.status, '') <> 'reversed'
                         GROUP BY t.customer_id
                       )
                       SELECT
                         (SELECT count(*) FROM customer_snapshots
                          WHERE status = 'active') AS active_customer_count,
                         (SELECT count(*) FROM activity
                          WHERE current_count > previous_count)
                           AS customers_increased_activity_30d,
                         (SELECT count(*) FROM customer_snapshots
                          WHERE coalesce(total_balance, 0) > 0)
                           AS customers_with_outstanding_balance,
                         coalesce(
                           100.0 * count(*) FILTER (WHERE credit_utilization >= 0.75)
                           / nullif(count(*), 0), 0
                         ) AS highly_utilized_percentage
                       FROM customer_snapshots"""
            ).fetchone()
            assert current is not None
            by_segment = connection.execute(
                """SELECT portfolio_segment AS label,
                          avg(average_transaction_amount_30d) AS value
                   FROM customer_snapshots
                   WHERE average_transaction_amount_30d IS NOT NULL
                   GROUP BY portfolio_segment ORDER BY portfolio_segment"""
            ).fetchall()
            by_country = connection.execute(
                """SELECT coalesce(country, 'unknown') AS label, count(*) AS count
                   FROM customer_snapshots
                   GROUP BY coalesce(country, 'unknown') ORDER BY label"""
            ).fetchall()
            trend = connection.execute(
                """SELECT batch_id, max(as_of_time) AS as_of_time,
                          count(*) AS customer_count,
                          count(*) FILTER (
                            WHERE snapshot->>'status' = 'active'
                          ) AS active_customer_count,
                          coalesce(sum(
                            nullif(snapshot->>'total_balance', '')::numeric
                          ), 0) AS total_balance,
                          avg(nullif(
                            snapshot->>'credit_utilization', ''
                          )::numeric) AS average_credit_utilization
                   FROM customer_snapshot_history
                   GROUP BY batch_id
                   ORDER BY as_of_time DESC
                   LIMIT 12"""
            ).fetchall()
        return {
            "active_customer_count": int(current["active_customer_count"] or 0),
            "customers_increased_activity_30d": int(
                current["customers_increased_activity_30d"] or 0
            ),
            "average_transaction_amount_by_segment": {
                str(row["label"]): float(row["value"]) for row in by_segment
            },
            "customers_with_outstanding_balance": int(
                current["customers_with_outstanding_balance"] or 0
            ),
            "highly_utilized_percentage": float(
                current["highly_utilized_percentage"] or 0
            ),
            "customers_by_country": [
                {"label": str(row["label"]), "count": int(row["count"])}
                for row in by_country
            ],
            "portfolio_trend": [
                {
                    "batch_id": str(row["batch_id"]),
                    "as_of_time": row["as_of_time"],
                    "customer_count": int(row["customer_count"]),
                    "active_customer_count": int(row["active_customer_count"]),
                    "total_balance": float(row["total_balance"] or 0),
                    "average_credit_utilization": (
                        float(row["average_credit_utilization"])
                        if row["average_credit_utilization"] is not None
                        else None
                    ),
                }
                for row in trend
            ],
        }

    def get_quality_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT batch_id, status, quality_status, quality_failure_reasons,
                          total_count, accepted_count, duplicate_count,
                          quarantined_count, required_field_failure_count,
                          referential_integrity_failure_count, source_event_min,
                          source_event_max, freshness_seconds, duration_seconds,
                          volume_change_rate, updated_at
                   FROM batches
                   WHERE status IN (
                       'COMPLETED', 'LOADED', 'COMPLETED_WITH_QUALITY_ISSUES',
                       'QUALITY_FAILED', 'FAILED'
                   )
                   ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
        if row is None:
            return {
                "batch_id": None,
                "batch_status": "EMPTY",
                "quality_status": "PENDING",
                "quality_failure_reasons": [],
                "total_count": 0,
                "accepted_count": 0,
                "duplicate_count": 0,
                "quarantined_count": 0,
                "required_field_completeness": 1.0,
                "referential_integrity_failure_rate": 0.0,
                "duplicate_rate": 0.0,
                "quarantine_rate": 0.0,
                "freshness_seconds": None,
                "duration_seconds": None,
                "volume_change_rate": None,
                "source_event_min": None,
                "source_event_max": None,
                "updated_at": None,
            }
        total = int(row["total_count"] or 0)
        denominator = total or 1
        batch_status = (
            "COMPLETED_WITH_QUALITY_ISSUES"
            if row["status"] == "QUALITY_FAILED"
            else row["status"]
        )
        return {
            "batch_id": row["batch_id"],
            "batch_status": batch_status,
            "quality_status": row["quality_status"],
            "quality_failure_reasons": list(row["quality_failure_reasons"] or []),
            "total_count": total,
            "accepted_count": int(row["accepted_count"] or 0),
            "duplicate_count": int(row["duplicate_count"] or 0),
            "quarantined_count": int(row["quarantined_count"] or 0),
            "required_field_completeness": max(
                0.0,
                1.0 - int(row["required_field_failure_count"] or 0) / denominator,
            ),
            "referential_integrity_failure_rate": int(
                row["referential_integrity_failure_count"] or 0
            )
            / denominator,
            "duplicate_rate": int(row["duplicate_count"] or 0) / denominator,
            "quarantine_rate": int(row["quarantined_count"] or 0) / denominator,
            "freshness_seconds": row["freshness_seconds"],
            "duration_seconds": row["duration_seconds"],
            "volume_change_rate": row["volume_change_rate"],
            "source_event_min": row["source_event_min"],
            "source_event_max": row["source_event_max"],
            "updated_at": row["updated_at"],
        }

    def get_quality_issues(
        self,
        batch_id: str | None = None,
        filename: str | None = None,
        issue_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        clauses: list[str] = []
        values: list[object] = []
        if batch_id:
            clauses.append("batch_id = %s")
            values.append(batch_id)
        if filename:
            clauses.append("filename = %s")
            values.append(filename)
        if issue_type:
            clauses.append("issue_type = %s")
            values.append(issue_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT filename, line_number, issue_type, detail "
                f"FROM quality_issues {where} ORDER BY id LIMIT %s",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

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
