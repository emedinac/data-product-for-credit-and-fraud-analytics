# Data Quality

The pipeline preserves raw files in landing storage and records invalid input in `quality_issues` instead of silently dropping it.

Current checks cover:

- required identifiers and required event timestamps;
- supported JSON, JSONL, and CSV file types;
- malformed records and unsupported source filenames;
- duplicate identifiers through database uniqueness constraints;
- referential integrity through database foreign keys; and
- source naming and categorical-value normalization.

Batch responses report accepted, duplicate, quarantined, and snapshot counts. The prototype quality gate stops publication when a batch has no accepted records. It does not yet enforce percentage-based quality thresholds.
