# Data Semantics

- Customer status and customer type are normalized to lowercase snake case.
- Country and currency labels are normalized to uppercase.
- `account_count` counts persisted accounts for the customer.
- `total_credit_limit` and `total_balance` sum persisted account values.
- `transaction_count` counts persisted transactions, regardless of status.
- `transaction_amount` sums approved transactions only.
- `declined_transaction_count` counts transactions with status `declined`.
- `fraud_event_count` counts persisted fraud events.
- `confirmed_fraud_count` counts fraud events whose normalized confirmation is
  true.
- `interaction_count` counts persisted customer interactions.
- `last_transaction_at` is the latest persisted transaction event time.

The prototype does not currently convert currencies, calculate utilization, apply historical customer state, or provide point-in-time ML features.
