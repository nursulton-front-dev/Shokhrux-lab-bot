"""Constants, request parsing and signature checking for the Click SHOP API.

Click posts form-encoded callbacks and authenticates them with an MD5 digest of
selected fields concatenated around the merchant secret key. MD5 is not a choice
here: the digest layout is fixed by Click's protocol. The digest is taken over
the values exactly as they arrived, because `amount` is a decimal string whose
formatting Click owns ("500000.00"); reparsing and re-rendering it would produce
a different hash for the same request.
"""
import dataclasses
import datetime
import hashlib
import hmac
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from bot.services.click import errors

ACTION_PREPARE = 0
ACTION_COMPLETE = 1

# Merchant-side transaction states, mirroring bot.services.payme.protocol.
STATE_PREPARED = 1
STATE_CONFIRMED = 2
STATE_CANCELLED = -1
STATE_CANCELLED_AFTER_CONFIRM = -2

# Click abandons a prepared transaction it never confirms; after this window the
# merchant releases the order instead of holding it reserved forever.
PREPARE_TIMEOUT = datetime.timedelta(hours=12)
CANCEL_REASON_TIMEOUT = -9
# The order stopped pricing its tariff between Prepare and Complete.
CANCEL_REASON_REJECTED = -2

# Click quotes sums in UZS with decimals; the bot stores tariffs in whole UZS.
TIYIN_PER_SUM = 100

# Order payment method routed through this endpoint.
METHOD_CLICK = "click"
CLICK_METHODS = frozenset({METHOD_CLICK})

PAY_URL = "https://my.click.uz/services/pay"

SIGNED_FIELDS = ("click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time")
REQUIRED_FIELDS = (*SIGNED_FIELDS, "sign_string")
MAX_FIELD_LENGTH = 128


@dataclasses.dataclass(frozen=True, slots=True)
class ClickRequest:
    action: int
    click_trans_id: int
    service_id: int
    click_paydoc_id: int | None
    order_id: int
    merchant_prepare_id: int | None
    amount_tiyin: int
    error: int


def build_pay_url(*, service_id: int, merchant_id: int, amount: int, order_id: int) -> str:
    """Checkout link for an order priced in whole UZS.

    `transaction_param` is the order id (`payments.id`) and comes back verbatim
    as `merchant_trans_id`; `amount` is rendered the way Click echoes it
    ("500000.00"), so the link, Prepare and Complete all quote the same string.
    """
    if not isinstance(order_id, int) or isinstance(order_id, bool) or order_id <= 0:
        raise ValueError(f"order_id must be a positive int, got {order_id!r}")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError(f"amount must be a positive int of UZS, got {amount!r}")
    query = urlencode({
        "service_id": service_id,
        "merchant_id": merchant_id,
        "amount": f"{amount:.2f}",
        "transaction_param": order_id,
    })
    return f"{PAY_URL}?{query}"


def to_tiyin(amount: str) -> int | None:
    """Convert Click's decimal sum to tiyin so comparisons stay exact."""
    try:
        value = Decimal(amount.strip())
    except (AttributeError, InvalidOperation):
        return None
    tiyin = value.scaleb(2)
    if tiyin < 0 or tiyin != tiyin.to_integral_value():
        return None
    return int(tiyin)


def sum_to_tiyin(amount_uzs: int) -> int:
    return amount_uzs * TIYIN_PER_SUM


def expected_signature(secret_key: str, raw: Mapping[str, str], action: int) -> str:
    """Digest the fields in the order Click documents for this action."""
    parts = [raw["click_trans_id"], raw["service_id"], secret_key, raw["merchant_trans_id"]]
    if action == ACTION_COMPLETE:
        parts.append(raw.get("merchant_prepare_id", ""))
    parts += [raw["amount"], raw["action"], raw["sign_time"]]
    return hashlib.md5("".join(parts).encode("utf-8")).hexdigest()


def _require_int(raw: Mapping[str, str], field: str, code: int) -> int:
    value = raw.get(field, "").strip()
    if not value.lstrip("-").isdigit():
        raise errors.ClickError(code, f"{field}={value!r} is not an integer")
    return int(value)


def parse_request(
    raw: Mapping[str, str], action: int, *, secret_key: str | None, service_id: int | None
) -> ClickRequest:
    """Validate the callback and return it as typed values.

    Nothing but the signed fields is trusted before the digest matches, so a
    forged body cannot steer parsing or reach the database.
    """
    if secret_key is None or service_id is None:
        raise errors.ClickError(errors.SIGN_CHECK_FAILED, "Click credentials are not configured")
    missing = [field for field in REQUIRED_FIELDS if not raw.get(field, "").strip()]
    if missing:
        raise errors.ClickError(errors.BAD_REQUEST, f"missing fields: {','.join(missing)}")
    if any(len(raw[field]) > MAX_FIELD_LENGTH for field in REQUIRED_FIELDS):
        raise errors.ClickError(errors.BAD_REQUEST, "field longer than the protocol allows")
    if _require_int(raw, "action", errors.ACTION_NOT_FOUND) != action:
        raise errors.ClickError(errors.ACTION_NOT_FOUND, f"action={raw['action']!r} on this endpoint")
    digest = expected_signature(secret_key, raw, action)
    if not hmac.compare_digest(raw["sign_string"].strip().lower(), digest):
        raise errors.ClickError(errors.SIGN_CHECK_FAILED, "sign_string does not match")
    if _require_int(raw, "service_id", errors.BAD_REQUEST) != service_id:
        raise errors.ClickError(errors.BAD_REQUEST, "callback addressed to another service_id")

    amount_tiyin = to_tiyin(raw["amount"])
    if amount_tiyin is None or amount_tiyin <= 0:
        raise errors.ClickError(errors.INCORRECT_AMOUNT, f"amount={raw['amount']!r}")
    order_field = raw["merchant_trans_id"].strip()
    if not order_field.isdigit():
        raise errors.ClickError(errors.ORDER_NOT_FOUND, f"merchant_trans_id={order_field!r}")
    merchant_prepare_id = None
    if action == ACTION_COMPLETE:
        merchant_prepare_id = _require_int(raw, "merchant_prepare_id", errors.TRANSACTION_NOT_FOUND)
    paydoc = raw.get("click_paydoc_id", "").strip()
    return ClickRequest(
        action=action,
        click_trans_id=_require_int(raw, "click_trans_id", errors.BAD_REQUEST),
        service_id=service_id,
        click_paydoc_id=int(paydoc) if paydoc.isdigit() else None,
        order_id=int(order_field),
        merchant_prepare_id=merchant_prepare_id,
        amount_tiyin=amount_tiyin,
        # Click reports its own failure in `error`; absent means success so far.
        error=_require_int(raw, "error", errors.BAD_REQUEST) if raw.get("error", "").strip() else 0,
    )
