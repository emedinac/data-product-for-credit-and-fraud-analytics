from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from customer_data_product.domain.quality import QualityThresholds


class Settings(BaseSettings):
    database_url: str = (
        "postgresql://customer:customer@localhost:5432/customer_product"
    )
    lake_root: Path = Path("lake")
    storage_backend: str = "local"
    storage_bucket: str | None = None
    gcp_project_id: str | None = None
    raw_root: Path = Path("raw_dev")
    enable_ground_truth: bool = False
    port: int = 8000
    backend_url: str = "http://localhost:8000"
    backend_token: str | None = None
    auth_audience: str | None = None
    auth_role_bindings: str = ""
    auth_consumer_entitlements: str = ""
    max_quarantine_rate: float = 0.05
    max_duplicate_rate: float = 0.05
    max_referential_integrity_failure_rate: float = 0.0
    min_required_field_completeness: float = 0.99
    max_volume_change_rate: float = 0.50
    max_freshness_seconds: float = 86400.0
    base_currency: str = "USD"
    exchange_rate_source: str = "configured"
    exchange_rate_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    exchange_rate_max_age_seconds: int = 86400
    exchange_rates: dict[str, Decimal] = Field(default_factory=dict)
    processing_max_attempts: int = 3
    processing_retry_base_seconds: int = 30
    processing_job_lease_seconds: int = 1800
    processing_worker_poll_seconds: float = 2.0

    @property
    def quality_thresholds(self) -> QualityThresholds:
        return QualityThresholds(
            max_quarantine_rate=self.max_quarantine_rate,
            max_duplicate_rate=self.max_duplicate_rate,
            max_referential_integrity_failure_rate=(
                self.max_referential_integrity_failure_rate
            ),
            min_required_field_completeness=self.min_required_field_completeness,
            max_volume_change_rate=self.max_volume_change_rate,
            max_freshness_seconds=self.max_freshness_seconds,
        )

    model_config = SettingsConfigDict(
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
