import json
import logging
from typing import Any

from opentelemetry import metrics
from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger("customer_data_product.metrics")

processing_duration = Histogram(
    "customer_data_product_processing_duration_seconds",
    "Batch processing duration in seconds.",
)
quality_failures = Counter(
    "customer_data_product_quality_failures_total",
    "Batches that failed the quality gate.",
)
processing_failures = Counter(
    "customer_data_product_processing_failures_total",
    "Batch processing failures.",
)
freshness_seconds = Gauge(
    "customer_data_product_freshness_seconds",
    "Seconds between the newest source event and processing.",
)
volume_change_ratio = Gauge(
    "customer_data_product_volume_change_ratio",
    "Absolute batch volume change ratio from the previous batch.",
)
source_schema_drift = Counter(
    "customer_data_product_source_schema_drift_total",
    "Source files whose records do not match the expected required fields.",
)
exchange_rate_failures = Counter(
    "customer_data_product_exchange_rate_failures_total",
    "Transactions skipped from monetary totals due to missing or stale rates.",
)
airflow_task_failures = Counter(
    "customer_data_product_airflow_task_failures_total",
    "Failed Airflow task attempts for the customer data pipeline.",
)
sla_breaches = Counter(
    "customer_data_product_sla_breaches_total",
    "Batches that exceeded the end-to-end freshness SLA.",
)
end_to_end_sla_seconds = Gauge(
    "customer_data_product_end_to_end_sla_seconds",
    "Seconds from the newest source event to snapshot publication.",
)
worker_heartbeat = Gauge(
    "customer_data_product_worker_heartbeat",
    "Worker liveness signal; set to 1 on every polling loop.",
)
processing_queue_depth = Gauge(
    "customer_data_product_processing_queue_depth",
    "Number of queued or retryable processing jobs.",
)

_otel_instruments: dict[str, Any] = {}
_otel_values: dict[str, float] = {}


def _observable_value(name: str) -> Any:
    def callback(_options: Any) -> list[Observation]:
        return [Observation(_otel_values.get(name, 0.0))]

    return callback


def configure_cloud_monitoring(project_id: str | None) -> None:
    if not project_id or isinstance(metrics.get_meter_provider(), MeterProvider):
        return
    exporter = CloudMonitoringMetricsExporter(project_id=project_id)
    provider = MeterProvider(
        metric_readers=[PeriodicExportingMetricReader(exporter)]
    )
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter("customer_data_product")
    _otel_instruments.update(
        processing_duration=meter.create_histogram(
            "customer_data_product_processing_duration_seconds",
            unit="s",
        ),
        quality_failures=meter.create_counter(
            "customer_data_product_quality_failures_total"
        ),
        processing_failures=meter.create_counter(
            "customer_data_product_processing_failures_total"
        ),
        freshness_seconds=meter.create_observable_gauge(
            "customer_data_product_freshness_seconds",
            callbacks=[_observable_value("freshness_seconds")],
            unit="s",
        ),
        volume_change_ratio=meter.create_observable_gauge(
            "customer_data_product_volume_change_ratio",
            callbacks=[_observable_value("volume_change_ratio")],
        ),
        source_schema_drift=meter.create_counter(
            "customer_data_product_source_schema_drift_total"
        ),
        exchange_rate_failures=meter.create_counter(
            "customer_data_product_exchange_rate_failures_total"
        ),
        airflow_task_failures=meter.create_counter(
            "customer_data_product_airflow_task_failures_total"
        ),
        sla_breaches=meter.create_counter("customer_data_product_sla_breaches_total"),
        end_to_end_sla_seconds=meter.create_observable_gauge(
            "customer_data_product_end_to_end_sla_seconds",
            callbacks=[_observable_value("end_to_end_sla_seconds")],
            unit="s",
        ),
        worker_heartbeat=meter.create_observable_gauge(
            "customer_data_product_worker_heartbeat",
            callbacks=[_observable_value("worker_heartbeat")],
        ),
        processing_queue_depth=meter.create_observable_gauge(
            "customer_data_product_processing_queue_depth",
            callbacks=[_observable_value("processing_queue_depth")],
        ),
    )


def emit_metric(name: str, **fields: Any) -> None:
    """Emit a log-shaped metric that can be shipped to a metrics backend."""
    logger.info(json.dumps({"metric": name, **fields}, default=str, sort_keys=True))
    if name == "batch_processing":
        if fields.get("duration_seconds") is not None:
            duration = float(fields["duration_seconds"])
            processing_duration.observe(duration)
            if "processing_duration" in _otel_instruments:
                _otel_instruments["processing_duration"].record(duration)
        if fields.get("freshness_seconds") is not None:
            freshness = float(fields["freshness_seconds"])
            freshness_seconds.set(freshness)
            _otel_values["freshness_seconds"] = freshness
        if fields.get("volume_change_rate") is not None:
            volume = float(fields["volume_change_rate"])
            volume_change_ratio.set(volume)
            _otel_values["volume_change_ratio"] = volume
    elif name == "quality_gate" and fields.get("status") == "FAILED":
        quality_failures.inc()
        if "quality_failures" in _otel_instruments:
            _otel_instruments["quality_failures"].add(1)
    elif name == "processing_failure":
        processing_failures.inc()
        if "processing_failures" in _otel_instruments:
            _otel_instruments["processing_failures"].add(1)
    elif name == "source_schema_drift":
        source_schema_drift.inc()
        if "source_schema_drift" in _otel_instruments:
            _otel_instruments["source_schema_drift"].add(1)
    elif name == "exchange_rate_failure":
        exchange_rate_failures.inc()
        if "exchange_rate_failures" in _otel_instruments:
            _otel_instruments["exchange_rate_failures"].add(1)
    elif name == "airflow_task_failure":
        airflow_task_failures.inc()
        if "airflow_task_failures" in _otel_instruments:
            _otel_instruments["airflow_task_failures"].add(1)
    elif name == "sla_breach":
        sla_breaches.inc()
        if "sla_breaches" in _otel_instruments:
            _otel_instruments["sla_breaches"].add(1)
    elif name == "batch_published" and fields.get("end_to_end_sla_seconds") is not None:
        elapsed = float(fields["end_to_end_sla_seconds"])
        end_to_end_sla_seconds.set(elapsed)
        _otel_values["end_to_end_sla_seconds"] = elapsed
    elif name == "worker_heartbeat":
        worker_heartbeat.set(1)
        _otel_values["worker_heartbeat"] = 1
    elif name == "processing_queue_depth":
        depth = float(fields.get("depth", 0))
        processing_queue_depth.set(depth)
        _otel_values["processing_queue_depth"] = depth
