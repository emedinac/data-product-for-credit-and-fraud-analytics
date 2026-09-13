CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'REGISTERED',
    files_count INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    quarantined_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    snapshot_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 0,
    required_field_failure_count INTEGER NOT NULL DEFAULT 0,
    referential_integrity_failure_count INTEGER NOT NULL DEFAULT 0,
    source_event_min TIMESTAMPTZ,
    source_event_max TIMESTAMPTZ,
    freshness_seconds DOUBLE PRECISION,
    duration_seconds DOUBLE PRECISION,
    volume_change_rate DOUBLE PRECISION,
    quality_status TEXT NOT NULL DEFAULT 'PENDING',
    quality_failure_reasons TEXT[] NOT NULL DEFAULT '{}',
    distribution_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    distribution_shift_score DOUBLE PRECISION,
    arrived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS batch_files (
    file_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
    filename TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL UNIQUE REFERENCES batches(batch_id),
    idempotency_key TEXT,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at TIMESTAMPTZ,
    lock_token TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_jobs_idempotency_key
    ON processing_jobs (idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_processing_jobs_ready
    ON processing_jobs (status, available_at);

CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    date_of_birth DATE,
    status TEXT,
    customer_type TEXT,
    country TEXT,
    city TEXT,
    registered_at TIMESTAMPTZ,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    account_type TEXT,
    opened_at TIMESTAMPTZ,
    credit_limit NUMERIC,
    balance NUMERIC,
    status TEXT,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    event_time TIMESTAMPTZ NOT NULL,
    amount NUMERIC NOT NULL,
    currency TEXT,
    amount_base_currency NUMERIC,
    exchange_rate NUMERIC,
    exchange_rate_source TEXT,
    exchange_rate_timestamp TIMESTAMPTZ,
    fraud_risk_score NUMERIC,
    fraud_decision TEXT,
    fraud_risk_reasons TEXT[] NOT NULL DEFAULT '{}',
    transaction_type TEXT,
    status TEXT,
    merchant_id TEXT,
    merchant_category TEXT,
    country TEXT,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS fraud_events (
    event_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    transaction_id TEXT REFERENCES transactions(transaction_id),
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT,
    severity TEXT,
    confirmed BOOLEAN NOT NULL,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS interactions (
    interaction_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    event_time TIMESTAMPTZ NOT NULL,
    channel TEXT,
    interaction_type TEXT,
    resolution TEXT,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS customer_snapshots (
    customer_id TEXT PRIMARY KEY REFERENCES customers(customer_id),
    first_name TEXT,
    last_name TEXT,
    date_of_birth DATE,
    status TEXT,
    customer_type TEXT,
    country TEXT,
    city TEXT,
    account_count INTEGER NOT NULL,
    total_credit_limit NUMERIC,
    total_balance NUMERIC,
    transaction_count INTEGER NOT NULL,
    transaction_amount NUMERIC NOT NULL,
    transaction_amount_currency TEXT NOT NULL DEFAULT 'USD',
    declined_transaction_count INTEGER NOT NULL,
    fraud_event_count INTEGER NOT NULL,
    confirmed_fraud_count INTEGER NOT NULL,
    interaction_count INTEGER NOT NULL,
    last_transaction_at TIMESTAMPTZ,
    customer_since TIMESTAMPTZ,
    customer_age_band TEXT,
    transaction_count_7d INTEGER NOT NULL DEFAULT 0,
    transaction_count_30d INTEGER NOT NULL DEFAULT 0,
    transaction_count_90d INTEGER NOT NULL DEFAULT 0,
    transaction_amount_7d NUMERIC NOT NULL DEFAULT 0,
    transaction_amount_30d NUMERIC NOT NULL DEFAULT 0,
    transaction_amount_90d NUMERIC NOT NULL DEFAULT 0,
    average_transaction_amount_30d NUMERIC,
    declined_transaction_count_30d INTEGER NOT NULL DEFAULT 0,
    decline_rate_30d NUMERIC,
    distinct_merchant_count_30d INTEGER NOT NULL DEFAULT 0,
    distinct_country_count_30d INTEGER NOT NULL DEFAULT 0,
    fraud_event_count_90d INTEGER NOT NULL DEFAULT 0,
    confirmed_fraud_count_90d INTEGER NOT NULL DEFAULT 0,
    days_since_last_transaction INTEGER,
    customer_tenure_days INTEGER,
    credit_utilization NUMERIC,
    delinquent_account_count INTEGER NOT NULL DEFAULT 0,
    has_delinquency BOOLEAN NOT NULL DEFAULT FALSE,
    portfolio_segment TEXT NOT NULL DEFAULT 'inactive',
    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at TIMESTAMPTZ,
    as_of_time TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customer_snapshot_history (
    snapshot_id BIGSERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
    effective_at TIMESTAMPTZ,
    as_of_time TIMESTAMPTZ NOT NULL,
    snapshot JSONB NOT NULL,
    UNIQUE (customer_id, batch_id)
);

CREATE TABLE IF NOT EXISTS quality_issues (
    id BIGSERIAL PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
    filename TEXT NOT NULL,
    line_number INTEGER,
    issue_type TEXT NOT NULL,
    detail TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_issues_batch_id
    ON quality_issues (batch_id);

CREATE TABLE IF NOT EXISTS access_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_subject TEXT NOT NULL,
    consumer TEXT,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('ALLOWED', 'DENIED')),
    roles TEXT[] NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_access_audit_actor_time
    ON access_audit (actor_subject, occurred_at DESC);
