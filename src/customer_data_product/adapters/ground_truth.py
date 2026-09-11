import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from customer_data_product.domain.models import GroundTruthLabel


@dataclass(frozen=True)
class GroundTruthReport:
    source: str
    description: str
    total: int
    confirmed: int
    evidence_found: int
    evidence_missing: int
    labels_by_type: dict[str, int]
    subtypes: dict[str, int]
    records: list[GroundTruthLabel]


class LocalGroundTruthReader:
    def __init__(self, raw_root: Path) -> None:
        self.path = raw_root / "ground_truth" / "scenario_labels.jsonl"
        self.scenario_path = raw_root / "mixed_events"

    def _evidence_ids(self) -> set[str]:
        scenario_ids: set[str] = set()
        for path in self.scenario_path.glob("*_scenario_*.jsonl"):
            with path.open(encoding="utf-8", errors="replace") as source:
                for line in source:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict) and value.get("scenario_id"):
                        scenario_ids.add(str(value["scenario_id"]))
        return scenario_ids

    def read(self) -> GroundTruthReport:
        records: list[GroundTruthLabel] = []
        evidence_ids = self._evidence_ids()
        if self.path.is_file():
            with self.path.open(encoding="utf-8") as source:
                for line in source:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(value, dict):
                        continue
                    scenario_id = value.get("scenario_id")
                    label = value.get("label")
                    if not scenario_id or not label:
                        continue
                    records.append(
                        GroundTruthLabel(
                            scenario_id=str(scenario_id),
                            label=str(label),
                            subtype=(
                                str(value["subtype"])
                                if value.get("subtype")
                                else None
                            ),
                            confirmed=bool(value.get("confirmed", False)),
                            evidence_found=str(scenario_id) in evidence_ids,
                        )
                    )

        return GroundTruthReport(
            source=str(self.path),
            description=(
                "Generated scenario labels for fraud and anomaly cases. "
                "They are evaluation labels, not operational fraud events."
            ),
            total=len(records),
            confirmed=sum(record.confirmed for record in records),
            evidence_found=sum(record.evidence_found for record in records),
            evidence_missing=sum(
                not record.evidence_found for record in records
            ),
            labels_by_type=dict(Counter(record.label for record in records)),
            subtypes=dict(
                Counter(record.subtype for record in records if record.subtype)
            ),
            records=records,
        )
