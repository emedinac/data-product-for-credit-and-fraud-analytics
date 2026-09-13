# Data Quality 

## Processing and operations 
Airflow runs the batch pipeline daily. The lifecycle is: register a batch, copy supported source files to landing storage, parse/normalize/validate/load, run the quality gate, and publish the customer snapshot. 
 
Batch records include status, counts, arrival, processing, creation, and update timestamps. Lineage links a published batch to its source filenames and landing storage keys. Database initialization applies the baseline schema and sorted SQL migrations. 

The product uses a 24-hour freshness SLA from the newest source event to publication. `freshness_seconds` measures this interval. Current snapshots are replaceable, while one immutable history record is retained per customer and published batch; `as_of` reads use that history. 

The pipeline preserves raw files in landing storage and records invalid input in `quality_issues` instead of silently dropping it. Current checks cover: 
- required identifiers and required event timestamps; 
- supported JSON, JSONL, and CSV file types; 
- malformed records and unsupported source filenames; 
- duplicate identifiers through database uniqueness constraints; 
- referential integrity through database foreign keys; and 
- source naming and categorical-value normalization. 
Batch responses report accepted, duplicate, quarantined, and snapshot counts. The quality gate is shared by the API and Airflow and stops publication when any default threshold is breached: quarantine and duplicate rates are at most 5%, referential-integrity failures are zero, required-field completeness is at least 99%, batch volume may change by at most 50%, and the newest source event must be no more than 24 hours old at processing time. Future-dated source events fail as `FUTURE_EVENT_TIME`. Every threshold is configurable through the matching environment variable in `Settings`. 
 
`GET /v1/quality/summary` returns the latest batch's rates, source/event freshness, duration, volume change, status, and failure reasons. Processing also emits JSON structured metrics for batch duration, record counts, freshness, quality failures, and processing failures. Airflow emits alert logs for task failures, quality-gate failures, and freshness breaches; these logs can be routed to an email or log-based alerting backend without changing the pipeline code. 

The generator also writes `metadata/quality_ground_truth.json` for the core files loaded by the demo. The Ground truth panel compares its expected record-quality counts with the latest observed batch. 

Failed quality gates do not discard the batch or return an ingestion error from the API. The batch is marked `COMPLETED_WITH_QUALITY_ISSUES`, its `quality_status` is `FAILED`, its customer snapshot is not published, and quarantined records remain available through `GET /v1/quality?batch_id=<batch_id>` for inspection. 
 
 
## Metric semantics 
 
 
- Source `event_time` is distinct from batch arrival and processing timestamps. 
- Snapshot `effective_at` is the newest source event represented; `as_of_time` 
 is publication time. 
- `account_count`, `total_credit_limit`, and `total_balance` use persisted 
 account values; account monetary values are assumed to be in the base 
 currency because the source has no account currency field. 
- `transaction_count` includes all persisted transactions. Approved 
 `transaction_amount` values are converted to the configured base currency; 
 transactions without a usable rate are excluded from that total. 
- Names and cities are trimmed; categorical labels use normalized snake case, 
 while country and currency labels are uppercase. 
- Fraud and interaction counts count persisted related records. 
 
 
Customer and account records are upserted when a later batch contains changed
state. Each successful publication stores an immutable customer-level portfolio
snapshot in `customer_snapshot_history`, including balance, credit limit,
utilization, delinquency, and status. Consumers can use the customer endpoint's
`as_of` parameter to compare those values across batches; this is batch-level
history rather than event-level account versioning.
