import re
import unicodedata
from typing import Any


def normalize_name(value: Any) -> str | None:
    """Return a stable snake_case representation for source labels."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", normalized)
    return normalized.strip("_").lower() or None
