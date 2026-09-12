from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Customer:
    customer_id: str
    status: str | None
    customer_type: str | None
    country: str | None
    registered_at: datetime | None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    city: str | None = None


@dataclass(frozen=True)
class Account:
    account_id: str
    customer_id: str
    account_type: str | None
    opened_at: datetime | None
    credit_limit: Decimal | None
    balance: Decimal | None
    status: str | None


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    customer_id: str
    account_id: str
    event_time: datetime
    amount: Decimal
    currency: str | None
    transaction_type: str | None
    status: str | None
    merchant_id: str | None = None
    merchant_category: str | None = None
    country: str | None = None


@dataclass(frozen=True)
class FraudEvent:
    event_id: str
    customer_id: str
    transaction_id: str | None
    event_time: datetime
    event_type: str | None
    severity: str | None
    confirmed: bool


@dataclass(frozen=True)
class Interaction:
    interaction_id: str
    customer_id: str
    event_time: datetime
    channel: str | None
    interaction_type: str | None
    resolution: str | None


@dataclass(frozen=True)
class BatchFile:
    batch_id: str
    file_id: str
    filename: str
    storage_key: str


@dataclass(frozen=True)
class GroundTruthLabel:
    scenario_id: str
    label: str
    subtype: str | None
    confirmed: bool
    evidence_found: bool
