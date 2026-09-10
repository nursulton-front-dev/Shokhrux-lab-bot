"""Constants and conversions shared by the Payme Merchant API implementation."""
import base64
import datetime

from bot.services.payme.errors import ACCOUNT_FIELD

# Transaction states defined by Payme.
STATE_CREATED = 1
STATE_PERFORMED = 2
STATE_CANCELLED = -1
STATE_CANCELLED_AFTER_PERFORM = -2

# Payme abandons an unconfirmed transaction after 12 hours; the merchant must
# cancel it with reason 4 once that window has passed.
TRANSACTION_TIMEOUT_MS = 12 * 60 * 60 * 1000
CANCEL_REASON_TIMEOUT = 4

# Payme quotes every amount in tiyin; the bot stores tariffs in whole UZS.
TIYIN_PER_SUM = 100

CHECKOUT_URL = "https://checkout.paycom.uz"

# Order payment methods routed through this endpoint. Sandbox orders exist only
# to satisfy Payme's test suite and never grant a subscription.
METHOD_PAYME = "payme"
METHOD_PAYME_SANDBOX = "payme_sandbox"
PAYME_METHODS = frozenset({METHOD_PAYME, METHOD_PAYME_SANDBOX})


def now_ms() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)


def to_ms(moment: datetime.datetime | None) -> int:
    """Payme expects 0, not null, for a timestamp that has not happened yet."""
    if moment is None:
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return int(moment.timestamp() * 1000)


def from_ms(milliseconds: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(milliseconds / 1000, tz=datetime.timezone.utc)


def to_tiyin(amount_uzs: int) -> int:
    return amount_uzs * TIYIN_PER_SUM


def build_checkout_url(*, merchant_id: str, order_id: int, amount_uzs: int) -> str:
    """Hosted checkout link for an order priced in whole UZS.

    Payme takes its parameters as one base64 blob, and the account field must be
    the same one the Merchant API reads out of `params.account`.
    """
    params = f"m={merchant_id};ac.{ACCOUNT_FIELD}={order_id};a={to_tiyin(amount_uzs)}"
    return f"{CHECKOUT_URL}/{base64.b64encode(params.encode('utf-8')).decode('ascii')}"
