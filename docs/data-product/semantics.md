# Data Semantics

- `first_name`, `last_name`, and `city` are trimmed source values and remain
  nullable.
- `date_of_birth` is stored and returned as a nullable calendar date.
- Transaction `merchant_id` is preserved as a trimmed source value.
- Transaction `merchant_category` is normalized to lowercase snake case.
- Transaction `country` is normalized to an uppercase country label.
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
