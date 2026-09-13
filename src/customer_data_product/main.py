from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from customer_data_product.adapters.ground_truth import LocalGroundTruthReader
from customer_data_product.adapters.http.api import router
from customer_data_product.adapters.persistence.postgres import PostgresRepository
from customer_data_product.bootstrap import build_service
from customer_data_product.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    service = build_service(settings)
    repository = service.batches
    assert isinstance(repository, PostgresRepository)
    app = FastAPI(title="Customer Data Product", version="0.1.0")

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(
        router(
            service,
            repository,
            LocalGroundTruthReader(settings.raw_root),
            enable_ground_truth=settings.enable_ground_truth,
            auth_audience=settings.auth_audience,
            auth_role_bindings=settings.auth_role_bindings,
            auth_consumer_entitlements=settings.auth_consumer_entitlements,
            auth_mode=settings.auth_mode,
            local_auth_token=settings.local_auth_token,
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
