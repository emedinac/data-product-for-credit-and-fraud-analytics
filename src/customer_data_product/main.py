import os
from pathlib import Path

from fastapi import FastAPI

from customer_data_product.adapters.events import LocalEventPublisher
from customer_data_product.adapters.http.api import router
from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.adapters.processing.local_processor import LocalProcessor
from customer_data_product.adapters.storage.local_filesystem import LocalObjectStorage
from customer_data_product.application.services import BatchService


def create_app() -> FastAPI:
    storage = LocalObjectStorage(Path(os.getenv("LAKE_ROOT", "lake")))
    repository = PostgresRepository(
        os.getenv(
            "DATABASE_URL",
            "postgresql://customer:customer@localhost:5432/customer_product",
        )
    )
    repository.initialize()
    processor = LocalProcessor(storage, repository)
    publisher = LocalEventPublisher()
    service = BatchService(repository, storage, publisher, processor)
    app = FastAPI(title="Customer Data Product", version="0.1.0")
    app.include_router(router(service, repository))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "customer_data_product.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
