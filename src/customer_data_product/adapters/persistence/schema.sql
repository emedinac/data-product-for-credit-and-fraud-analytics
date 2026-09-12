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
    declined_transaction_count INTEGER NOT NULL,
    fraud_event_count INTEGER NOT NULL,
    confirmed_fraud_count INTEGER NOT NULL,
    interaction_count INTEGER NOT NULL,
    last_transaction_at TIMESTAMPTZ,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
