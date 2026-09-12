from dataclasses import dataclass
from typing import Mapping, cast


@dataclass(frozen=True)
class QualityThresholds:
    max_quarantine_rate: float = 0.05
    max_duplicate_rate: float = 0.05
    max_referential_integrity_failure_rate: float = 0.0
    min_required_field_completeness: float = 0.99
    max_volume_change_rate: float = 0.50
    max_freshness_seconds: float = 86_400.0


@dataclass(frozen=True)
class QualityAssessment:
    status: str
    failures: tuple[str, ...]
    total_count: int
    quarantine_rate: float
    duplicate_rate: float
    referential_integrity_failure_rate: float
    required_field_completeness: float
    volume_change_rate: float | None
    freshness_seconds: float | None


def assess_quality(
    counts: Mapping[str, object],
    thresholds: QualityThresholds,
) -> QualityAssessment:
    total = cast(int, counts.get("total_count", 0))
    quarantined = cast(int, counts.get("quarantined_count", 0))
    duplicates = cast(int, counts.get("duplicate_count", 0))
    referential = cast(int, counts.get("referential_integrity_failure_count", 0))
    required_failures = cast(int, counts.get("required_field_failure_count", 0))
    denominator = total or 1
    quarantine_rate = quarantined / denominator
    duplicate_rate = duplicates / denominator
    referential_rate = referential / denominator
    completeness = max(0.0, 1.0 - required_failures / denominator)
    volume_change = counts.get("volume_change_rate")
    freshness = counts.get("freshness_seconds")
    volume_change_rate = (
        cast(float, volume_change) if volume_change is not None else None
    )
    freshness_seconds = cast(float, freshness) if freshness is not None else None

    failures: list[str] = []
    if total == 0:
        failures.append("EMPTY_BATCH")
    if quarantine_rate > thresholds.max_quarantine_rate:
        failures.append("QUARANTINE_RATE")
    if duplicate_rate > thresholds.max_duplicate_rate:
        failures.append("DUPLICATE_RATE")
    if referential_rate > thresholds.max_referential_integrity_failure_rate:
        failures.append("REFERENTIAL_INTEGRITY")
    if completeness < thresholds.min_required_field_completeness:
        failures.append("REQUIRED_FIELD_COMPLETENESS")
    if (
        volume_change_rate is not None
        and volume_change_rate > thresholds.max_volume_change_rate
    ):
        failures.append("VOLUME_ANOMALY")
    if (
        freshness_seconds is not None
        and freshness_seconds > thresholds.max_freshness_seconds
    ):
        failures.append("FRESHNESS")
    return QualityAssessment(
        status="PASSED" if not failures else "FAILED",
        failures=tuple(failures),
        total_count=total,
        quarantine_rate=quarantine_rate,
        duplicate_rate=duplicate_rate,
        referential_integrity_failure_rate=referential_rate,
        required_field_completeness=completeness,
        volume_change_rate=volume_change_rate,
        freshness_seconds=freshness_seconds,
    )
