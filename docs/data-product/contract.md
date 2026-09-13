# Customer Data Product Contract

## Product

- Version: `v1`
- Grain: one record per customer in the latest successfully published batch.
- Access: `GET /v1/customers/{customer_id}`.
- Transaction history: `GET /v1/customers/{customer_id}/transactions` returns
  that customer's source transactions ordered by `event_time`, for timeline
  visualizations and investigation.
- Each transaction includes an explainable history-based `fraud_risk_score`,
  `fraud_decision`, and `fraud_risk_reasons`. The detector uses prior customer
  and account transaction behavior; it does not consume external fraud labels.
- Source batches: customer core, accounts, transactions, fraud, and customer
 interactions.
- Source ingestion: `POST /v1/customers`, `POST /v1/accounts`, `POST
  /v1/transactions`, `POST /v1/interactions`, and `POST /v1/fraud-events`.
  The fraud endpoint is reserved for external fraud feedback; evaluation
  releases do not call it.

## Customer response
The response contains the customer identifier, first and last name, date of birth, city, and normalized status, type, and country; account count, total credit limit, and total balance; transaction count, approved transaction amount, its `transaction_amount_currency`, declined transaction count, and last transaction time; fraud-event and confirmed-fraud counts; interaction count; the source `batch_id`; and the snapshot `updated_at` timestamp.

Nullable source values remain nullable. Counts are zero when no related records exist.

The response also supplies a point-in-time feature set: 7-, 30-, and 90-day
transaction counts and approved base-currency amounts; 30-day average approved
amount, declined count/rate, and distinct merchant/country counts; 90-day fraud
and confirmed-fraud counts; customer tenure, age band, days since last
transaction, utilization, delinquency, and portfolio segment. `GET
/v1/customers` returns up to 1,000 current records, or the latest retained
record per customer at `as_of`, for analytics and ML extraction.

Rolling windows end at the batch's `effective_at` source-event cutoff and only
include non-reversed transactions at or before that cutoff. Amount and average
fields include approved transactions with a converted base-currency amount;
decline rate is declined transactions divided by approved plus declined
transactions in the 30-day window, and is null when that denominator is zero.
Credit utilization is total balance divided by total credit limit and is null
when the limit is zero or absent. `has_delinquency` and
`delinquent_account_count` derive from account statuses `delinquent` and
`past_due`. Segments are, in order: `delinquent`, `inactive` (no transaction in
90 days), `high_utilization` (at least 75%), `revolving` (positive
utilization), and `no_credit`. Age bands use the snapshot cutoff.

## Units and currency

- The default base currency is `USD`, configurable with `BASE_CURRENCY`.
- `EXCHANGE_RATES` is a JSON object such as `{"EUR": 1.08, "GBP": 1.27}`. Each value is base-currency units for one source-currency unit.
- Rates are supplied by the configured `EXCHANGE_RATE_SOURCE` and described by `EXCHANGE_RATE_TIMESTAMP`.
- Non-base rates must be present, positive, timestamped, and no older than `EXCHANGE_RATE_MAX_AGE_SECONDS` (default 24 hours); future timestamps are rejected.
- Each transaction retains its source `amount` and `currency`, plus the converted amount, rate, source, and timestamp. Same-currency conversion uses rate `1`.
- Account `credit_limit` and `balance` values are treated as already being in the base currency because the account source does not provide a currency.
- Approved transaction totals are aggregated only from converted amounts and are labeled with `transaction_amount_currency`. Transactions with a missing rate remain in transaction counts but are excluded from monetary totals; no raw amounts from different currencies are added together.
- Every transaction retains the applied rate and timestamp in the warehouse, providing historical rate retention. Missing or stale rates emit `customer_data_product_exchange_rate_failures_total`; processing continues and monetary totals exclude those transactions.

## Required, nullable, and allowed values

Required output fields are `customer_id`, `account_count`, `transaction_count`,
`transaction_amount`, `transaction_amount_currency`, all count fields,
`batch_id`, `updated_at`, and `as_of_time`. Source identity and status fields
(`status`, `customer_type`, `country`) are nullable; nullable source values are
preserved as null. Monetary totals are non-null and use zero when no qualifying
records exist. `credit_utilization`, `decline_rate_30d`, `last_transaction_at`,
tenure/age fields, and effective timestamps are nullable when their inputs are
missing or undefined.

The approved normalized sets are: customer statuses `active`, `inactive`,
`blocked`, `closed`; customer types `individual`, `premium`, `business`; account
types `credit_card`, `personal_loan`, `payment_account`; account statuses
`active`, `closed`, `delinquent`, `past_due`; transaction types `purchase`,
`withdrawal`, `transfer`, `payment`, `refund`; transaction statuses `approved`,
`declined`, `reversed`; and fraud event types `suspicious_transaction`,
`account_takeover`, `card_stolen`, `identity_risk`, `chargeback`. Countries must
be ISO 3166-1 alpha-2 uppercase codes and currencies ISO 4217-style uppercase
three-letter codes. Unknown non-null values are quarantined as
`INVALID_ALLOWED_VALUE`.

## Time semantics

- `event_time` is the source-system event time.
- `arrived_at` is when the batch was registered/uploaded.
- `processing_started_at` and `processing_completed_at` bracket product
 processing time.
- `effective_at` is the latest source event time represented by a customer
 snapshot.
- `as_of_time` is when that snapshot was published and is the timestamp used
 for historical `as_of` queries.

## Update behavior and freshness SLA

The current customer endpoint serves the latest successfully published snapshot. Each published batch is also retained immutably in `customer_snapshot_history`; the endpoint accepts an optional `as_of` query parameter to retrieve the latest retained snapshot available at that time. Customer and account changes in later batches are upserted before publication, so historical snapshots retain the balance, credit-limit, utilization, delinquency, and status state observed for each batch. The current snapshot is replaceable, while history is append-only and unique per customer and batch.

The customer data product SLA is a maximum freshness of 24 hours: a successful batch must be published no more than 24 hours after its newest source event. The `freshness_seconds` quality metric measures this interval, and a batch exceeding the threshold fails the quality gate.

## Batch and lineage access

`GET /v1/batches/{batch_id}/lineage` returns the batch source, status, uploaded
filenames and storage keys, and field-level source and transformation lineage
for the customer snapshot.

`GET /v1/summary` and `GET /v1/status` return aggregate counts and the latest batch update time. `GET /ready` checks database readiness. 

`GET /v1/summary/analytics` provides purpose-built analytics aggregates:
active customers, customers whose 30-day transaction activity increased versus
the preceding 30 days, average 30-day transaction amount by portfolio segment,
customers with outstanding balances, highly-utilized percentage, customer
counts by country, and the latest 12 published portfolio trend points. This
endpoint prevents consumers from reconstructing those aggregates from every
customer snapshot.

All `/v1/*` requests require a valid OAuth bearer token. Cloud Run IAM controls service invocation, and application roles are `reader`, `operator`, `pii_reader`, and `admin`. The customer endpoint redacts first name, last name, date of birth, and city unless the caller has `pii_reader` or `admin`.

When `AUTH_CONSUMER_ENTITLEMENTS` is configured, it is the authoritative
subject-to-consumer-and-role map. Authorization decisions are retained in the
access audit trail; request values and response data are excluded.
