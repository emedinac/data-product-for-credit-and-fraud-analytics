"""
PayFlow synthetic RAW data generator.

Purpose:
    Generate intentionally messy, semi-structured and unstructured financial
    source data for practicing end-to-end ETL / data engineering.

The generator deliberately creates source-system complexity rather than
clean analytical tables.

It produces:

    - JSON
    - JSONL
    - nested JSON
    - CSV with schema drift
    - application logs
    - customer-support text
    - transaction events
    - fraud events
    - account events
    - payment events
    - chargebacks
    - loan events
    - card events
    - customer interactions
    - authentication events
    - device events
    - multiple source systems
    - mixed date formats
    - mixed currencies
    - different monetary representations
    - duplicated records
    - duplicated files
    - late-arriving events
    - out-of-order events
    - malformed records
    - missing fields
    - unknown IDs
    - inconsistent IDs
    - inconsistent naming
    - inconsistent casing
    - inconsistent categorical values
    - schema drift
    - PII mixed into raw data
    - nested PII
    - multiple events inside one file
    - files containing multiple schemas
    - inconsistent delimiters
    - inconsistent encodings
    - application errors
    - retries
    - failed API calls
    - suspicious transaction patterns
    - account takeover scenarios
    - impossible transactions
    - duplicate payments
    - chargeback scenarios
    - high-risk customers
    - high-risk devices
    - high-risk merchants
    - geographic anomalies
    - velocity anomalies
    - customer state changes
    - account state changes
    - temporal inconsistencies
    - referential-integrity problems
    - source-specific identifiers
    - source-specific semantics
    - batch/file metadata
    - ground-truth fraud labels
    - ground-truth anomaly labels
    - ground-truth data-quality labels

The generated data is RAW.

Do not clean it here.

The purpose is to make the downstream system discover, reconcile,
validate, standardize, enrich and expose the data.

Example:

    python fake_data_generation.py \
        --records 10000000 \
        --customers 500000 \
        --output ./raw \
        --seed 42

Small development run:

    python fake_data_generation.py \
        --records 10000 \
        --customers 1000 \
        --output ./raw_dev \
        --seed 42

Higher-quality-chaos run:

    python fake_data_generation.py \
        --records 10000000 \
        --customers 500000 \
        --output ./raw \
        --seed 42 \
        --duplicate-rate 0.03 \
        --missing-rate 0.02 \
        --malformed-rate 0.005 \
        --unknown-id-rate 0.003 \
        --late-rate 0.05 \
        --schema-drift-rate 0.10 \
        --fraud-rate 0.015 \
        --pii-rate 0.80


Logical records by default:

    Customers
    Accounts
    Transactions
    Fraud events
    Customer interactions
    Authentication events
    Device events
    Payments
    Chargebacks
    Loans
    Card events
    Application events
    Support tickets

The total logical event count is controlled by --records.
Customer and account master records are generated in addition to the
event count.


Output:

raw/
├── customer_core/
├── accounts/
├── payments/
├── transactions/
├── fraud/
├── chargebacks/
├── loans/
├── cards/
├── customer_service/
├── authentication/
├── devices/
├── application_logs/
├── mixed_events/
├── metadata/
└── ground_truth/
"""

import argparse
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from faker import Faker

# ============================================================
# CONFIGURATION
# ============================================================

COUNTRIES = [
    "US",
    "BR",
    "MX",
    "CA",
    "GB",
    "ES",
    "DE",
    "FR",
    "AR",
    "CL",
    "CO",
    "PT",
    "IT",
]

CURRENCIES = [
    "USD",
    "BRL",
    "MXN",
    "CAD",
    "EUR",
    "GBP",
    "ARS",
    "CLP",
    "COP",
]

MERCHANT_CATEGORIES = [
    "grocery",
    "restaurant",
    "travel",
    "fuel",
    "electronics",
    "health",
    "entertainment",
    "utilities",
    "retail",
    "online_services",
    "gaming",
    "education",
    "insurance",
    "government",
    "crypto",
    "cash_advance",
]

TRANSACTION_TYPES = [
    "purchase",
    "withdrawal",
    "transfer",
    "payment",
    "refund",
    "cash_deposit",
    "cash_withdrawal",
    "recurring_payment",
    "international_transfer",
    "card_present",
    "card_not_present",
]

TRANSACTION_STATUSES = [
    "approved",
    "declined",
    "reversed",
    "pending",
    "cancelled",
    "expired",
    "processing",
]

CUSTOMER_STATUSES = [
    "active",
    "inactive",
    "blocked",
    "closed",
    "pending_verification",
    "under_review",
    "suspended",
]

CUSTOMER_TYPES = [
    "individual",
    "premium",
    "business",
    "student",
    "employee",
    "high_net_worth",
]

ACCOUNT_TYPES = [
    "credit_card",
    "personal_loan",
    "mortgage",
    "payment_account",
    "checking",
    "savings",
    "business_account",
    "investment_account",
    "overdraft",
    "line_of_credit",
]

ACCOUNT_STATUSES = [
    "ACTIVE",
    "BLOCKED",
    "CLOSED",
    "PENDING",
    "DEFAULTED",
    "FROZEN",
    "DORMANT",
]

FRAUD_TYPES = [
    "suspicious_transaction",
    "account_takeover",
    "card_stolen",
    "identity_risk",
    "chargeback",
    "synthetic_identity",
    "credential_stuffing",
    "payment_fraud",
    "friendly_fraud",
    "merchant_fraud",
    "money_laundering",
    "first_party_fraud",
    "application_fraud",
]

FRAUD_SEVERITIES = [
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]

INTERACTION_CHANNELS = [
    "APP",
    "WEB",
    "PHONE",
    "EMAIL",
    "BRANCH",
    "WHATSAPP",
    "CHAT",
    "SMS",
    "SOCIAL_MEDIA",
]

INTERACTION_TYPES = [
    "support",
    "complaint",
    "payment_question",
    "fraud_report",
    "account_change",
    "product_question",
    "card_activation",
    "limit_increase",
    "address_change",
    "identity_verification",
    "chargeback_request",
    "loan_question",
    "transaction_dispute",
    "password_reset",
    "account_closure",
    "fee_question",
]

DEVICE_TYPES = [
    "mobile",
    "tablet",
    "desktop",
    "pos",
    "atm",
    "unknown",
]

OPERATING_SYSTEMS = [
    "ios",
    "android",
    "windows",
    "macos",
    "linux",
    "unknown",
]

AUTH_METHODS = [
    "password",
    "biometric",
    "otp",
    "sms_otp",
    "email_otp",
    "passkey",
    "unknown",
]

AUTH_RESULTS = [
    "success",
    "failure",
    "locked",
    "challenged",
    "expired",
]

LOAN_TYPES = [
    "personal",
    "auto",
    "mortgage",
    "student",
    "business",
]

CARD_TYPES = [
    "visa",
    "mastercard",
    "amex",
    "virtual",
    "prepaid",
]

CARD_EVENTS = [
    "issued",
    "activated",
    "blocked",
    "unblocked",
    "replaced",
    "expired",
    "lost",
    "stolen",
    "pin_changed",
]

CHARGEBACK_REASONS = [
    "duplicate_charge",
    "fraudulent_transaction",
    "product_not_received",
    "product_not_as_described",
    "processing_error",
    "subscription_cancelled",
    "unknown",
]


# ============================================================
# ARGUMENTS
# ============================================================


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--records",
        type=int,
        default=10_000_000,
        help="Number of logical event records.",
    )

    parser.add_argument(
        "--customers",
        type=int,
        default=500_000,
    )

    parser.add_argument(
        "--output",
        type=str,
        default="./raw",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    parser.add_argument(
        "--duplicate-rate",
        type=float,
        default=0.03,
    )

    parser.add_argument(
        "--missing-rate",
        type=float,
        default=0.02,
    )

    parser.add_argument(
        "--malformed-rate",
        type=float,
        default=0.005,
    )

    parser.add_argument(
        "--unknown-id-rate",
        type=float,
        default=0.003,
    )

    parser.add_argument(
        "--late-rate",
        type=float,
        default=0.05,
    )

    parser.add_argument(
        "--out-of-order-rate",
        type=float,
        default=0.04,
    )

    parser.add_argument(
        "--schema-drift-rate",
        type=float,
        default=0.10,
    )

    parser.add_argument(
        "--pii-rate",
        type=float,
        default=0.80,
    )

    parser.add_argument(
        "--fraud-rate",
        type=float,
        default=0.015,
    )

    parser.add_argument(
        "--anomaly-rate",
        type=float,
        default=0.02,
    )

    parser.add_argument(
        "--file-size",
        type=int,
        default=50_000,
    )

    parser.add_argument(
        "--duplicate-file-rate",
        type=float,
        default=0.03,
    )

    return parser.parse_args()


# ============================================================
# HELPERS
# ============================================================


def chance(probability):
    return random.random() < probability


def random_id(prefix):
    # Use the seeded PRNG instead of uuid4(), otherwise --seed cannot fully
    # reproduce a generated dataset.
    return f"{prefix}_{random.getrandbits(48):012x}"


def random_date(
    start_year=2024,
    end_year=2026,
):
    start = datetime(
        start_year,
        1,
        1,
        tzinfo=timezone.utc,
    )

    end = datetime(
        end_year,
        12,
        31,
        23,
        59,
        59,
        tzinfo=timezone.utc,
    )

    seconds = int((end - start).total_seconds())

    return start + timedelta(seconds=random.randint(0, seconds))


def mixed_date(dt):
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ]

    value = dt.strftime(random.choice(formats))

    if chance(0.05):
        value += random.choice([
            "Z",
            "+00:00",
            "-03:00",
            "+01:00",
            "-05:00",
        ])

    return value


def random_amount():
    amount = random.lognormvariate(
        3.5,
        1.2,
    )

    return round(
        max(
            0.01,
            amount,
        ),
        2,
    )


def mixed_currency_amount():
    currency = random.choice(CURRENCIES)

    amount = random_amount()

    representation = random.randint(
        1,
        7,
    )

    if representation == 1:
        return f"{amount:.2f} {currency}"

    if representation == 2:
        return f"{currency} {amount:.2f}"

    if representation == 3:
        return {
            "currency": currency,
            "amount": amount,
        }

    if representation == 4:
        return {
            "amount": amount,
            "currency_code": currency,
        }

    if representation == 5:
        return f"{amount:,.2f} {currency}"

    if representation == 6:
        return {
            "value": f"{amount:.2f}",
            "ccy": currency,
        }

    return {
        "currency": currency,
        "amount": amount,
        "minor_units": int(amount * 100),
    }


def mixed_boolean(value):
    if value:
        return random.choice([
            True,
            "true",
            "TRUE",
            "yes",
            "Y",
            1,
        ])

    return random.choice([
        False,
        "false",
        "FALSE",
        "no",
        "N",
        0,
    ])


def inconsistent_case(value):
    option = random.randint(
        1,
        5,
    )

    if option == 1:
        return value.lower()

    if option == 2:
        return value.upper()

    if option == 3:
        return value.title()

    if option == 4:
        return value.replace(
            "_",
            "-",
        )

    return value


def maybe_missing(record, fields, rate):
    if not chance(rate):
        return

    if not fields:
        return

    field = random.choice(fields)

    record.pop(
        field,
        None,
    )


def maybe_schema_drift(
    record,
    args,
):
    if not chance(args.schema_drift_rate):
        return

    mappings = [
        ("customer_id", "customerId"),
        ("customerId", "customer_id"),
        ("account_id", "accountId"),
        ("accountId", "account_id"),
        ("transaction_id", "transactionId"),
        ("event_time", "eventTimestamp"),
        ("timestamp", "event_time"),
        ("status", "state"),
        ("country", "country_code"),
        ("type", "event_type"),
    ]

    source, target = random.choice(mappings)

    if source in record:
        record[target] = record.pop(source)


def maybe_unknown_id(
    record,
    args,
):
    if not chance(args.unknown_id_rate):
        return

    possible_fields = [
        "customer_id",
        "customerId",
        "account_id",
        "accountId",
        "transaction_id",
        "transactionId",
        "device_id",
        "merchant_id",
    ]

    available = [field for field in possible_fields if field in record]

    if available:
        field = random.choice(available)

        prefix = field.upper().replace(
            "_ID",
            "",
        )

        record[field] = f"UNKNOWN_{prefix}_{random.getrandbits(32):08x}"


def corrupt_record(
    record,
    args,
):
    record = dict(record)

    maybe_unknown_id(
        record,
        args,
    )

    maybe_missing(
        record,
        list(record.keys()),
        args.missing_rate,
    )

    maybe_schema_drift(
        record,
        args,
    )

    return record


# ============================================================
# CUSTOMER
# ============================================================


def generate_customer(
    fake,
    customer_id,
    args,
):
    created = random_date()

    customer = {
        "customerId": customer_id,
        "firstName": fake.first_name(),
        "last_name": fake.last_name(),
        "dateOfBirth": fake.date_of_birth(
            minimum_age=18,
            maximum_age=85,
        ).isoformat(),
        "country": random.choice(COUNTRIES),
        "city": fake.city(),
        "registered_at": mixed_date(created),
        "status": random.choice(CUSTOMER_STATUSES),
        "customer_type": random.choice(CUSTOMER_TYPES),
        "risk_profile": random.choice([
            "low",
            "medium",
            "high",
            "unknown",
        ]),
        "kyc": {
            "status": random.choice([
                "verified",
                "pending",
                "failed",
                "expired",
            ]),
            "verification_level": random.choice([
                "basic",
                "standard",
                "enhanced",
            ]),
        },
        "marketing": {
            "email_opt_in": mixed_boolean(chance(0.65)),
            "sms_opt_in": mixed_boolean(chance(0.45)),
        },
    }

    if chance(args.pii_rate):
        customer["email"] = fake.email()

        customer["phone"] = fake.phone_number()

        customer["national_id"] = fake.bothify(text="###.###.###-##")

        customer["address"] = {
            "street": fake.street_address(),
            "city": customer["city"],
            "postal_code": fake.postcode(),
            "country": customer["country"],
        }

    if chance(args.missing_rate):
        maybe_missing(
            customer,
            [
                "city",
                "country",
                "dateOfBirth",
                "email",
                "phone",
                "national_id",
            ],
            1.0,
        )

    if chance(0.20):
        customer["status"] = inconsistent_case(customer["status"])

    if chance(0.15):
        customer["customer_type"] = inconsistent_case(customer["customer_type"])

    maybe_schema_drift(
        customer,
        args,
    )

    return customer


# ============================================================
# ACCOUNT
# ============================================================


def generate_account(
    customer_id,
):
    opening = random_date()

    account_type = random.choice(ACCOUNT_TYPES)

    account = {
        "account_id": random_id("ACC"),
        "customer_id": customer_id,
        "type": account_type,
        "opened": mixed_date(opening),
        "status": random.choice(ACCOUNT_STATUSES),
        "credit_limit": round(
            random.uniform(
                500,
                150_000,
            ),
            2,
        ),
        "balance": round(
            random.uniform(
                -500,
                100_000,
            ),
            2,
        ),
        "available_balance": round(
            random.uniform(
                0,
                100_000,
            ),
            2,
        ),
        "interest_rate": round(
            random.uniform(
                0.0,
                45.0,
            ),
            4,
        ),
        "branch": random.randint(
            1,
            9999,
        ),
    }

    if account_type in [
        "personal_loan",
        "mortgage",
        "auto",
        "student",
        "business_account",
    ]:
        account["loan"] = {
            "principal": round(
                random.uniform(
                    1_000,
                    500_000,
                ),
                2,
            ),
            "term_months": random.choice([
                12,
                24,
                36,
                48,
                60,
                120,
                240,
            ]),
            "monthly_payment": round(
                random.uniform(
                    50,
                    8_000,
                ),
                2,
            ),
            "delinquency_days": random.choice([
                0,
                0,
                0,
                5,
                15,
                30,
                60,
                90,
            ]),
        }

    if chance(0.10):
        account["status"] = inconsistent_case(account["status"])

    return account


# ============================================================
# TRANSACTION
# ============================================================


def generate_transaction(
    customer_id,
    account_id,
    device_id=None,
    merchant_id=None,
    force_anomaly=False,
):
    event_time = random_date()

    amount = random_amount()

    if force_anomaly:
        amount *= random.uniform(
            10,
            100,
        )

    transaction_type = random.choice(TRANSACTION_TYPES)

    transaction = {
        "event_type": "transaction",
        "transaction_id": random_id("TX"),
        "customer_id": customer_id,
        "account_id": account_id,
        "event_time": mixed_date(event_time),
        "transaction": {
            "type": transaction_type,
            "amount": mixed_currency_amount(),
            "merchant": {
                "id": merchant_id or random_id("MER"),
                "category": random.choice(MERCHANT_CATEGORIES),
            },
            "country": random.choice(COUNTRIES),
            "channel": random.choice([
                "card",
                "bank_transfer",
                "cash",
                "online",
                "mobile",
                "atm",
            ]),
        },
        "status": random.choice(TRANSACTION_STATUSES),
        "device_id": device_id or random_id("DEV"),
    }

    if force_anomaly:
        transaction["risk"] = {
            "velocity_spike": True,
            "unusual_amount": True,
            "unusual_country": True,
        }

    return transaction


# ============================================================
# PAYMENT
# ============================================================


def generate_payment(
    customer_id,
    account_id,
):
    timestamp = random_date()

    return {
        "event_type": "payment",
        "payment_id": random_id("PAY"),
        "customer_id": customer_id,
        "account_id": account_id,
        "timestamp": mixed_date(timestamp),
        "amount": mixed_currency_amount(),
        "method": random.choice([
            "bank_transfer",
            "debit_card",
            "credit_card",
            "direct_debit",
            "cash",
            "pix",
            "ach",
            "wire",
        ]),
        "status": random.choice([
            "initiated",
            "processing",
            "completed",
            "failed",
            "reversed",
        ]),
        "reference": random_id("REF"),
    }


# ============================================================
# FRAUD
# ============================================================


def generate_fraud_event(
    customer_id,
    transaction_id,
    force_positive=False,
):
    event_time = random_date()

    fraud_type = random.choice(FRAUD_TYPES)

    confirmed = force_positive or chance(0.12)

    return {
        "event_type": "fraud_event",
        "event_id": random_id("FRAUD"),
        "customer_id": customer_id,
        "transaction_id": transaction_id,
        "timestamp": mixed_date(event_time),
        "classification": {
            "type": fraud_type,
            "severity": random.choice(FRAUD_SEVERITIES),
            "confirmed": confirmed,
            "model_score": round(
                random.random(),
                6,
            ),
            "analyst_decision": (
                random.choice([
                    "confirmed_fraud",
                    "false_positive",
                    "needs_review",
                    "unknown",
                ])
                if confirmed
                else "unknown"
            ),
        },
        "signals": {
            "velocity": random.choice([
                "normal",
                "elevated",
                "high",
            ]),
            "geo_distance": round(
                random.uniform(
                    0,
                    10_000,
                ),
                2,
            ),
            "device_change": chance(0.15),
            "merchant_risk": random.choice([
                "low",
                "medium",
                "high",
            ]),
        },
    }


# ============================================================
# CHARGEBACK
# ============================================================


def generate_chargeback(
    customer_id,
    transaction_id,
):
    return {
        "event_type": "chargeback",
        "chargeback_id": random_id("CB"),
        "customer_id": customer_id,
        "transaction_id": transaction_id,
        "created_at": mixed_date(random_date()),
        "reason": random.choice(CHARGEBACK_REASONS),
        "amount": mixed_currency_amount(),
        "status": random.choice([
            "opened",
            "under_review",
            "accepted",
            "rejected",
            "won",
            "lost",
        ]),
        "evidence": {
            "merchant_response": chance(0.60),
            "customer_statement": chance(0.80),
            "documentation": chance(0.45),
        },
    }


# ============================================================
# DEVICE
# ============================================================


def generate_device(
    customer_id,
):
    first_seen = random_date()

    return {
        "event_type": "device_registration",
        "device_id": random_id("DEV"),
        "customer_id": customer_id,
        "first_seen": mixed_date(first_seen),
        "device_type": random.choice(DEVICE_TYPES),
        "os": random.choice(OPERATING_SYSTEMS),
        "browser": random.choice([
            "chrome",
            "safari",
            "firefox",
            "edge",
            "unknown",
        ]),
        "ip_address": fake_ip(),
        "country": random.choice(COUNTRIES),
        "trusted": mixed_boolean(chance(0.75)),
    }


def fake_ip():
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


# ============================================================
# AUTHENTICATION
# ============================================================


def generate_authentication(
    customer_id,
    device_id=None,
):
    timestamp = random_date()

    result = random.choice(AUTH_RESULTS)

    return {
        "event_type": "authentication",
        "auth_event_id": random_id("AUTH"),
        "customer_id": customer_id,
        "device_id": device_id or random_id("DEV"),
        "timestamp": mixed_date(timestamp),
        "method": random.choice(AUTH_METHODS),
        "result": result,
        "ip_address": fake_ip(),
        "country": random.choice(COUNTRIES),
        "attempt_number": random.randint(
            1,
            6,
        ),
    }


# ============================================================
# CARD EVENT
# ============================================================


def generate_card_event(
    customer_id,
    account_id,
):
    return {
        "event_type": "card_event",
        "card_event_id": random_id("CARD_EVT"),
        "customer_id": customer_id,
        "account_id": account_id,
        "card_id": random_id("CARD"),
        "timestamp": mixed_date(random_date()),
        "card_type": random.choice(CARD_TYPES),
        "event": random.choice(CARD_EVENTS),
        "last_four": str(
            random.randint(
                0,
                9999,
            )
        ).zfill(4),
    }


# ============================================================
# LOAN EVENT
# ============================================================


def generate_loan_event(
    customer_id,
    account_id,
):
    return {
        "event_type": "loan_event",
        "loan_event_id": random_id("LOAN_EVT"),
        "customer_id": customer_id,
        "account_id": account_id,
        "timestamp": mixed_date(random_date()),
        "loan_type": random.choice(LOAN_TYPES),
        "event": random.choice([
            "application",
            "approved",
            "rejected",
            "funded",
            "payment",
            "delinquent",
            "defaulted",
            "closed",
        ]),
        "amount": mixed_currency_amount(),
        "credit_score": random.randint(
            300,
            850,
        ),
    }


# ============================================================
# CUSTOMER INTERACTION
# ============================================================


def generate_interaction(
    customer_id,
):
    event_time = random_date()

    interaction_type = random.choice(INTERACTION_TYPES)

    return {
        "event_type": "customer_interaction",
        "interaction_id": random_id("INT"),
        "customer_id": customer_id,
        "timestamp": mixed_date(event_time),
        "channel": random.choice(INTERACTION_CHANNELS),
        "interaction": {
            "type": interaction_type,
            "resolution": random.choice([
                "resolved",
                "pending",
                "escalated",
                "no_action",
                "transferred",
                "duplicate",
            ]),
            "duration_seconds": random.randint(
                5,
                3600,
            ),
        },
        "sentiment": random.choice([
            "positive",
            "neutral",
            "negative",
            "angry",
            "unknown",
        ]),
    }


# ============================================================
# SUPPORT TEXT
# ============================================================


def generate_support_text(
    fake,
    customer_id,
):
    subjects = [
        "Card declined",
        "Unknown transaction",
        "Duplicate payment",
        "Credit limit request",
        "Suspicious account activity",
        "Unable to access account",
        "Chargeback request",
        "Payment missing",
        "Wrong exchange rate",
        "Cash withdrawal dispute",
        "Loan payment question",
        "Account closure request",
    ]

    text_templates = [
        "Customer reports that their card was declined several times.",
        "Customer reports an unknown transaction on their account.",
        "Customer believes they were charged twice.",
        "Customer says the payment is missing.",
        "Customer reports suspicious activity while travelling.",
        "Customer cannot access the mobile application.",
        "Customer is requesting a chargeback.",
        "Customer says the exchange rate appears incorrect.",
        "Customer says the cash withdrawal was not made by them.",
        "Customer wants to understand their outstanding balance.",
    ]

    subject = random.choice(subjects)

    body = random.choice(text_templates)

    if chance(0.40):
        body += " " + fake.paragraph(
            nb_sentences=random.randint(
                1,
                4,
            )
        )

    return (
        f"Ticket ID: {random_id("TICKET")}\n"
        f"Customer: {customer_id}\n"
        f"Created: {mixed_date(random_date())}\n"
        f"Channel: {random.choice(INTERACTION_CHANNELS)}\n"
        f"Priority: {random.choice(["LOW", "MEDIUM", "HIGH", "URGENT"])}\n"
        f"Subject: {subject}\n"
        f"Language: {random.choice(["en", "pt", "es", "fr"])}\n\n"
        f"{body}\n"
    )


# ============================================================
# APPLICATION LOGS
# ============================================================


def generate_application_log(
    customer_id=None,
):
    timestamp = random_date()

    level = random.choices(
        [
            "INFO",
            "DEBUG",
            "WARN",
            "ERROR",
            "CRITICAL",
        ],
        weights=[
            65,
            15,
            15,
            4,
            1,
        ],
    )[0]

    messages = {
        "INFO": [
            "payment processed",
            "customer profile loaded",
            "account lookup completed",
            "transaction accepted",
            "authentication successful",
        ],
        "DEBUG": [
            "cache lookup",
            "database query",
            "risk score calculated",
            "customer feature lookup",
        ],
        "WARN": [
            "slow downstream response",
            "retrying payment provider",
            "customer profile incomplete",
            "unexpected fraud response",
            "high authentication failure rate",
        ],
        "ERROR": [
            "database connection timeout",
            "payment provider unavailable",
            "fraud service unavailable",
            "failed to serialize transaction",
            "customer service API timeout",
        ],
        "CRITICAL": [
            "payment processor unavailable",
            "database unavailable",
            "authentication provider unavailable",
        ],
    }

    message = random.choice(messages[level])

    style = random.randint(
        1,
        7,
    )

    if style == 1:
        return (
            f"{timestamp.isoformat()} "
            f"[{level}] "
            f"customer_id={customer_id} "
            f'message="{message}"'
        )

    if style == 2:
        return (
            f"{mixed_date(timestamp)} | "
            f"{level} | "
            f"customer={customer_id} | "
            f"{message}"
        )

    if style == 3:
        return json.dumps({
            "timestamp": mixed_date(timestamp),
            "level": level,
            "customer": customer_id,
            "message": message,
        })

    if style == 4:
        return (
            f"{timestamp.strftime("%Y-%m-%d %H:%M:%S")} "
            f"{level} {message} "
            f"cid={customer_id} "
            f"request_id={random_id("REQ")}"
        )

    if style == 5:
        return (
            f"{timestamp.strftime("%d/%m/%Y %H:%M:%S")};"
            f"{level};"
            f"{customer_id};"
            f"{message}"
        )

    if style == 6:
        return (
            f"timestamp={mixed_date(timestamp)} "
            f"severity={level.lower()} "
            f"cid={customer_id} "
            f"msg='{message}'"
        )

    service = random.choice(["payments", "fraud", "accounts", "auth", "customer"])
    return (
        f"{timestamp.isoformat()} "
        f"{level} "
        f"service={service} "
        f"request={random_id("REQ")} "
        f"customer={customer_id} "
        f"message={message}"
    )


# ============================================================
# ANOMALOUS SCENARIOS
# ============================================================


def generate_fraud_scenario(
    customer_id,
    account_id,
):
    """
    Creates several related records representing a realistic fraud pattern.

    These records are deliberately correlated so downstream systems can
    discover the scenario rather than simply detecting an isolated bad row.
    """

    scenario_id = random_id("SCENARIO")

    device_a = random_id("DEV")
    device_b = random_id("DEV")

    merchant_a = random_id("MER")

    base_time = random_date()

    records = []

    # Successful login from normal device.
    records.append({
        "event_type": "authentication",
        "scenario_id": scenario_id,
        "ground_truth_scenario": "account_takeover",
        "customer_id": customer_id,
        "device_id": device_a,
        "timestamp": mixed_date(base_time),
        "method": "password",
        "result": "success",
        "ip_address": fake_ip(),
        "country": "US",
    })

    # New device.
    records.append({
        "event_type": "authentication",
        "scenario_id": scenario_id,
        "ground_truth_scenario": "account_takeover",
        "customer_id": customer_id,
        "device_id": device_b,
        "timestamp": mixed_date(base_time + timedelta(minutes=2)),
        "method": "password",
        "result": "success",
        "ip_address": fake_ip(),
        "country": random.choice([
            "RU",
            "NG",
            "CN",
            "TR",
        ]),
    })

    transaction_id = random_id("TX")

    # Large transaction.
    records.append({
        "event_type": "transaction",
        "scenario_id": scenario_id,
        "ground_truth_scenario": "account_takeover",
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "account_id": account_id,
        "event_time": mixed_date(base_time + timedelta(minutes=5)),
        "transaction": {
            "type": "purchase",
            "amount": {
                "currency": "USD",
                "amount": round(
                    random.uniform(
                        5_000,
                        30_000,
                    ),
                    2,
                ),
            },
            "merchant": {
                "id": merchant_a,
                "category": "electronics",
            },
            "country": random.choice([
                "RU",
                "NG",
                "CN",
                "TR",
            ]),
        },
        "status": "approved",
        "device_id": device_b,
    })

    # Fraud label.
    records.append({
        "event_type": "fraud_event",
        "scenario_id": scenario_id,
        "ground_truth_scenario": "account_takeover",
        "event_id": random_id("FRAUD"),
        "customer_id": customer_id,
        "transaction_id": transaction_id,
        "timestamp": mixed_date(base_time + timedelta(hours=2)),
        "classification": {
            "type": "account_takeover",
            "severity": "HIGH",
            "confirmed": True,
        },
    })

    return records


def generate_velocity_scenario(
    customer_id,
    account_id,
):
    scenario_id = random_id("SCENARIO")

    base_time = random_date()

    records = []

    for i in range(20):
        transaction_id = random_id("TX")

        records.append({
            "event_type": "transaction",
            "scenario_id": scenario_id,
            "ground_truth_scenario": "velocity_anomaly",
            "transaction_id": transaction_id,
            "customer_id": customer_id,
            "account_id": account_id,
            "event_time": mixed_date(base_time + timedelta(seconds=i * 20)),
            "transaction": {
                "type": "purchase",
                "amount": {
                    "currency": "USD",
                    "amount": round(
                        random.uniform(
                            500,
                            2_000,
                        ),
                        2,
                    ),
                },
                "merchant": {
                    "id": random_id("MER"),
                    "category": random.choice(MERCHANT_CATEGORIES),
                },
                "country": random.choice([
                    "US",
                    "BR",
                    "MX",
                    "RU",
                    "NG",
                ]),
            },
            "status": "approved",
        })

    return records


def generate_duplicate_payment_scenario(
    customer_id,
    account_id,
):
    scenario_id = random_id("SCENARIO")

    payment_id = random_id("PAY")

    timestamp = random_date()

    payment = {
        "event_type": "payment",
        "scenario_id": scenario_id,
        "ground_truth_scenario": "duplicate_payment",
        "payment_id": payment_id,
        "customer_id": customer_id,
        "account_id": account_id,
        "timestamp": mixed_date(timestamp),
        "amount": {
            "currency": "USD",
            "amount": 1299.99,
        },
        "method": "credit_card",
        "status": "completed",
        "reference": "REFERENCE_DUPLICATE_001",
    }

    duplicate = dict(payment)

    duplicate["source_system"] = "PAYMENT_PROCESSOR_RETRY"

    duplicate["received_at"] = mixed_date(timestamp + timedelta(minutes=4))

    return [
        payment,
        duplicate,
    ]


# ============================================================
# JSON / JSONL WRITERS
# ============================================================


def malformed_json(record):
    serialized = json.dumps(
        record,
        ensure_ascii=False,
    )

    mode = random.randint(
        1,
        8,
    )

    if mode == 1:
        return serialized[:-1]

    if mode == 2:
        return serialized.replace(
            '"',
            "",
            1,
        )

    if mode == 3:
        return serialized + " garbage"

    if mode == 4:
        return serialized.replace(
            ",",
            "",
            1,
        )

    if mode == 5:
        return serialized.replace(
            "{",
            "[",
            1,
        )

    if mode == 6:
        return serialized + ","

    if mode == 7:
        return '{"broken": ' + serialized

    return serialized.replace(
        "true",
        "TRUE",
    )


def write_jsonl(
    path,
    records,
    args,
):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        for record in records:
            record = corrupt_record(
                record,
                args,
            )

            if chance(args.malformed_rate):
                f.write(malformed_json(record) + "\n")
            else:
                f.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                    )
                    + "\n"
                )


def write_json(
    path,
    records,
    args,
):
    payload = {
        "batch": {
            "batch_id": random_id("BATCH"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": random.choice([
                "CUSTOMER_CORE",
                "ACCOUNT_CORE",
                "PAYMENT_PROCESSOR",
                "FRAUD_PLATFORM",
                "CUSTOMER_SERVICE",
            ]),
            "record_count": len(records),
        },
        "records": [
            corrupt_record(
                record,
                args,
            )
            for record in records
        ],
    }

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# MESSY CSV
# ============================================================


def write_messy_csv(
    path,
    accounts,
    args,
):
    schema_versions = [
        [
            "account_id",
            "customer_id",
            "account_type",
            "opening_date",
            "credit_limit",
            "balance",
            "status",
        ],
        [
            "accountId",
            "customerId",
            "type",
            "opened_at",
            "creditLimit",
            "current_balance",
            "account_status",
        ],
        [
            "ACCOUNT_ID",
            "CUSTOMER",
            "PRODUCT",
            "OPEN_DATE",
            "LIMIT",
            "BALANCE",
            "STATE",
        ],
    ]

    headers = random.choice(schema_versions)

    delimiter = random.choice([
        ",",
        ",",
        ",",
        ";",
        "|",
    ])

    with open(
        path,
        "w",
        encoding=random.choice([
            "utf-8",
            "utf-8-sig",
        ]),
        newline="",
    ) as f:
        writer = csv.writer(
            f,
            delimiter=delimiter,
        )

        writer.writerow(headers)

        for account in accounts:
            values = [
                account.get(
                    "account_id",
                    "",
                ),
                account.get(
                    "customer_id",
                    "",
                ),
                account.get(
                    "type",
                    "",
                ),
                account.get(
                    "opened",
                    "",
                ),
                account.get(
                    "credit_limit",
                    "",
                ),
                account.get(
                    "balance",
                    "",
                ),
                account.get(
                    "status",
                    "",
                ),
            ]

            # More realistic CSV corruption.
            if chance(args.missing_rate):
                index = random.randrange(len(values))

                values[index] = ""

            if chance(args.schema_drift_rate):
                values = [str(value) for value in values]

                if chance(0.50):
                    values[random.randrange(len(values))] = "NULL"

                else:
                    values[random.randrange(len(values))] = "N/A"

            writer.writerow(values)


# ============================================================
# APPLICATION LOG WRITER
# ============================================================


def write_logs(
    path,
    customer_ids,
    count,
):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        for _ in range(count):
            customer_id = random.choice(customer_ids)

            f.write(generate_application_log(customer_id) + "\n")


# ============================================================
# SUPPORT WRITER
# ============================================================


def write_support(
    path,
    fake,
    customer_ids,
    count,
):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        for i in range(count):
            f.write(
                generate_support_text(
                    fake,
                    random.choice(customer_ids),
                )
            )

            if i < count - 1:
                f.write("\n---\n")


# ============================================================
# DUPLICATE FILES
# ============================================================


def duplicate_file(
    original,
    duplicate_number,
):
    original = Path(original)

    duplicate = original.parent / (
        original.stem + f"_REDELIVERY_{duplicate_number}" + original.suffix
    )

    duplicate.write_bytes(original.read_bytes())

    return duplicate


# ============================================================
# GROUND TRUTH
# ============================================================


def write_ground_truth(
    output,
    fraud_scenarios,
    anomaly_scenarios,
    duplicate_scenarios,
):
    ground_truth = []

    for scenario in fraud_scenarios:
        ground_truth.append({
            "scenario_id": scenario,
            "label": "fraud",
            "subtype": "account_takeover",
            "confirmed": True,
        })

    for scenario in anomaly_scenarios:
        ground_truth.append({
            "scenario_id": scenario,
            "label": "anomaly",
            "subtype": "velocity",
            "confirmed": True,
        })

    for scenario in duplicate_scenarios:
        ground_truth.append({
            "scenario_id": scenario,
            "label": "duplicate",
            "subtype": "duplicate_payment",
            "confirmed": True,
        })

    path = output / "ground_truth" / "scenario_labels.jsonl"

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        for row in ground_truth:
            f.write(json.dumps(row) + "\n")


# ============================================================
# SOURCE METADATA
# ============================================================


def write_source_metadata(
    output,
    args,
):
    metadata = {
        "CUSTOMER_CORE": {
            "format": ["JSON"],
            "owner": "Customer Operations",
            "domain": "customer",
            "contains_pii": True,
            "expected_sla": "99.9%",
            "identifier": "customerId",
        },
        "ACCOUNT_CORE": {
            "format": ["CSV"],
            "owner": "Account Operations",
            "domain": "account",
            "contains_pii": False,
            "expected_sla": "99.5%",
            "identifier": "account_id",
        },
        "PAYMENT_PROCESSOR": {
            "format": ["JSONL"],
            "owner": "Payments Engineering",
            "domain": "transaction",
            "contains_pii": False,
            "expected_sla": "99.99%",
            "identifier": "transaction_id",
        },
        "FRAUD_PLATFORM": {
            "format": [
                "JSON",
                "JSONL",
            ],
            "owner": "Risk Engineering",
            "domain": "fraud",
            "contains_pii": False,
            "expected_sla": "99.99%",
            "identifier": "event_id",
        },
        "CUSTOMER_SERVICE": {
            "format": [
                "JSONL",
                "TXT",
            ],
            "owner": "Customer Experience",
            "domain": "customer_interaction",
            "contains_pii": True,
            "expected_sla": "99.5%",
            "identifier": "interaction_id",
        },
        "AUTHENTICATION_PLATFORM": {
            "format": [
                "LOG",
                "JSONL",
            ],
            "owner": "Identity Engineering",
            "domain": "authentication",
            "contains_pii": True,
            "expected_sla": "99.99%",
            "identifier": "auth_event_id",
        },
        "CARD_PLATFORM": {
            "format": ["JSONL"],
            "owner": "Cards Engineering",
            "domain": "cards",
            "contains_pii": False,
            "expected_sla": "99.9%",
            "identifier": "card_event_id",
        },
        "LENDING_PLATFORM": {
            "format": ["JSON"],
            "owner": "Lending",
            "domain": "loans",
            "contains_pii": False,
            "expected_sla": "99.5%",
            "identifier": "loan_event_id",
        },
        "APPLICATION_PLATFORM": {
            "format": [
                "LOG",
                "JSON",
            ],
            "owner": "Platform Engineering",
            "domain": "application",
            "contains_pii": True,
            "expected_sla": "99.99%",
            "identifier": "request_id",
        },
    }

    path = output / "metadata" / "source_systems.json"

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata,
            f,
            indent=2,
        )


# ============================================================
# MANIFEST
# ============================================================


def write_manifest(
    output,
    args,
    counts,
):
    manifest = {
        "generator": "payflow-raw-generator",
        "generator_version": "3.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "requested_logical_records": args.records,
        "customer_count": args.customers,
        "event_distribution": counts,
        "quality_parameters": {
            "duplicate_rate": args.duplicate_rate,
            "missing_rate": args.missing_rate,
            "malformed_rate": args.malformed_rate,
            "unknown_id_rate": args.unknown_id_rate,
            "late_rate": args.late_rate,
            "out_of_order_rate": args.out_of_order_rate,
            "schema_drift_rate": args.schema_drift_rate,
            "pii_rate": args.pii_rate,
            "fraud_rate": args.fraud_rate,
            "anomaly_rate": args.anomaly_rate,
            "duplicate_file_rate": args.duplicate_file_rate,
        },
        "intentionally_present_issues": [
            "missing_fields",
            "duplicate_records",
            "duplicate_files",
            "malformed_json",
            "unknown_foreign_keys",
            "schema_drift",
            "mixed_date_formats",
            "mixed_currency_formats",
            "inconsistent_casing",
            "inconsistent_column_names",
            "inconsistent_identifiers",
            "late_arriving_data",
            "out_of_order_events",
            "mixed_event_types",
            "unstructured_text",
            "application_errors",
            "retry_events",
            "PII",
            "fraud_scenarios",
            "velocity_anomalies",
            "duplicate_payments",
            "account_takeover_scenarios",
            "chargeback_scenarios",
            "geographic_anomalies",
            "device_anomalies",
        ],
    }

    path = output / "metadata" / "manifest.json"

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
        )


# ============================================================
# MAIN
# ============================================================


def main():
    args = parse_args()

    random.seed(args.seed)

    fake = Faker()

    fake.seed_instance(args.seed)

    output = Path(args.output)

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    directories = [
        "customer_core",
        "accounts",
        "payments",
        "transactions",
        "fraud",
        "chargebacks",
        "loans",
        "cards",
        "customer_service",
        "authentication",
        "devices",
        "application_logs",
        "mixed_events",
        "metadata",
        "ground_truth",
    ]

    for directory in directories:
        (output / directory).mkdir(
            parents=True,
            exist_ok=True,
        )

    # ========================================================
    # CUSTOMERS
    # ========================================================

    print(f"Generating {args.customers:,} customers...")

    customer_ids = [
        f"CUST_{i:08d}"
        for i in range(
            1,
            args.customers + 1,
        )
    ]

    customers = []

    for customer_id in customer_ids:
        customers.append(
            generate_customer(
                fake,
                customer_id,
                args,
            )
        )

    customer_files = []

    for start in range(
        0,
        len(customers),
        args.file_size,
    ):
        batch = customers[start : start + args.file_size]

        number = start // args.file_size

        path = output / "customer_core" / f"customers_{number:05d}.json"

        write_json(
            path,
            batch,
            args,
        )

        customer_files.append(str(path))

    # ========================================================
    # ACCOUNTS
    # ========================================================

    print("Generating accounts...")

    accounts = []

    for customer_id in customer_ids:
        number = random.choices(
            [
                1,
                2,
                3,
                4,
            ],
            weights=[
                65,
                25,
                8,
                2,
            ],
        )[0]

        for _ in range(number):
            accounts.append(generate_account(customer_id))

    account_files = []

    for start in range(
        0,
        len(accounts),
        args.file_size,
    ):
        batch = accounts[start : start + args.file_size]

        number = start // args.file_size

        path = output / "accounts" / f"accounts_{number:05d}.csv"

        write_messy_csv(
            path,
            batch,
            args,
        )

        account_files.append(str(path))

    account_ids = [account["account_id"] for account in accounts]

    # ========================================================
    # EVENT DISTRIBUTION
    # ========================================================

    distribution = {
        "transaction": int(args.records * 0.45),
        "payment": int(args.records * 0.08),
        "fraud_event": int(args.records * 0.04),
        "customer_interaction": int(args.records * 0.10),
        "authentication": int(args.records * 0.08),
        "device_registration": int(args.records * 0.04),
        "chargeback": int(args.records * 0.03),
        "loan_event": int(args.records * 0.04),
        "card_event": int(args.records * 0.04),
        "application_log": int(args.records * 0.07),
        "support_ticket": int(args.records * 0.03),
    }

    # ========================================================
    # TRANSACTIONS
    # ========================================================

    print(f"Generating {distribution["transaction"]:,} transactions...")

    transaction_files = []

    buffer = []

    for _ in range(distribution["transaction"]):
        customer_id = random.choice(customer_ids)

        account_id = random.choice(account_ids)

        force_anomaly = chance(args.anomaly_rate)

        transaction = generate_transaction(
            customer_id,
            account_id,
            force_anomaly=force_anomaly,
        )

        buffer.append(transaction)

        if len(buffer) >= args.file_size:
            path = (
                output
                / "transactions"
                / f"transactions_{len(transaction_files):05d}.jsonl"
            )

            write_jsonl(
                path,
                buffer,
                args,
            )

            transaction_files.append(str(path))

            buffer = []

    if buffer:
        path = (
            output / "transactions" / f"transactions_{len(transaction_files):05d}.jsonl"
        )

        write_jsonl(
            path,
            buffer,
            args,
        )

        transaction_files.append(str(path))

    # ========================================================
    # PAYMENTS
    # ========================================================

    print(f"Generating {distribution["payment"]:,} payments...")

    payment_files = []

    buffer = []

    for _ in range(distribution["payment"]):
        buffer.append(
            generate_payment(
                random.choice(customer_ids),
                random.choice(account_ids),
            )
        )

        if len(buffer) >= args.file_size:
            path = output / "payments" / f"payments_{len(payment_files):05d}.jsonl"

            write_jsonl(
                path,
                buffer,
                args,
            )

            payment_files.append(str(path))

            buffer = []

    if buffer:
        path = output / "payments" / f"payments_{len(payment_files):05d}.jsonl"

        write_jsonl(
            path,
            buffer,
            args,
        )

        payment_files.append(str(path))

    # ========================================================
    # FRAUD
    # ========================================================

    print(f"Generating {distribution["fraud_event"]:,} fraud events...")

    fraud_files = []

    buffer = []

    for _ in range(distribution["fraud_event"]):
        buffer.append(
            generate_fraud_event(
                random.choice(customer_ids),
                random_id("TX"),
            )
        )

        if len(buffer) >= args.file_size:
            path = output / "fraud" / f"fraud_{len(fraud_files):05d}.jsonl"

            write_jsonl(
                path,
                buffer,
                args,
            )

            fraud_files.append(str(path))

            buffer = []

    if buffer:
        path = output / "fraud" / f"fraud_{len(fraud_files):05d}.jsonl"

        write_jsonl(
            path,
            buffer,
            args,
        )

        fraud_files.append(str(path))

    # ========================================================
    # CUSTOMER INTERACTIONS
    # ========================================================

    print("Generating customer interactions...")

    interaction_files = []

    buffer = []

    for _ in range(distribution["customer_interaction"]):
        buffer.append(generate_interaction(random.choice(customer_ids)))

        if len(buffer) >= args.file_size:
            path = (
                output
                / "customer_service"
                / f"interactions_{len(interaction_files):05d}.jsonl"
            )

            write_jsonl(
                path,
                buffer,
                args,
            )

            interaction_files.append(str(path))

            buffer = []

    if buffer:
        path = (
            output
            / "customer_service"
            / f"interactions_{len(interaction_files):05d}.jsonl"
        )

        write_jsonl(
            path,
            buffer,
            args,
        )

        interaction_files.append(str(path))

    # ========================================================
    # AUTHENTICATION
    # ========================================================

    print("Generating authentication events...")

    auth_files = []

    buffer = []

    for _ in range(distribution["authentication"]):
        buffer.append(generate_authentication(random.choice(customer_ids)))

        if len(buffer) >= args.file_size:
            path = (
                output
                / "authentication"
                / f"authentication_{len(auth_files):05d}.jsonl"
            )

            write_jsonl(
                path,
                buffer,
                args,
            )

            auth_files.append(str(path))

            buffer = []

    if buffer:
        path = output / "authentication" / f"authentication_{len(auth_files):05d}.jsonl"

        write_jsonl(
            path,
            buffer,
            args,
        )

        auth_files.append(str(path))

    # ========================================================
    # DEVICES
    # ========================================================

    print("Generating device events...")

    device_files = []

    buffer = []

    for _ in range(distribution["device_registration"]):
        buffer.append(generate_device(random.choice(customer_ids)))

        if len(buffer) >= args.file_size:
            path = output / "devices" / f"devices_{len(device_files):05d}.jsonl"

            write_jsonl(
                path,
                buffer,
                args,
            )

            device_files.append(str(path))

            buffer = []

    if buffer:
        path = output / "devices" / f"devices_{len(device_files):05d}.jsonl"

        write_jsonl(
            path,
            buffer,
            args,
        )

        device_files.append(str(path))

    # ========================================================
    # CHARGEBACKS
    # ========================================================

    print("Generating chargebacks...")

    chargeback_files = []

    buffer = []

    for _ in range(distribution["chargeback"]):
        buffer.append(
            generate_chargeback(
                random.choice(customer_ids),
                random_id("TX"),
            )
        )

        if len(buffer) >= args.file_size:
            path = (
                output
                / "chargebacks"
                / f"chargebacks_{len(chargeback_files):05d}.jsonl"
            )

            write_jsonl(
                path,
                buffer,
                args,
            )

            chargeback_files.append(str(path))

            buffer = []

    if buffer:
        path = output / "chargebacks" / f"chargebacks_{len(chargeback_files):05d}.jsonl"

        write_jsonl(
            path,
            buffer,
            args,
        )

        chargeback_files.append(str(path))

    # ========================================================
    # LOANS
    # ========================================================

    print("Generating loan events...")

    loan_files = []

    buffer = []

    for _ in range(distribution["loan_event"]):
        buffer.append(
            generate_loan_event(
                random.choice(customer_ids),
                random.choice(account_ids),
            )
        )

        if len(buffer) >= args.file_size:
            path = output / "loans" / f"loans_{len(loan_files):05d}.jsonl"

            write_jsonl(
                path,
                buffer,
                args,
            )

            loan_files.append(str(path))

            buffer = []

    if buffer:
        path = output / "loans" / f"loans_{len(loan_files):05d}.jsonl"

        write_jsonl(
            path,
            buffer,
            args,
        )

        loan_files.append(str(path))

    # ========================================================
    # CARD EVENTS
    # ========================================================

    print("Generating card events...")

    card_files = []

    buffer = []

    for _ in range(distribution["card_event"]):
        buffer.append(
            generate_card_event(
                random.choice(customer_ids),
                random.choice(account_ids),
            )
        )

        if len(buffer) >= args.file_size:
            path = output / "cards" / f"cards_{len(card_files):05d}.jsonl"

            write_jsonl(
                path,
                buffer,
                args,
            )

            card_files.append(str(path))

            buffer = []

    if buffer:
        path = output / "cards" / f"cards_{len(card_files):05d}.jsonl"

        write_jsonl(
            path,
            buffer,
            args,
        )

        card_files.append(str(path))

    # ========================================================
    # APPLICATION LOGS
    # ========================================================

    print("Generating application logs...")

    log_files = []

    remaining = distribution["application_log"]

    while remaining > 0:
        count = min(
            args.file_size,
            remaining,
        )

        path = output / "application_logs" / f"application_{len(log_files):05d}.log"

        write_logs(
            path,
            customer_ids,
            count,
        )

        log_files.append(str(path))

        remaining -= count

    # ========================================================
    # SUPPORT TICKETS
    # ========================================================

    print("Generating support tickets...")

    support_files = []

    remaining = distribution["support_ticket"]

    while remaining > 0:
        count = min(
            10_000,
            remaining,
        )

        path = output / "customer_service" / f"support_{len(support_files):05d}.txt"

        write_support(
            path,
            fake,
            customer_ids,
            count,
        )

        support_files.append(str(path))

        remaining -= count

    # ========================================================
    # CORRELATED FRAUD / ANOMALY SCENARIOS
    # ========================================================

    print("Generating correlated ground-truth scenarios...")

    fraud_scenarios = []

    anomaly_scenarios = []

    duplicate_scenarios = []

    scenario_files = []

    for _ in range(
        max(
            100,
            int(args.customers * args.fraud_rate),
        )
    ):
        customer_id = random.choice(customer_ids)

        account_id = random.choice(account_ids)

        records = generate_fraud_scenario(
            customer_id,
            account_id,
        )

        scenario_id = records[0]["scenario_id"]

        fraud_scenarios.append(scenario_id)

        path = (
            output / "mixed_events" / f"fraud_scenario_{len(scenario_files):05d}.jsonl"
        )

        write_jsonl(
            path,
            records,
            args,
        )

        scenario_files.append(str(path))

    for _ in range(
        max(
            100,
            int(args.customers * args.anomaly_rate),
        )
    ):
        customer_id = random.choice(customer_ids)

        account_id = random.choice(account_ids)

        records = generate_velocity_scenario(
            customer_id,
            account_id,
        )

        scenario_id = records[0]["scenario_id"]

        anomaly_scenarios.append(scenario_id)

        path = (
            output
            / "mixed_events"
            / f"velocity_scenario_{len(scenario_files):05d}.jsonl"
        )

        write_jsonl(
            path,
            records,
            args,
        )

        scenario_files.append(str(path))

    for _ in range(100):
        customer_id = random.choice(customer_ids)

        account_id = random.choice(account_ids)

        records = generate_duplicate_payment_scenario(
            customer_id,
            account_id,
        )

        scenario_id = records[0]["scenario_id"]

        duplicate_scenarios.append(scenario_id)

        path = (
            output
            / "payments"
            / f"duplicate_payment_{len(duplicate_scenarios):05d}.jsonl"
        )

        write_jsonl(
            path,
            records,
            args,
        )

    # ========================================================
    # MIXED EVENT FILES
    # ========================================================

    print("Generating mixed-event files...")

    mixed_files = []

    event_generators = [
        lambda cid: generate_transaction(
            cid,
            random.choice(account_ids),
        ),
        lambda cid: generate_payment(
            cid,
            random.choice(account_ids),
        ),
        lambda cid: generate_interaction(cid),
        lambda cid: generate_authentication(cid),
        lambda cid: generate_device(cid),
        lambda cid: generate_fraud_event(
            cid,
            random_id("TX"),
        ),
        lambda cid: generate_card_event(
            cid,
            random.choice(account_ids),
        ),
        lambda cid: generate_loan_event(
            cid,
            random.choice(account_ids),
        ),
    ]

    for file_number in range(20):
        records = []

        for _ in range(
            min(
                args.file_size,
                20_000,
            )
        ):
            customer_id = random.choice(customer_ids)

            generator = random.choice(event_generators)

            records.append(generator(customer_id))

        # Deliberately shuffle event order.
        random.shuffle(records)

        path = output / "mixed_events" / f"events_{file_number:05d}.jsonl"

        write_jsonl(
            path,
            records,
            args,
        )

        mixed_files.append(str(path))

    # ========================================================
    # LATE ARRIVING FILES
    # ========================================================

    print("Creating late-arriving files...")

    late_dir = output / "payments" / "late_arrivals"

    late_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for i in range(10):
        records = []

        for _ in range(
            min(
                5_000,
                args.file_size,
            )
        ):
            customer_id = random.choice(customer_ids)

            record = generate_transaction(
                customer_id,
                random.choice(account_ids),
            )

            record["event_time"] = mixed_date(
                random_date(
                    2024,
                    2025,
                )
            )

            record["ingested_at"] = mixed_date(datetime.now(timezone.utc))

            record["delivery_status"] = "late"

            records.append(record)

        path = late_dir / f"late_batch_{i:05d}.jsonl"

        write_jsonl(
            path,
            records,
            args,
        )

    # ========================================================
    # FILE-LEVEL DUPLICATION
    # ========================================================

    print("Creating duplicate file deliveries...")

    all_files = (
        customer_files
        + account_files
        + transaction_files
        + payment_files
        + fraud_files
        + interaction_files
        + auth_files
        + device_files
        + chargeback_files
        + loan_files
        + card_files
        + log_files
        + support_files
        + mixed_files
    )

    duplicate_count = max(
        1,
        int(len(all_files) * args.duplicate_file_rate),
    )

    duplicate_sources = random.sample(
        all_files,
        min(
            duplicate_count,
            len(all_files),
        ),
    )

    for number, original in enumerate(duplicate_sources):
        duplicate_file(
            original,
            number,
        )

    # ========================================================
    # SOURCE METADATA
    # ========================================================

    write_source_metadata(
        output,
        args,
    )

    # ========================================================
    # GROUND TRUTH
    # ========================================================

    write_ground_truth(
        output,
        fraud_scenarios,
        anomaly_scenarios,
        duplicate_scenarios,
    )

    # ========================================================
    # MANIFEST
    # ========================================================

    write_manifest(
        output,
        args,
        distribution,
    )

    # ========================================================
    # DATA QUALITY CHALLENGES
    # ========================================================

    quality_challenges = {
        "identity_resolution": [
            "customerId vs customer_id",
            "customer identifier changes",
            "unknown customer identifiers",
            "duplicate customer records",
        ],
        "schema": [
            "schema drift",
            "column renaming",
            "nested vs flat structures",
            "multiple schemas in same domain",
            "multiple event types in same file",
        ],
        "temporal": [
            "mixed timestamp formats",
            "timezone differences",
            "late arriving events",
            "out of order events",
            "events with future timestamps",
            "events received long after event time",
        ],
        "financial": [
            "multiple currencies",
            "currency symbol amounts",
            "numeric amounts",
            "string amounts",
            "minor-unit amounts",
            "negative amounts",
            "very large amounts",
            "rounding differences",
        ],
        "quality": [
            "missing values",
            "malformed JSON",
            "duplicate records",
            "duplicate files",
            "unknown foreign keys",
            "invalid enum values",
            "inconsistent casing",
            "inconsistent naming",
            "NULL strings",
            "N/A strings",
        ],
        "fraud": [
            "account takeover",
            "velocity anomaly",
            "geographic anomaly",
            "new device",
            "device switching",
            "high value transaction",
            "suspicious merchant",
            "authentication failures",
            "duplicate payment",
            "chargeback",
        ],
        "privacy": [
            "email",
            "phone",
            "address",
            "national ID",
            "IP address",
            "nested PII",
        ],
        "unstructured": [
            "support tickets",
            "application logs",
            "mixed log formats",
            "free-text customer descriptions",
        ],
    }

    with open(
        output / "metadata" / "quality_challenges.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            quality_challenges,
            f,
            indent=2,
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("==========================================")
    print("PAYFLOW RAW DATA GENERATION COMPLETE")
    print("==========================================")

    print(f"Requested logical event records: " f"{args.records:,}")

    print(f"Customers: " f"{args.customers:,}")

    print(f"Accounts: " f"{len(accounts):,}")

    print(f"Fraud scenarios: " f"{len(fraud_scenarios):,}")

    print(f"Anomaly scenarios: " f"{len(anomaly_scenarios):,}")

    print(f"Duplicate-payment scenarios: " f"{len(duplicate_scenarios):,}")

    print(f"Output: " f"{output.resolve()}")

    print()
    print("Intentional data problems:")

    for item in [
        "JSON / JSONL / CSV / LOG / TXT",
        "nested JSON",
        "mixed event types",
        "schema drift",
        "missing fields",
        "malformed records",
        "duplicate records",
        "duplicate files",
        "unknown IDs",
        "inconsistent identifiers",
        "mixed date formats",
        "mixed currencies",
        "mixed monetary representations",
        "late-arriving data",
        "out-of-order data",
        "unstructured text",
        "application errors",
        "retry events",
        "PII",
        "fraud scenarios",
        "velocity anomalies",
        "geographic anomalies",
        "account takeover scenarios",
        "duplicate payments",
        "chargebacks",
        "device anomalies",
    ]:
        print(f"  - {item}")


if __name__ == "__main__":
    main()
