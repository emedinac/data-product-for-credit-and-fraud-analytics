# Governance

## Ownership

The Data Product Owner is accountable for the customer contract, prioritization,
and consumer communication. The Data Engineering Owner is responsible for the
pipeline, schema, lineage, and operational fixes. The Data Quality Owner owns
quality thresholds and accepts or rejects quality-gate exceptions. The Privacy
and Security Owner approves PII access, retention, and security changes. Each
consumer team owns its use of the product and must register breaking-change
dependencies.

## SLAs and escalation

- Freshness: the newest source event is published within 24 hours.
- Quality: quarantine and duplicate rates are at most 5%; referential-integrity
  failures are zero; required-field completeness is at least 99%.
- Availability: planned daily processing is monitored by the Engineering Owner;
  incidents affecting a consumer are acknowledged within one business hour.

Quality-gate failure or a freshness breach is first triaged by Data Engineering,
then escalated to the Data Product Owner and Data Quality Owner. PII or access
incidents are immediately escalated to Privacy and Security. A material outage
or unresolved breach is escalated to the business owner and incident manager.
The existing quality and Airflow logs are the operational evidence for triage.

## Change management

Changes to schemas, field meaning, transformations, SLAs, PII classification,
or access roles require a pull request, an updated contract and lineage entry,
an owner review, and relevant quality/API tests. Breaking changes require a
new product version and consumer notice before release. Additive nullable fields
may remain in `v1` after owner approval. Threshold-only changes require Data
Quality Owner approval and a documented reason. Emergency changes must be
recorded in the next pull request and reviewed within two business days.
