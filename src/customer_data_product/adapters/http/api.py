from datetime import date, datetime
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
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
    declined_transaction_count: int
    fraud_event_count: int
    confirmed_fraud_count: int
    interaction_count: int
    last_transaction_at: datetime | None
    batch_id: str
    updated_at: datetime


class LineageFileResponse(BaseModel):
    file_id: str
    filename: str
    storage_key: str


class LineageResponse(BaseModel):
    batch_id: str
    source: str
    status: str
    created_at: datetime
    updated_at: datetime
    files: list[LineageFileResponse]


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


class QualityIssueResponse(BaseModel):
    filename: str
    line_number: int | None
    issue_type: str
    detail: str


def router(
    service: BatchService,
    repository: PostgresRepository,
    ground_truth: LocalGroundTruthReader,
    enable_ground_truth: bool = False,
    api_key: str | None = None,
) -> APIRouter:
    def authenticate(x_api_key: str | None = Header(default=None)) -> None:
        if api_key and x_api_key != api_key:
            raise HTTPException(status_code=401, detail="invalid API key")

    api = APIRouter(prefix="/v1", dependencies=[Depends(authenticate)])

    @api.post("/batches", response_model=BatchResponse, status_code=201)
    def create_batch(request: BatchCreateRequest) -> BatchResponse:
        batch_id = service.create(request.source)
        batch = repository.get_batch(batch_id)
        assert batch is not None
        return BatchResponse(**batch)

    @api.post(
        "/batches/{batch_id}/files", response_model=UploadResponse, status_code=201
    )
    def upload_file(batch_id: str, file: UploadFile = File(...)) -> UploadResponse:
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
        size = Path(service.storage.root / record.storage_key).stat().st_size  # type: ignore[attr-defined]
        return UploadResponse(
            batch_id=record.batch_id,
            file_id=record.file_id,
            filename=record.filename,
            storage_key=record.storage_key,
            size_bytes=size,
        )

    @api.post("/batches/{batch_id}/process", response_model=BatchResponse)
    def process_batch(batch_id: str) -> BatchResponse:
        if repository.get_batch(batch_id) is None:
            raise HTTPException(status_code=404, detail="batch not found")
        service.process(batch_id)
        batch = repository.get_batch(batch_id)
        assert batch is not None
        return BatchResponse(**batch)

    @api.get("/batches/{batch_id}", response_model=BatchResponse)
    def get_batch(batch_id: str) -> BatchResponse:
        batch = repository.get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="batch not found")
        return BatchResponse(**batch)

    @api.get("/batches/{batch_id}/lineage", response_model=LineageResponse)
    def get_batch_lineage(batch_id: str) -> LineageResponse:
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
        )

    @api.get("/customers/{customer_id}", response_model=CustomerResponse)
    def get_customer(customer_id: str) -> CustomerResponse:
        try:
            customer = repository.get_customer_snapshot(customer_id)
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")
        return CustomerResponse(**customer)

    @api.get("/summary", response_model=SummaryResponse)
    def get_summary() -> SummaryResponse:
        return SummaryResponse(**repository.get_summary())

    @api.get("/status", response_model=SummaryResponse)
    def get_status() -> SummaryResponse:
        return get_summary()

    @api.get(
        "/summary/distributions", response_model=SummaryDistributionsResponse
    )
    def get_summary_distributions() -> SummaryDistributionsResponse:
        return SummaryDistributionsResponse(**repository.get_distributions())

    @api.get("/quality", response_model=list[QualityIssueResponse])
    def get_quality(
        filename: str | None = None,
        issue_type: str | None = None,
        limit: int = 100,
    ) -> list[QualityIssueResponse]:
        safe_limit = min(max(limit, 1), 500)
        return [
            QualityIssueResponse(**issue)
            for issue in repository.get_quality_issues(
                filename=filename,
                issue_type=issue_type,
                limit=safe_limit,
            )
        ]

    if enable_ground_truth:

        @api.get("/ground-truth", response_model=GroundTruthResponse)
        def get_ground_truth() -> GroundTruthResponse:
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
            )

    return api
