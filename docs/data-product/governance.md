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

## Access and entitlements

Every API authorization decision is appended to `access_audit` with the
authenticated subject, consumer, roles, method, path, outcome, and time.
Request and response bodies, query values, bearer tokens, and PII are never
written to this audit trail. Audit records are restricted to the Privacy and
Security Owner and retained for seven years.

Consumer access is granted through a reviewed change to
`AUTH_CONSUMER_ENTITLEMENTS`. When set, it is authoritative and has this
shape: `{"subject@example.com":{"consumer":"analytics","roles":["reader"]}}`.
The consumer owner requests the minimum role required; the Data Product Owner
approves product access and the Privacy and Security Owner additionally
approves `pii_reader` or `admin`. Entitlements are removed on team departure,
role change, or expiry review. `AUTH_ROLE_BINDINGS` remains a development
compatibility mechanism and must not be used for production grants.

Roles are narrow: `reader` can access masked customer data and aggregate or
quality endpoints; `pii_reader` can access unmasked customer PII; `operator`
can upload and start processing; and `admin` is limited to product
administration. Cloud Run invocation, Cloud SQL, GCS, Secret Manager, and
Monitoring access remain assigned only to their dedicated service accounts.

## Retention and deletion

Raw uploaded files are retained for 90 days, quality issues for 180 days,
published snapshots and lineage for seven years, and access-audit records for
seven years. A legal hold overrides scheduled deletion. Deletion requests are
verified by the Privacy and Security Owner, recorded in the incident/change
log, and applied to raw storage, normalized records, current snapshots, and
history together; backups expire under the same retention window. Production
operations must schedule and evidence the purges before handling real customer
data.
