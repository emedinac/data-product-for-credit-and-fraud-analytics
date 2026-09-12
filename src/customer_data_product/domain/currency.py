from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class CurrencyPolicy:
    """Conversion policy; rates are base units per one source unit."""

    base_currency: str = "USD"
    rates: dict[str, Decimal] | None = None
    source: str = "configured"
    rate_timestamp: datetime | None = None

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
        return amount * rate, rate, self.source, self.rate_timestamp
