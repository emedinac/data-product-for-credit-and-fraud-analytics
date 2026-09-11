from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

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
    status: str | None
    customer_type: str | None
    country: str | None
    account_count: int
    total_credit_limit: float | None
    total_balance: float | None
    transaction_count: int
    transaction_amount: float
    declined_transaction_count: int
    fraud_event_count: int
    confirmed_fraud_count: int
    last_transaction_at: datetime | None


class SummaryResponse(BaseModel):
    customer_count: int
    account_count: int
    transaction_count: int
    fraud_event_count: int
    confirmed_fraud_count: int
    quarantined_count: int
    last_batch_id: str | None
    last_batch_status: str | None


class DistributionItem(BaseModel):
    label: str
    count: int


class SummaryDistributionsResponse(BaseModel):
    customers_by_status: list[DistributionItem]
    transactions_by_status: list[DistributionItem]


def router(service: BatchService, repository: PostgresRepository) -> APIRouter:
    api = APIRouter(prefix="/v1")

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

    @api.get(
        "/summary/distributions", response_model=SummaryDistributionsResponse
    )
    def get_summary_distributions() -> SummaryDistributionsResponse:
        return SummaryDistributionsResponse(**repository.get_distributions())

    return api
