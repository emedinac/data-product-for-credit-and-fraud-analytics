# Customer Data Product

This directory documents the deployable prototype of the PayFlow customer data product. It provides a customer-level snapshot assembled from customer, account, transaction, fraud, and customer-interaction source files.

- [Contract](contract.md): product grain, API fields, and version.
- [Semantics](semantics.md): definitions used by the current metrics.
- [Quality](quality.md): normalization, validation, and quarantine behavior.
- [Operations](operations.md): batches, lineage, freshness, and limitations.

The current product is a daily batch prototype. It does not provide historical as-of views, streaming ingestion, enterprise identity management, or automated SLA alerting.
