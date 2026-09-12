# Operations

Airflow runs the batch pipeline daily. The batch lifecycle is:

1. Register a batch.
2. Copy supported source files to landing storage.
3. Parse, normalize, validate, and load records.
4. Run the quality gate.
5. Publish the customer snapshot.

The batch record provides status, counts, creation time, and update time. The lineage endpoint links a published batch to its source filenames and landing storage keys.

Quality thresholds are configured with `MAX_QUARANTINE_RATE` and
`MAX_DUPLICATE_RATE`. Their default is `1.0` for prototype compatibility; a
deployment can lower them to enforce stricter publication rules. `API_KEY`
enables the simple internal API-key check.

Database initialization applies the baseline schema and then records sorted SQL migrations in `schema_migrations`.

Freshness currently means the update time of the latest successful batch. The synthetic generator includes late-arriving data, but this prototype does not measure a source-arrival SLA or provide automated alerts.

The prototype is intended for trusted internal deployment. Historical/as-of queries, slowly changing dimensions, streaming ingestion, enterprise IAM, automated catalogs, dashboards, and SLA alerting are out of scope for `v1`.
