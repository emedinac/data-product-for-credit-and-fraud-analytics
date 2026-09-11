# Customer Data Product Contract

## Product

- Version: `v1`
- Grain: one record per customer in the latest successfully published batch.
- Access: `GET /v1/customers/{customer_id}`.
- Source batches: customer core, accounts, transactions, fraud, and customer
  interactions.

## Customer response

The response contains the customer identifier and normalized status, type, and country; account count, total credit limit, and total balance; transaction count, approved transaction amount, declined transaction count, and last transaction time; fraud-event and confirmed-fraud counts; interaction count; the source `batch_id`; and the snapshot `updated_at` timestamp.

Nullable source values remain nullable. Counts are zero when no related records exist. Amounts are stored as numeric values in the source currency and are not converted across currencies by this prototype.

## Batch and lineage access

`GET /v1/batches/{batch_id}/lineage` returns the batch source, status, and the uploaded filenames and storage keys used to produce the batch.
