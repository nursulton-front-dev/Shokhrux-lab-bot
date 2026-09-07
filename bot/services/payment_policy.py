"""Authoritative server-side tariff amounts (integer UZS)."""

TARIFF_PRICES: dict[int, int] = {1: 500_000, 3: 1_200_000, 6: 2_300_000}


class PaymentValidationError(ValueError):
    """A payment cannot be completed without changing its financial terms."""
