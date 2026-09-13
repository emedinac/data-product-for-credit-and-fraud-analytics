"""Approved values for the v1 customer data product contract."""

CUSTOMER_STATUSES = frozenset({"active", "inactive", "blocked", "closed"})
CUSTOMER_TYPES = frozenset({"individual", "premium", "business"})
ACCOUNT_TYPES = frozenset({"credit_card", "personal_loan", "payment_account"})
ACCOUNT_STATUSES = frozenset({"active", "closed", "delinquent", "past_due"})
TRANSACTION_TYPES = frozenset(
    {"purchase", "withdrawal", "transfer", "payment", "refund"}
)
TRANSACTION_STATUSES = frozenset({"approved", "declined", "reversed"})
FRAUD_TYPES = frozenset(
    {
        "suspicious_transaction",
        "account_takeover",
        "card_stolen",
        "identity_risk",
        "chargeback",
    }
)


def is_country(value: str) -> bool:
    """Countries use ISO 3166-1 alpha-2 codes in the output contract."""
    return len(value) == 2 and value.isalpha() and value.isupper()


def is_currency(value: str) -> bool:
    """Currencies use ISO 4217-style three-letter codes."""
    return len(value) == 3 and value.isalpha() and value.isupper()
