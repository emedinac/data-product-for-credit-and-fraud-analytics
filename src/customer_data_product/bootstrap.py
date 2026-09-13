from customer_data_product.adapters.events import LocalEventPublisher
from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.adapters.processing.local_processor import LocalProcessor
from customer_data_product.adapters.storage.gcs import GCSObjectStorage
from customer_data_product.adapters.storage.local_filesystem import LocalObjectStorage
from customer_data_product.application.ports import ObjectStorage
from customer_data_product.application.services import BatchService
from customer_data_product.domain.currency import CurrencyPolicy
from customer_data_product.observability import configure_cloud_monitoring
from customer_data_product.settings import Settings


def build_service(settings: Settings) -> BatchService:
    configure_cloud_monitoring(settings.gcp_project_id)
    storage: ObjectStorage
    if settings.storage_backend.lower() == "gcs":
        if not settings.storage_bucket:
            raise ValueError("STORAGE_BUCKET is required when STORAGE_BACKEND=gcs")
        storage = GCSObjectStorage(settings.storage_bucket)
    else:
        storage = LocalObjectStorage(settings.lake_root)
    repository = PostgresRepository(settings.database_url, settings.base_currency)
    repository.initialize()
    processor = LocalProcessor(
        storage,
        repository,
        CurrencyPolicy(
            base_currency=settings.base_currency,
            rates={
                key.upper(): value for key, value in settings.exchange_rates.items()
            },
            source=settings.exchange_rate_source,
            rate_timestamp=settings.exchange_rate_timestamp,
            max_rate_age_seconds=settings.exchange_rate_max_age_seconds,
        ),
    )
    return BatchService(
        repository,
        storage,
        LocalEventPublisher(),
        processor,
        settings.quality_thresholds,
        settings.processing_max_attempts,
    )
