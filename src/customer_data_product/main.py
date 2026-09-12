from fastapi import FastAPI, HTTPException

from customer_data_product.adapters.events import LocalEventPublisher
from customer_data_product.adapters.ground_truth import LocalGroundTruthReader
from customer_data_product.adapters.http.api import router
from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.adapters.processing.local_processor import LocalProcessor
from customer_data_product.adapters.storage.local_filesystem import LocalObjectStorage
from customer_data_product.application.services import BatchService
from customer_data_product.domain.currency import CurrencyPolicy
from customer_data_product.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    storage = LocalObjectStorage(settings.lake_root)
    repository = PostgresRepository(settings.database_url, settings.base_currency)
    repository.initialize()
    processor = LocalProcessor(
        storage,
        repository,
        CurrencyPolicy(
            base_currency=settings.base_currency,
            rates={
                key.upper(): value
                for key, value in settings.exchange_rates.items()
            },
            source=settings.exchange_rate_source,
            rate_timestamp=settings.exchange_rate_timestamp,
        ),
    )
    publisher = LocalEventPublisher()
    service = BatchService(
        repository,
        storage,
        publisher,
        processor,
        settings.quality_thresholds,
    )
    app = FastAPI(title="Customer Data Product", version="0.1.0")
    app.include_router(
        router(
            service,
            repository,
            LocalGroundTruthReader(settings.raw_root),
            enable_ground_truth=settings.enable_ground_truth,
            api_key=settings.api_key,
        )
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        try:
            repository.check_connection()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="database is not ready"
            ) from exc
        return {"status": "ready"}

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
