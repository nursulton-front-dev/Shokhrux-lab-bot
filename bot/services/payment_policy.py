"""Authoritative server-side tariff amounts (integer UZS)."""

TARIFF_PRICES: dict[int, int] = {1: 500_000, 3: 1_200_000, 6: 2_300_000}

# Only these methods may carry a 0 UZS invoice: the tariff is paid from balance.
BALANCE_ONLY_METHODS = frozenset({"cashback"})


class PaymentValidationError(ValueError):
    """A payment cannot be completed without changing its financial terms."""


def assert_order_matches_tariff(*, amount: int, cashback_applied: int | None,
                                tariff_months: int, payment_method: str) -> None:
    """Reject an order whose money terms no longer add up to its tariff.

    `amount` (what the payer transfers) plus `cashback_applied` (what the
    balance covers) must equal the tariff price exactly; both are whole UZS,
    never tiyin. Anything else means the row was edited after it was minted
    (a test hack, a manual "discount", a migration) and must not activate a
    subscription at a price the tariff table does not know.
    """
    price = TARIFF_PRICES.get(tariff_months)
    cashback = cashback_applied or 0
    if (price is None or amount < 0 or cashback < 0 or amount + cashback != price
            or (payment_method in BALANCE_ONLY_METHODS and amount != 0)):
        raise PaymentValidationError("Payment amount does not match its tariff")
