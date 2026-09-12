import json
import logging
from typing import Any

logger = logging.getLogger("customer_data_product.metrics")


def emit_metric(name: str, **fields: Any) -> None:
    """Emit a log-shaped metric that can be shipped to a metrics backend."""
    logger.info(json.dumps({"metric": name, **fields}, default=str, sort_keys=True))
