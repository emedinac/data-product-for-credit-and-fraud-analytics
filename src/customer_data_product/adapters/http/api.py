import csv
import io
import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, Self, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from customer_data_product.adapters.ground_truth import LocalGroundTruthReader
from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.application.services import BatchService


class BatchCreateRequest(BaseModel):
    source: str = Field(min_length=1, max_length=100)


class ObservationCustomer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1)
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    country: str | None = None
    city: str | None = None
    registered_at: datetime | None = None
    status: str | None = None
    customer_type: str | None = None


class ObservationAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    type: str | None = None
    opened: datetime | None = None
    status: str | None = None
    credit_limit: str | float | None = None
    balance: str | float | None = None


class ObservationAmount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(min_length=3, max_length=3)
    amount: float


class ObservationTransactionDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    amount: ObservationAmount
    merchant_id: str | None = None
    merchant_category: str | None = None
    country: str | None = None


class ObservationTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str | None = None
    transaction_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    event_time: datetime
    transaction: ObservationTransactionDetails
    status: str | None = None


class CustomerIngestionRequest(BaseModel):
    """A customer create/update event from the customer source system."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1)
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    country: str | None = None
    city: str | None = None
    registered_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("registered_at", "registration_date"),
    )
    status: str | None = Field(
        default=None,
        validation_alias=AliasChoices("status", "customer_status"),
    )
    customer_type: str | None = None


class AccountIngestionRequest(BaseModel):
    """An account create/update event from the account source system."""

    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    account_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("account_type", "type"),
    )
    opened_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("opened_at", "opening_date", "opened"),
    )
    credit_limit: str | float | None = None
    balance: str | float | None = Field(
        default=None,
        validation_alias=AliasChoices("balance", "current_balance"),
    )
    status: str | None = Field(
        default=None,
        validation_alias=AliasChoices("status", "account_status"),
    )


class TransactionIngestionRequest(BaseModel):
    """A transaction event from the transaction source system.

    Both the flat source-system shape and the nested shape used by the file
    parser are accepted. The latter keeps this endpoint compatible with the
    evaluation fixture without making the evaluator send fraud labels.
    """

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    event_time: datetime = Field(
        validation_alias=AliasChoices("event_time", "timestamp", "event_timestamp")
    )
    amount: float | ObservationAmount | None = None
    currency: str | None = None
    transaction_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("transaction_type", "type"),
    )
    merchant_id: str | None = None
    merchant_category: str | None = None
    country: str | None = None
    status: str | None = None
    transaction: ObservationTransactionDetails | None = None

    @model_validator(mode="after")
    def validate_amount(self) -> Self:
        if self.amount is None and self.transaction is None:
            raise ValueError("amount is required")
        return self


class InteractionDetailsIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    resolution: str | None = None


class InteractionIngestionRequest(BaseModel):
    """A customer interaction event from the interaction source system."""

    model_config = ConfigDict(extra="forbid")

    interaction_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    event_time: datetime = Field(
        validation_alias=AliasChoices("event_time", "timestamp", "event_timestamp")
    )
    channel: str | None = None
    interaction_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("interaction_type", "type"),
    )
    resolution: str | None = None
    interaction: InteractionDetailsIngestionRequest | None = None

    @model_validator(mode="after")
    def validate_nested_fields(self) -> Self:
        if self.interaction is not None:
            if self.interaction_type is None:
                self.interaction_type = self.interaction.type
            if self.resolution is None:
                self.resolution = self.interaction.resolution
        return self


class FraudEventIngestionRequest(BaseModel):
    """External fraud-system feedback; evaluation ground truth is excluded."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    transaction_id: str | None = None
    customer_id: str = Field(min_length=1)
    event_time: datetime = Field(
        validation_alias=AliasChoices("event_time", "event_timestamp", "timestamp")
    )
    event_type: str | None = None
    severity: str | None = None
    confirmed_fraud: bool = Field(
        validation_alias=AliasChoices("confirmed_fraud", "confirmed")
    )


class ObservationUploadRequest(BaseModel):
    """One canonical observation; fraud labels are intentionally not accepted."""

    model_config = ConfigDict(extra="forbid")

    customer: ObservationCustomer
    account: ObservationAccount
    transaction: ObservationTransaction

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        if self.customer.customer_id != self.account.customer_id:
            raise ValueError("customer and account customer_id values must match")
        if self.customer.customer_id != self.transaction.customer_id:
            raise ValueError("customer and transaction customer_id values must match")
        if self.account.account_id != self.transaction.account_id:
            raise ValueError("account and transaction account_id values must match")
        return self


class BatchResponse(BaseModel):
    batch_id: str
    source: str | None = None
    status: str
    files_count: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    quarantined_count: int = 0
    snapshot_count: int = 0


class ProcessingJobResponse(BaseModel):
    job_id: str
    batch_id: str
    status: str
    attempts: int
    max_attempts: int


class ProcessEnqueueResponse(BaseModel):
    batch: BatchResponse
    job: ProcessingJobResponse


class ObservationUploadResponse(BaseModel):
    batch: BatchResponse
    job: ProcessingJobResponse


class SourceIngestionResponse(BaseModel):
    source: str
    batch: BatchResponse
    job: ProcessingJobResponse


class UploadResponse(BaseModel):
    batch_id: str
    file_id: str
    filename: str
    storage_key: str
    size_bytes: int


class CustomerResponse(BaseModel):
    customer_id: str
    first_name: str | None
    last_name: str | None
    date_of_birth: date | None
    status: str | None
    customer_type: str | None
    country: str | None
    city: str | None
    account_count: int
    total_credit_limit: float | None
    total_balance: float | None
    transaction_count: int
    transaction_amount: float
    transaction_amount_currency: str
    declined_transaction_count: int
    fraud_event_count: int
    confirmed_fraud_count: int
    interaction_count: int
    last_transaction_at: datetime | None
    customer_since: datetime | None = None
    customer_age_band: str | None = None
    transaction_count_7d: int = 0
    transaction_count_30d: int = 0
    transaction_count_90d: int = 0
    transaction_amount_7d: float = 0
    transaction_amount_30d: float = 0
    transaction_amount_90d: float = 0
    average_transaction_amount_30d: float | None = None
    declined_transaction_count_30d: int = 0
    decline_rate_30d: float | None = None
    distinct_merchant_count_30d: int = 0
    distinct_country_count_30d: int = 0
    fraud_event_count_90d: int = 0
    confirmed_fraud_count_90d: int = 0
    days_since_last_transaction: int | None = None
    customer_tenure_days: int | None = None
    credit_utilization: float | None = None
    delinquent_account_count: int = 0
    has_delinquency: bool = False
    portfolio_segment: str = "inactive"
    batch_id: str
    updated_at: datetime
    effective_at: datetime | None
    as_of_time: datetime


class CustomerTransactionResponse(BaseModel):
    transaction_id: str
    customer_id: str
    account_id: str
    event_time: datetime
    amount: float
    currency: str | None
    amount_base_currency: float | None
    transaction_type: str | None
    status: str | None
    merchant_id: str | None
    merchant_category: str | None
    country: str | None
    fraud_risk_score: float | None = None
    fraud_decision: str | None = None
    fraud_risk_reasons: list[str] = Field(default_factory=list)


class LineageFileResponse(BaseModel):
    file_id: str
    filename: str
    storage_key: str


class FieldLineageResponse(BaseModel):
    target_field: str
    source_fields: list[str]
    transformation: str


class LineageResponse(BaseModel):
    batch_id: str
    source: str
    status: str
    created_at: datetime
    updated_at: datetime
    files: list[LineageFileResponse]
    field_lineage: list[FieldLineageResponse]


class SummaryResponse(BaseModel):
    customer_count: int
    account_count: int
    transaction_count: int
    fraud_event_count: int
    confirmed_fraud_count: int
    interaction_count: int
    quarantined_count: int
    last_batch_id: str | None
    last_batch_status: str | None
    last_batch_updated_at: datetime | None
    latest_accepted_count: int
    latest_duplicate_count: int
    latest_quarantined_count: int


class DistributionItem(BaseModel):
    label: str
    count: int


class SummaryDistributionsResponse(BaseModel):
    customers_by_status: list[DistributionItem]
    transactions_by_status: list[DistributionItem]


class PortfolioTrendPoint(BaseModel):
    batch_id: str
    as_of_time: datetime
    customer_count: int
    active_customer_count: int
    total_balance: float
    average_credit_utilization: float | None


class AnalyticsSummaryResponse(BaseModel):
    active_customer_count: int
    customers_increased_activity_30d: int
    average_transaction_amount_by_segment: dict[str, float]
    customers_with_outstanding_balance: int
    highly_utilized_percentage: float
    customers_by_country: list[DistributionItem]
    portfolio_trend: list[PortfolioTrendPoint]


class GroundTruthRecord(BaseModel):
    scenario_id: str
    label: str
    subtype: str | None
    confirmed: bool
    evidence_found: bool
    customer_id: str | None = None
    transaction_ids: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    evidence_records: list[dict[str, object]] = Field(default_factory=list)
    explanation: str
    predicted_label: str = "not_fraud"
    classification_result: str = "correct"
    misclassified: bool = False


class GroundTruthResponse(BaseModel):
    source: str
    description: str
    total: int
    confirmed: int
    evidence_found: int
    evidence_missing: int
    labels_by_type: dict[str, int]
    subtypes: dict[str, int]
    records: list[GroundTruthRecord]
    quality_ground_truth: dict[str, object] = Field(default_factory=dict)


class QualityIssueResponse(BaseModel):
    filename: str
    line_number: int | None
    issue_type: str
    detail: str


class QualitySummaryResponse(BaseModel):
    batch_id: str | None
    batch_status: str
    quality_status: str
    quality_failure_reasons: list[str]
    total_count: int
    accepted_count: int
    duplicate_count: int
    quarantined_count: int
    required_field_completeness: float
    referential_integrity_failure_rate: float
    duplicate_rate: float
    quarantine_rate: float
    freshness_seconds: float | None
    duration_seconds: float | None
    volume_change_rate: float | None
    source_event_min: datetime | None
    source_event_max: datetime | None
    updated_at: datetime | None


FIELD_LINEAGE = [
    FieldLineageResponse(
        target_field="customer_id",
        source_fields=["customer_core.customer_id"],
        transformation="Pass through; customer key.",
    ),
    FieldLineageResponse(
        target_field="first_name",
        source_fields=["customer_core.first_name"],
        transformation="Trim whitespace; preserve null.",
    ),
    FieldLineageResponse(
        target_field="last_name",
        source_fields=["customer_core.last_name"],
        transformation="Trim whitespace; preserve null.",
    ),
    FieldLineageResponse(
        target_field="date_of_birth",
        source_fields=["customer_core.date_of_birth"],
        transformation="Parse as ISO date; preserve null.",
    ),
    FieldLineageResponse(
        target_field="status",
        source_fields=["customer_core.customer_status"],
        transformation="Normalize case, separators, and whitespace.",
    ),
    FieldLineageResponse(
        target_field="customer_type",
        source_fields=["customer_core.customer_type"],
        transformation="Normalize case, separators, and whitespace.",
    ),
    FieldLineageResponse(
        target_field="country",
        source_fields=["customer_core.country"],
        transformation="Trim and uppercase.",
    ),
    FieldLineageResponse(
        target_field="city",
        source_fields=["customer_core.city"],
        transformation="Trim whitespace; preserve null.",
    ),
    FieldLineageResponse(
        target_field="account_count",
        source_fields=["accounts.account_id", "accounts.customer_id"],
        transformation="Count accounts grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="total_credit_limit",
        source_fields=["accounts.credit_limit", "accounts.customer_id"],
        transformation="Sum account credit_limit grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="total_balance",
        source_fields=["accounts.current_balance", "accounts.customer_id"],
        transformation="Sum account current_balance grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="transaction_count",
        source_fields=["transactions.transaction_id", "transactions.customer_id"],
        transformation="Count transactions grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="transaction_amount",
        source_fields=[
            "transactions.amount",
            "transactions.currency",
            "transactions.status",
            "transactions.customer_id",
            "configured exchange rates",
        ],
        transformation="Sum approved amounts after conversion to base currency.",
    ),
    FieldLineageResponse(
        target_field="transaction_amount_currency",
        source_fields=["BASE_CURRENCY configuration"],
        transformation="Configured base currency.",
    ),
    FieldLineageResponse(
        target_field="declined_transaction_count",
        source_fields=["transactions.status", "transactions.customer_id"],
        transformation=(
            "Count transactions with status declined grouped by customer_id."
        ),
    ),
    FieldLineageResponse(
        target_field="last_transaction_at",
        source_fields=["transactions.timestamp", "transactions.customer_id"],
        transformation="Maximum transaction timestamp grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="fraud_event_count",
        source_fields=["fraud.event_id", "fraud.customer_id"],
        transformation="Count fraud events grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="confirmed_fraud_count",
        source_fields=["fraud.confirmed_fraud", "fraud.customer_id"],
        transformation="Count confirmed fraud events grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="interaction_count",
        source_fields=[
            "customer_service.interaction_id",
            "customer_service.customer_id",
        ],
        transformation="Count interactions grouped by customer_id.",
    ),
    FieldLineageResponse(
        target_field="batch_id",
        source_fields=["batch metadata.batch_id"],
        transformation="Batch that produced the snapshot.",
    ),
    FieldLineageResponse(
        target_field="updated_at",
        source_fields=["batch metadata.publication time"],
        transformation="Snapshot publication timestamp.",
    ),
    FieldLineageResponse(
        target_field="effective_at",
        source_fields=["source event timestamps"],
        transformation="Latest source event represented in the snapshot.",
    ),
    FieldLineageResponse(
        target_field="as_of_time",
        source_fields=["batch metadata.publication time"],
        transformation="Time at which the snapshot was published.",
    ),
]


def observation_files(
    request: ObservationUploadRequest,
) -> tuple[tuple[str, bytes], ...]:
    """Convert one canonical observation into the existing source files."""
    customer = json.dumps(
        {"records": [request.customer.model_dump(mode="json", exclude_none=True)]}
    ).encode()

    account = request.account.model_dump(mode="json", exclude_none=True)
    account_output = io.StringIO()
    account_writer = csv.DictWriter(account_output, fieldnames=list(account))
    account_writer.writeheader()
    account_writer.writerow(account)

    transaction = json.dumps(
        request.transaction.model_dump(mode="json", exclude_none=True)
    ).encode()
    return (
        ("customers.json", customer),
        ("accounts.csv", account_output.getvalue().encode()),
        ("transactions.jsonl", transaction + b"\n"),
    )


def customer_ingestion_file(request: CustomerIngestionRequest) -> bytes:
    payload = request.model_dump(mode="json", exclude_none=True)
    return json.dumps({"records": [payload]}).encode()


def account_ingestion_file(request: AccountIngestionRequest) -> bytes:
    payload = request.model_dump(mode="json", exclude_none=True)
    if "status" in payload:
        payload["account_status"] = payload.pop("status")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(payload))
    writer.writeheader()
    writer.writerow(payload)
    return output.getvalue().encode()


def transaction_ingestion_file(request: TransactionIngestionRequest) -> bytes:
    if isinstance(request.amount, ObservationAmount):
        amount = request.amount.model_dump(mode="json", exclude_none=True)
    elif request.amount is not None:
        amount = {"amount": request.amount}
        if request.currency is not None:
            amount["currency"] = request.currency
    else:
        assert request.transaction is not None
        nested_details = request.transaction.model_dump(mode="json", exclude_none=True)
        amount = cast(dict[str, object], nested_details["amount"])

    details: dict[str, object] = {"amount": amount}
    if request.transaction is not None:
        details = request.transaction.model_dump(mode="json", exclude_none=True)
    if request.transaction_type is not None:
        details["type"] = request.transaction_type
    for field in ("merchant_id", "merchant_category", "country"):
        value = getattr(request, field)
        if value is not None:
            details[field] = value

    payload: dict[str, object] = {
        "transaction_id": request.transaction_id,
        "customer_id": request.customer_id,
        "account_id": request.account_id,
        "event_time": request.event_time.isoformat(),
        "transaction": details,
    }
    if request.status is not None:
        payload["status"] = request.status
    return (json.dumps(payload) + "\n").encode()


def interaction_ingestion_file(request: InteractionIngestionRequest) -> bytes:
    interaction: dict[str, str] = {}
    if request.interaction_type is not None:
        interaction["type"] = request.interaction_type
    if request.resolution is not None:
        interaction["resolution"] = request.resolution
    payload: dict[str, object] = {
        "interaction_id": request.interaction_id,
        "customer_id": request.customer_id,
        "timestamp": request.event_time.isoformat(),
        "interaction": interaction,
    }
    if request.channel is not None:
        payload["channel"] = request.channel
    return (json.dumps(payload) + "\n").encode()


def fraud_event_ingestion_file(request: FraudEventIngestionRequest) -> bytes:
    classification: dict[str, object] = {"confirmed": request.confirmed_fraud}
    if request.event_type is not None:
        classification["type"] = request.event_type
    if request.severity is not None:
        classification["severity"] = request.severity
    payload: dict[str, object] = {
        "event_id": request.event_id,
        "customer_id": request.customer_id,
        "timestamp": request.event_time.isoformat(),
        "classification": classification,
    }
    if request.transaction_id is not None:
        payload["transaction_id"] = request.transaction_id
    return (json.dumps(payload) + "\n").encode()


def router(
    service: BatchService,
    repository: PostgresRepository,
    ground_truth: LocalGroundTruthReader,
    enable_ground_truth: bool = False,
    auth_audience: str | None = None,
    auth_role_bindings: str = "",
    auth_consumer_entitlements: str = "",
    auth_mode: str = "google",
    local_auth_token: str | None = None,
) -> APIRouter:
    try:
        role_bindings = json.loads(auth_role_bindings) if auth_role_bindings else {}
    except json.JSONDecodeError as exc:
        raise ValueError("AUTH_ROLE_BINDINGS must be valid JSON") from exc
    try:
        consumer_entitlements = (
            json.loads(auth_consumer_entitlements) if auth_consumer_entitlements else {}
        )
    except json.JSONDecodeError as exc:
        raise ValueError("AUTH_CONSUMER_ENTITLEMENTS must be valid JSON") from exc
    if not isinstance(consumer_entitlements, dict):
        raise ValueError("AUTH_CONSUMER_ENTITLEMENTS must be a JSON object")

    def authenticate(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        token = authorization.removeprefix("Bearer ").strip()
        if auth_mode.lower() == "local":
            if not local_auth_token or token != local_auth_token:
                raise HTTPException(status_code=401, detail="invalid local token")
            subject = next(iter(role_bindings), "local-dev")
            return {"email": subject, "sub": subject, "roles": []}
        try:
            from google.auth.transport import requests
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(
                token,
                requests.Request(),
                audience=auth_audience,  # type: ignore[no-untyped-call]
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail="invalid bearer token") from exc
        return cast(dict[str, Any], claims)

    def require_role(
        *allowed: str,
    ) -> Callable[..., dict[str, Any]]:
        def dependency(
            request: Request,
            claims: dict[str, Any] = Depends(authenticate),
        ) -> dict[str, Any]:
            subject = str(claims.get("email") or claims.get("sub") or "")
            entitlement = consumer_entitlements.get(subject)
            consumer: str | None = None
            if consumer_entitlements:
                if not isinstance(entitlement, dict):
                    roles: set[str] = set()
                else:
                    consumer_value = entitlement.get("consumer")
                    consumer = (
                        str(consumer_value) if isinstance(consumer_value, str) else None
                    )
                    roles = {
                        role
                        for role in entitlement.get("roles", [])
                        if isinstance(role, str)
                    }
            else:
                roles = {
                    role for role in claims.get("roles", []) if isinstance(role, str)
                }
                configured_role = role_bindings.get(subject)
                if isinstance(configured_role, str):
                    roles.add(configured_role)
            outcome = "ALLOWED" if roles.intersection(allowed) else "DENIED"
            route = request.scope.get("route")
            repository.record_access_audit(
                actor_subject=subject or "unknown",
                consumer=consumer,
                action=request.method,
                resource=str(getattr(route, "path", request.url.path)),
                outcome=outcome,
                roles=roles,
            )
            if not roles.intersection(allowed):
                raise HTTPException(status_code=403, detail="insufficient role")
            return {**claims, "_roles": roles, "_consumer": consumer}

        return dependency

    def validate_idempotency_key(key: str | None) -> None:
        if key is not None and not key.strip():
            raise HTTPException(
                status_code=422, detail="Idempotency-Key cannot be blank"
            )

    def has_pii_access(claims: dict[str, Any]) -> bool:
        roles = claims.get("_roles", claims.get("roles", []))
        return bool(set(roles).intersection({"pii_reader", "admin"}))

    def redact_customer(customer: dict[str, object]) -> dict[str, object]:
        return {
            **customer,
            "first_name": None,
            "last_name": None,
            "date_of_birth": None,
            "city": None,
        }

    api = APIRouter(prefix="/v1", dependencies=[Depends(authenticate)])

    @api.post("/batches", response_model=BatchResponse, status_code=201)
    def create_batch(
        request: BatchCreateRequest,
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> BatchResponse:
        batch_id = service.create(request.source)
        batch = repository.get_batch(batch_id)
        assert batch is not None
        return BatchResponse(**batch)

    def ingest_source(
        source: str,
        filename: str,
        content: bytes,
        idempotency_key: str | None,
    ) -> SourceIngestionResponse:
        validate_idempotency_key(idempotency_key)
        try:
            batch_id, job = service.ingest_source_record(
                source, filename, [content], idempotency_key
            )
        except ValueError as exc:
            status_code = 404 if str(exc) == "batch not found" else 422
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        batch = repository.get_batch(batch_id)
        assert batch is not None
        return SourceIngestionResponse(
            source=source,
            batch=BatchResponse(**batch),
            job=ProcessingJobResponse(**job),
        )

    @api.post("/customers", response_model=SourceIngestionResponse, status_code=202)
    def ingest_customer(
        request: CustomerIngestionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> SourceIngestionResponse:
        return ingest_source(
            "customer_system",
            "customers.json",
            customer_ingestion_file(request),
            idempotency_key,
        )

    @api.post("/accounts", response_model=SourceIngestionResponse, status_code=202)
    def ingest_account(
        request: AccountIngestionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> SourceIngestionResponse:
        return ingest_source(
            "account_system",
            "accounts.csv",
            account_ingestion_file(request),
            idempotency_key,
        )

    @api.post("/transactions", response_model=SourceIngestionResponse, status_code=202)
    def ingest_transaction(
        request: TransactionIngestionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> SourceIngestionResponse:
        return ingest_source(
            "transaction_system",
            "transactions.jsonl",
            transaction_ingestion_file(request),
            idempotency_key,
        )

    @api.post("/interactions", response_model=SourceIngestionResponse, status_code=202)
    def ingest_interaction(
        request: InteractionIngestionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> SourceIngestionResponse:
        return ingest_source(
            "interaction_system",
            "interactions.jsonl",
            interaction_ingestion_file(request),
            idempotency_key,
        )

    @api.post("/fraud-events", response_model=SourceIngestionResponse, status_code=202)
    def ingest_fraud_event(
        request: FraudEventIngestionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> SourceIngestionResponse:
        return ingest_source(
            "fraud_system",
            "fraud-events.jsonl",
            fraud_event_ingestion_file(request),
            idempotency_key,
        )

    @api.post(
        "/upload-sample-test",
        response_model=ObservationUploadResponse,
        status_code=202,
    )
    def upload_observation(
        request: ObservationUploadRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> ObservationUploadResponse:
        validate_idempotency_key(idempotency_key)
        batch_id = service.create("single_observation")
        for filename, content in observation_files(request):
            service.upload_file(batch_id, filename, [content])
        try:
            job = service.enqueue_processing(batch_id, idempotency_key)
        except ValueError as exc:
            status_code = 404 if str(exc) == "batch not found" else 422
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        batch = repository.get_batch(batch_id)
        assert batch is not None
        return ObservationUploadResponse(
            batch=BatchResponse(**batch), job=ProcessingJobResponse(**job)
        )

    @api.post(
        "/batches/{batch_id}/files", response_model=UploadResponse, status_code=201
    )
    def upload_file(
        batch_id: str,
        file: UploadFile = File(...),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> UploadResponse:
        if repository.get_batch(batch_id) is None:
            raise HTTPException(status_code=404, detail="batch not found")
        if not file.filename:
            raise HTTPException(status_code=422, detail="filename is required")
        if Path(file.filename).suffix.lower() not in {".json", ".jsonl", ".csv"}:
            raise HTTPException(
                status_code=415, detail="only JSON, JSONL, and CSV files are supported"
            )
        record = service.upload_file(
            batch_id, file.filename, iter(lambda: file.file.read(1024 * 1024), b"")
        )
        size = service.storage.size(record.storage_key)
        return UploadResponse(
            batch_id=record.batch_id,
            file_id=record.file_id,
            filename=record.filename,
            storage_key=record.storage_key,
            size_bytes=size,
        )

    @api.post(
        "/batches/{batch_id}/process",
        response_model=ProcessEnqueueResponse,
        status_code=202,
    )
    def process_batch(
        batch_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> ProcessEnqueueResponse:
        validate_idempotency_key(idempotency_key)
        try:
            job = service.enqueue_processing(batch_id, idempotency_key)
        except ValueError as exc:
            status_code = 404 if str(exc) == "batch not found" else 422
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        batch = repository.get_batch(batch_id)
        assert batch is not None
        return ProcessEnqueueResponse(
            batch=BatchResponse(**batch), job=ProcessingJobResponse(**job)
        )

    @api.get("/batches/{batch_id}", response_model=BatchResponse)
    def get_batch(
        batch_id: str,
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> BatchResponse:
        batch = repository.get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="batch not found")
        return BatchResponse(**batch)

    @api.get("/batches/{batch_id}/lineage", response_model=LineageResponse)
    def get_batch_lineage(
        batch_id: str,
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> LineageResponse:
        batch = repository.get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="batch not found")
        return LineageResponse(
            batch_id=batch_id,
            source=str(batch["source"]),
            status=str(batch["status"]),
            created_at=cast(datetime, batch["created_at"]),
            updated_at=cast(datetime, batch["updated_at"]),
            files=[
                LineageFileResponse(
                    file_id=file.file_id,
                    filename=file.filename,
                    storage_key=file.storage_key,
                )
                for file in repository.list_files(batch_id)
            ],
            field_lineage=FIELD_LINEAGE,
        )

    @api.get("/customers/{customer_id}", response_model=CustomerResponse)
    def get_customer(
        customer_id: str,
        as_of: datetime | None = Query(default=None),
        claims: dict[str, Any] = Depends(require_role("reader", "pii_reader", "admin")),
    ) -> CustomerResponse:
        try:
            customer = repository.get_customer_snapshot(customer_id, as_of)
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")
        if not has_pii_access(claims):
            customer = redact_customer(customer)
        return CustomerResponse(**customer)

    @api.get(
        "/customers/{customer_id}/transactions",
        response_model=list[CustomerTransactionResponse],
    )
    def list_customer_transactions(
        customer_id: str,
        limit: int = Query(default=1000, ge=1, le=10000),
        _: dict[str, Any] = Depends(require_role("reader", "pii_reader", "admin")),
    ) -> list[CustomerTransactionResponse]:
        try:
            customer = repository.get_customer_snapshot(customer_id)
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")
        transactions = repository.list_customer_transactions(customer_id, limit)
        return [
            CustomerTransactionResponse(**transaction) for transaction in transactions
        ]

    @api.get("/customers", response_model=list[CustomerResponse])
    def list_customers(
        as_of: datetime | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        claims: dict[str, Any] = Depends(require_role("reader", "pii_reader", "admin")),
    ) -> list[CustomerResponse]:
        customers = repository.list_customer_snapshots(as_of=as_of, limit=limit)
        if not has_pii_access(claims):
            customers = [redact_customer(customer) for customer in customers]
        return [CustomerResponse(**customer) for customer in customers]

    @api.get("/summary", response_model=SummaryResponse)
    def get_summary(
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> SummaryResponse:
        return SummaryResponse(**repository.get_summary())

    @api.get("/status", response_model=SummaryResponse)
    def get_status(
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> SummaryResponse:
        return SummaryResponse(**repository.get_summary())

    @api.get("/summary/distributions", response_model=SummaryDistributionsResponse)
    def get_summary_distributions(
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> SummaryDistributionsResponse:
        return SummaryDistributionsResponse(**repository.get_distributions())

    @api.get("/summary/analytics", response_model=AnalyticsSummaryResponse)
    def get_analytics_summary(
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> AnalyticsSummaryResponse:
        return AnalyticsSummaryResponse(**repository.get_analytics_summary())

    @api.get("/quality", response_model=list[QualityIssueResponse])
    def get_quality(
        batch_id: str | None = None,
        filename: str | None = None,
        issue_type: str | None = None,
        limit: int = 100,
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> list[QualityIssueResponse]:
        safe_limit = min(max(limit, 1), 5000)
        return [
            QualityIssueResponse(**issue)
            for issue in repository.get_quality_issues(
                batch_id=batch_id,
                filename=filename,
                issue_type=issue_type,
                limit=safe_limit,
            )
        ]

    @api.get("/quality/summary", response_model=QualitySummaryResponse)
    def get_quality_summary(
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> QualitySummaryResponse:
        return QualitySummaryResponse(**repository.get_quality_summary())

    if enable_ground_truth:

        @api.get("/ground-truth", response_model=GroundTruthResponse)
        def get_ground_truth(
            _: dict[str, Any] = Depends(require_role("admin")),
        ) -> GroundTruthResponse:
            report = ground_truth.read()
            return GroundTruthResponse(
                source=report.source,
                description=report.description,
                total=report.total,
                confirmed=report.confirmed,
                evidence_found=report.evidence_found,
                evidence_missing=report.evidence_missing,
                labels_by_type=report.labels_by_type,
                subtypes=report.subtypes,
                records=[
                    GroundTruthRecord(**record.__dict__) for record in report.records
                ],
                quality_ground_truth=report.quality_ground_truth,
            )

    return api
