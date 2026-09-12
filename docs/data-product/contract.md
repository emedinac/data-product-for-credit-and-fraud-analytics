# Customer Data Product Contract

## Product

- Version: `v1`
- Grain: one record per customer in the latest successfully published batch.
- Access: `GET /v1/customers/{customer_id}`.
- Source batches: customer core, accounts, transactions, fraud, and customer
 interactions.

## Customer response
The response contains the customer identifier, first and last name, date of birth, city, and normalized status, type, and country; account count, total credit limit, and total balance; transaction count, approved transaction amount, its `transaction_amount_currency`, declined transaction count, and last transaction time; fraud-event and confirmed-fraud counts; interaction count; the source `batch_id`; and the snapshot `updated_at` timestamp.

Nullable source values remain nullable. Counts are zero when no related records exist.

## Units and currency

- The default base currency is `USD`, configurable with `BASE_CURRENCY`.
- `EXCHANGE_RATES` is a JSON object such as `{"EUR": 1.08, "GBP": 1.27}`. Each value is base-currency units for one source-currency unit.
- Rates are supplied by the configured `EXCHANGE_RATE_SOURCE` and described by `EXCHANGE_RATE_TIMESTAMP`.
- Each transaction retains its source `amount` and `currency`, plus the converted amount, rate, source, and timestamp. Same-currency conversion uses rate `1`.
- Account `credit_limit` and `balance` values are treated as already being in the base currency because the account source does not provide a currency.
- Approved transaction totals are aggregated only from converted amounts and are labeled with `transaction_amount_currency`. Transactions with a missing rate remain in transaction counts but are excluded from monetary totals; no raw amounts from different currencies are added together.

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

The current customer endpoint serves the latest successfully published snapshot. Each published batch is also retained immutably in `customer_snapshot_history`; the endpoint accepts an optional `as_of` query parameter to retrieve the latest retained snapshot available at that time. The current snapshot is replaceable, while history is append-only and unique per customer and batch.

The customer data product SLA is a maximum freshness of 24 hours: a successful batch must be published no more than 24 hours after its newest source event. The `freshness_seconds` quality metric measures this interval, and a batch exceeding the threshold fails the quality gate.

## Batch and lineage access

`GET /v1/batches/{batch_id}/lineage` returns the batch source, status, uploaded
filenames and storage keys, and field-level source and transformation lineage
for the customer snapshot.

`GET /v1/summary` and `GET /v1/status` return aggregate counts and the latest batch update time. `GET /ready` checks database readiness. 

All `/v1/*` requests require a valid OAuth bearer token. Cloud Run IAM controls service invocation, and application roles are `reader`, `operator`, `pii_reader`, and `admin`. The customer endpoint redacts first name, last name, date of birth, and city unless the caller has `pii_reader` or `admin`.
