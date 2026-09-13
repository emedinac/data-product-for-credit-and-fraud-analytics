from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class CurrencyPolicy:
    """Conversion policy; rates are base units per one source unit."""

    base_currency: str = "USD"
    rates: dict[str, Decimal] | None = None
    source: str = "configured"
    rate_timestamp: datetime | None = None
    max_rate_age_seconds: int = 86400

    def __post_init__(self) -> None:
        if not self.base_currency.isalpha() or len(self.base_currency) != 3:
            raise ValueError("base_currency must be an ISO 4217-style code")
        for code, rate in (self.rates or {}).items():
            if len(code) != 3 or not code.isalpha() or rate <= 0:
                raise ValueError("exchange rates must have positive ISO currency keys")

    def convert(
        self, amount: Decimal, currency: str | None
    ) -> tuple[Decimal | None, Decimal | None, str | None, datetime | None]:
        if currency is None:
            return None, None, None, None
        code = currency.upper()
        base = self.base_currency.upper()
        rate = Decimal("1") if code == base else (self.rates or {}).get(code)
        if rate is None:
            return None, None, None, None
        if code != base:
            if self.rate_timestamp is None:
                return None, None, None, None
            age = (datetime.now(timezone.utc) - self.rate_timestamp).total_seconds()
            if age > self.max_rate_age_seconds or age < 0:
                return None, None, None, None
        return amount * rate, rate, self.source, self.rate_timestamp
