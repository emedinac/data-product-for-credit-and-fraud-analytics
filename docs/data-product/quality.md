# Data Quality
The pipeline preserves raw files in landing storage and records invalid input in `quality_issues` instead of silently dropping it.
Current checks cover:
- required identifiers and required event timestamps;
- supported JSON, JSONL, and CSV file types;
- malformed records and unsupported source filenames;
- duplicate identifiers through database uniqueness constraints;
- referential integrity through database foreign keys; and
- source naming and categorical-value normalization.
Batch responses report accepted, duplicate, quarantined, and snapshot counts. The quality gate is shared by the API and Airflow and stops publication when any default threshold is breached: quarantine and duplicate rates are at most 5%, referential-integrity failures are zero, required-field completeness is at least 99%, batch volume may change by at most 50%, and the newest source event must be no more than 24 hours old at processing time. Every threshold is configurable through the matching environment variable in `Settings`.

`GET /v1/quality/summary` returns the latest batch's rates, source/event freshness, duration, volume change, status, and failure reasons. Processing also emits JSON structured metrics for batch duration, record counts, freshness, quality failures, and processing failures. Airflow emits alert logs for task failures, quality-gate failures, and freshness breaches; these logs can be routed to an email or log-based alerting backend without changing the pipeline code. 