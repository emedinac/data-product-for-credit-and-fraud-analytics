import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
        self.raw_root = raw_root

    def _evidence_records(self) -> dict[str, list[dict[str, Any]]]:
        records_by_scenario: dict[str, list[dict[str, Any]]] = {}
        for path in self.raw_root.rglob("*.jsonl"):
            if path.parent.name == "ground_truth":
                continue
            with path.open(encoding="utf-8", errors="replace") as source:
                for line in source:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict) and value.get("scenario_id"):
                        scenario_id = str(value["scenario_id"])
                        records_by_scenario.setdefault(scenario_id, []).append(
                            value
                        )
        return records_by_scenario

    @staticmethod
    def _explanation(
        label: str,
        subtype: str | None,
        confirmed: bool,
        evidence_found: bool,
        event_types: list[str],
    ) -> str:
        classification = label
        if subtype:
            classification += f" ({subtype})"
        confirmation = "confirmed" if confirmed else "not confirmed"
        if not evidence_found:
            return f"{classification}: {confirmation}. Evidence: none."
        events = ", ".join(event_types) if event_types else "no event types"
        return f"{classification}: {confirmation}. Evidence: {events}."

    @staticmethod
    def _prediction(
        label: str, evidence_records: list[dict[str, Any]]
    ) -> tuple[str, str, bool]:
        predicted_fraud = any(
            record.get("event_type") == "fraud_event"
            and isinstance(record.get("classification"), dict)
            and bool(record["classification"].get("confirmed"))
            for record in evidence_records
        )
        predicted_label = "fraud" if predicted_fraud else "not_fraud"
        ground_truth_fraud = label == "fraud"
        misclassified = predicted_fraud != ground_truth_fraud
        result = "misclassified" if misclassified else "correct"
        return predicted_label, result, misclassified

    def read(self) -> GroundTruthReport:
        records: list[GroundTruthLabel] = []
        evidence_records = self._evidence_records()
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
                    scenario_evidence = evidence_records.get(str(scenario_id), [])
                    customer_ids = sorted(
                        {
                            str(record["customer_id"])
                            for record in scenario_evidence
                            if record.get("customer_id")
                        }
                    )
                    transaction_ids = sorted(
                        {
                            str(record["transaction_id"])
                            for record in scenario_evidence
                            if record.get("transaction_id")
                        }
                    )
                    event_types = sorted(
                        {
                            str(record["event_type"])
                            for record in scenario_evidence
                            if record.get("event_type")
                        }
                    )
                    evidence_found = bool(scenario_evidence)
                    predicted_label, classification_result, misclassified = (
                        self._prediction(str(label), scenario_evidence)
                    )
                    subtype = (
                        str(value["subtype"]) if value.get("subtype") else None
                    )
                    explanation = self._explanation(
                        str(label),
                        subtype,
                        bool(value.get("confirmed", False)),
                        evidence_found,
                        event_types,
                    )
                    explanation += (
                        f" Prediction: {predicted_label}; {classification_result}."
                    )
                    records.append(
                        GroundTruthLabel(
                            scenario_id=str(scenario_id),
                            label=str(label),
                            subtype=subtype,
                            confirmed=bool(value.get("confirmed", False)),
                            evidence_found=evidence_found,
                            customer_id=(
                                customer_ids[0] if customer_ids else None
                            ),
                            transaction_ids=tuple(transaction_ids),
                            event_types=tuple(event_types),
                            evidence_records=tuple(scenario_evidence),
                            explanation=explanation,
                            predicted_label=predicted_label,
                            classification_result=classification_result,
                            misclassified=misclassified,
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
