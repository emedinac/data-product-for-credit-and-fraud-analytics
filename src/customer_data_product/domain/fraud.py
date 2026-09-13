"""Explainable, history-based transaction risk assessment."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from statistics import median

from customer_data_product.domain.models import Transaction


@dataclass(frozen=True)
class FraudAssessment:
    score: Decimal
    decision: str
    reasons: tuple[str, ...]


class HistoryBasedFraudDetector:
    """Score a transaction against prior behavior for its customer/account.

    This is an explainable baseline for the prototype, not a trained ML model.
    It deliberately uses only historical transaction attributes and does not
    read confirmed fraud labels.
    """

    def assess(
        self, transaction: Transaction, history: list[Transaction]
    ) -> FraudAssessment:
        prior = [
            item
            for item in history
            if item.transaction_id != transaction.transaction_id
            and item.status != "reversed"
            and item.event_time < transaction.event_time
        ]
        if not prior:
            return FraudAssessment(Decimal("0"), "insufficient_history", ())

        account_history = [
            item for item in prior if item.account_id == transaction.account_id
        ]
        baseline = account_history or prior
        current_amount = self._amount(transaction)
        historical_amounts: list[Decimal] = []
        for item in baseline:
            amount = self._amount(item)
            if amount is not None:
                historical_amounts.append(amount)

        score = Decimal("0")
        reasons: list[str] = []
        if current_amount is not None and historical_amounts:
            typical_amount = Decimal(str(median(historical_amounts)))
            if typical_amount > 0:
                ratio = current_amount / typical_amount
                if ratio >= 5:
                    score += Decimal("0.55")
                    reasons.append("amount_at_least_5x_account_baseline")
                elif ratio >= 3:
                    score += Decimal("0.40")
                    reasons.append("amount_at_least_3x_account_baseline")
                elif ratio >= 2:
                    score += Decimal("0.20")
                    reasons.append("amount_at_least_2x_account_baseline")

        historical_merchants = {
            item.merchant_id for item in prior if item.merchant_id is not None
        }
        if (
            transaction.merchant_id is not None
            and historical_merchants
            and transaction.merchant_id not in historical_merchants
        ):
            score += Decimal("0.15")
            reasons.append("new_merchant_for_customer")

        historical_countries = {
            item.country for item in prior if item.country is not None
        }
        if (
            transaction.country is not None
            and historical_countries
            and transaction.country not in historical_countries
        ):
            score += Decimal("0.10")
            reasons.append("new_country_for_customer")

        recent_start = transaction.event_time - timedelta(hours=24)
        recent_count = sum(item.event_time >= recent_start for item in prior)
        if recent_count >= 5:
            score += Decimal("0.25")
            reasons.append("high_24h_transaction_velocity")
        elif recent_count >= 3:
            score += Decimal("0.15")
            reasons.append("elevated_24h_transaction_velocity")

        score = min(score, Decimal("1"))
        if score >= Decimal("0.75"):
            decision = "likely_fraud"
        elif score >= Decimal("0.50"):
            decision = "review"
        else:
            decision = "clear"
        return FraudAssessment(score, decision, tuple(reasons))

    @staticmethod
    def _amount(transaction: Transaction) -> Decimal | None:
        return transaction.amount_base_currency or transaction.amount
