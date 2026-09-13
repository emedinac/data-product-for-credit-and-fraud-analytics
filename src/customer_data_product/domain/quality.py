from dataclasses import dataclass
from math import log2
from typing import Mapping, cast

DistributionProfile = Mapping[str, Mapping[str, int]]


def jensen_shannon_divergence(
    current: Mapping[str, int], previous: Mapping[str, int]
) -> float:
    """Compare two categorical distributions with a bounded [0, 1] score."""
    current_total = sum(max(value, 0) for value in current.values())
    previous_total = sum(max(value, 0) for value in previous.values())
    if current_total == 0 and previous_total == 0:
        return 0.0
    if current_total == 0 or previous_total == 0:
        return 1.0

    labels = set(current) | set(previous)
    divergence = 0.0
    for label in labels:
        current_probability = max(current.get(label, 0), 0) / current_total
        previous_probability = max(previous.get(label, 0), 0) / previous_total
        midpoint = (current_probability + previous_probability) / 2
        if current_probability:
            divergence += (
                0.5 * current_probability * log2(current_probability / midpoint)
            )
        if previous_probability:
            divergence += (
                0.5 * previous_probability * log2(previous_probability / midpoint)
            )
    return divergence


def distribution_shift_scores(
    current: DistributionProfile, previous: DistributionProfile | None
) -> dict[str, float]:
    """Return one JSD score per profiled categorical dimension."""
    if previous is None:
        return {}
    dimensions = set(current) | set(previous)
    return {
        dimension: jensen_shannon_divergence(
            current.get(dimension, {}), previous.get(dimension, {})
        )
        for dimension in dimensions
    }


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
    if freshness_seconds is not None and freshness_seconds < 0:
        failures.append("FUTURE_EVENT_TIME")
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
