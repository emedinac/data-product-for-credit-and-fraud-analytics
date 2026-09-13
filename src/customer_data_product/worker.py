"""Durable processing worker. Run this separately from the HTTP API."""

import logging
import time
from typing import cast

from customer_data_product.application.services import BatchService
from customer_data_product.bootstrap import build_service
from customer_data_product.observability import emit_metric
from customer_data_product.settings import get_settings

logger = logging.getLogger(__name__)


def run_once(service: BatchService) -> bool:
    settings = get_settings()
    depth = service.batches.processing_queue_depth()
    emit_metric("worker_heartbeat")
    emit_metric("processing_queue_depth", depth=depth)
    job = service.batches.claim_processing_job(settings.processing_job_lease_seconds)
    if job is None:
        return False
    job_id = str(job["job_id"])
    batch_id = str(job["batch_id"])
    lock_token = str(job["lock_token"])
    attempts = cast(int, job["attempts"])
    try:
        service.process(batch_id)
    except Exception as exc:
        retry_delay = settings.processing_retry_base_seconds * (2 ** (attempts - 1))
        retry = service.batches.fail_processing_job(
            job_id, lock_token, str(exc), retry_delay
        )
        logger.exception("processing_job_failed job_id=%s retry=%s", job_id, retry)
    else:
        service.batches.complete_processing_job(job_id, lock_token)
        logger.info("processing_job_completed job_id=%s batch_id=%s", job_id, batch_id)
    return True


def run() -> None:
    settings = get_settings()
    service = build_service(settings)
    while True:
        if not run_once(service):
            time.sleep(settings.processing_worker_poll_seconds)


if __name__ == "__main__":
    run()
