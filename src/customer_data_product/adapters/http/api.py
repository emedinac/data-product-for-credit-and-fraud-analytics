import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from customer_data_product.adapters.ground_truth import LocalGroundTruthReader
from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.application.services import BatchService


class BatchCreateRequest(BaseModel):
    source: str = Field(min_length=1, max_length=100)


class BatchResponse(BaseModel):
    batch_id: str
    source: str | None = None
    status: str
    files_count: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    quarantined_count: int = 0
    snapshot_count: int = 0


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
    batch_id: str
    updated_at: datetime
    effective_at: datetime | None
    as_of_time: datetime


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


def router(
    service: BatchService,
    repository: PostgresRepository,
    ground_truth: LocalGroundTruthReader,
    enable_ground_truth: bool = False,
    auth_audience: str | None = None,
    auth_role_bindings: str = "",
) -> APIRouter:
    try:
        role_bindings = json.loads(auth_role_bindings) if auth_role_bindings else {}
    except json.JSONDecodeError as exc:
        raise ValueError("AUTH_ROLE_BINDINGS must be valid JSON") from exc

    def authenticate(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            from google.auth.transport import requests  # type: ignore[import-untyped]
            from google.oauth2 import id_token  # type: ignore[import-untyped]

            claims = id_token.verify_oauth2_token(
                token, requests.Request(), audience=auth_audience
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail="invalid bearer token") from exc
        return cast(dict[str, Any], claims)

    def require_role(
        *allowed: str,
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def dependency(
            claims: dict[str, Any] = Depends(authenticate),
        ) -> dict[str, Any]:
            subject = str(claims.get("email") or claims.get("sub") or "")
            roles = set(claims.get("roles", []))
            configured_role = role_bindings.get(subject)
            if configured_role:
                roles.add(configured_role)
            if not roles.intersection(allowed):
                raise HTTPException(status_code=403, detail="insufficient role")
            return {**claims, "_roles": roles}

        return dependency

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

    @api.post("/batches/{batch_id}/process", response_model=BatchResponse)
    def process_batch(
        batch_id: str,
        _: dict[str, Any] = Depends(require_role("operator", "admin")),
    ) -> BatchResponse:
        if repository.get_batch(batch_id) is None:
            raise HTTPException(status_code=404, detail="batch not found")
        try:
            service.process(batch_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        batch = repository.get_batch(batch_id)
        assert batch is not None
        return BatchResponse(**batch)

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
        if not set(claims.get("_roles", claims.get("roles", []))).intersection(
            {"pii_reader", "admin"}
        ):
            customer = {
                **customer,
                "first_name": None,
                "last_name": None,
                "date_of_birth": None,
                "city": None,
            }
        return CustomerResponse(**customer)

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

    @api.get(
        "/summary/distributions", response_model=SummaryDistributionsResponse
    )
    def get_summary_distributions(
        _: dict[str, Any] = Depends(require_role("reader", "operator", "admin")),
    ) -> SummaryDistributionsResponse:
        return SummaryDistributionsResponse(**repository.get_distributions())

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
                    GroundTruthRecord(**record.__dict__)
                    for record in report.records
                ],
                quality_ground_truth=report.quality_ground_truth,
            )

    return api
