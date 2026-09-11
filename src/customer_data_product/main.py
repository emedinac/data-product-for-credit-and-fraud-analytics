from fastapi import FastAPI

from customer_data_product.adapters.events import LocalEventPublisher
from customer_data_product.adapters.ground_truth import LocalGroundTruthReader
from customer_data_product.adapters.http.api import router
from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.adapters.processing.local_processor import LocalProcessor
from customer_data_product.adapters.storage.local_filesystem import LocalObjectStorage
from customer_data_product.application.services import BatchService
from customer_data_product.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    storage = LocalObjectStorage(settings.lake_root)
    repository = PostgresRepository(settings.database_url)
    repository.initialize()
    processor = LocalProcessor(storage, repository)
    publisher = LocalEventPublisher()
    service = BatchService(repository, storage, publisher, processor)
    app = FastAPI(title="Customer Data Product", version="0.1.0")
    app.include_router(
        router(
            service,
            repository,
            LocalGroundTruthReader(settings.raw_root),
            enable_ground_truth=settings.enable_ground_truth,
        )
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "customer_data_product.main:app",
        host="0.0.0.0",
        port=settings.port,
    )
