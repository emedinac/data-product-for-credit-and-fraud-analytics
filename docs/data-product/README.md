# Customer Data Product

This directory documents the deployable prototype of the PayFlow customer data product. It provides a customer-level snapshot assembled from customer, account, transaction, fraud, and customer-interaction source files.

- [Contract](contract.md): product grain, API fields, and version.
- [Quality and operations](quality.md): normalization, validation, batches,
  lineage, freshness, and limitations.
- [Governance](governance.md): ownership, SLAs, escalation, and change control.

The current product is a daily batch prototype. It provides retained customer/batch snapshots and historical `as_of` reads, but does not provide streaming ingestion, enterprise identity management, or automated SLA alerting.
