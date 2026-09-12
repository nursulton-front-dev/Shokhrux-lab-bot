"""Expire orders and provider reservations under the same money locks."""
import datetime

from sqlalchemy import or_, select

from bot.database.models import ClickTransaction, PaymeTransaction
from bot.services.cashback import release_cashback
from bot.services.click.protocol import PREPARE_TIMEOUT
from bot.services.payme.protocol import TRANSACTION_TIMEOUT_MS, CANCEL_REASON_TIMEOUT
from bot.services.payment_policy import ORDER_TTL
from bot.services.rahmat import _lock_payment

UTC = datetime.timezone.utc


def gateway_live_predicates(now):
    return (
        (ClickTransaction.state == 1) & (ClickTransaction.created_at > now - PREPARE_TIMEOUT),
        (PaymeTransaction.state == 1) & (PaymeTransaction.payme_time > int(now.timestamp()*1000) - TRANSACTION_TIMEOUT_MS),
    )


async def gateway_is_active(session, payment_id: int) -> bool:
    now = datetime.datetime.now(UTC)
    click_live, payme_live = gateway_live_predicates(now)
    return bool(await session.scalar(select(or_(
        select(ClickTransaction.id).where(ClickTransaction.payment_id == payment_id, click_live).exists(),
        select(PaymeTransaction.id).where(PaymeTransaction.payment_id == payment_id, payme_live).exists(),
    ))))


async def expire_pending_order(session, payment_id: int, now: datetime.datetime) -> bool:
    """Caller owns commit. Gateway creation/completion takes these same locks."""
    payment, user, _ = await _lock_payment(session, payment_id)
    if payment is None or user is None or payment.status != 'pending':
        return False
    click = list((await session.scalars(select(ClickTransaction).where(
        ClickTransaction.payment_id == payment_id, ClickTransaction.state.in_((1, 2))
    ).with_for_update())).all())
    payme = list((await session.scalars(select(PaymeTransaction).where(
        PaymeTransaction.payment_id == payment_id, PaymeTransaction.state.in_((1, 2))
    ).with_for_update())).all())
    # Confirmed gateway + pending order is a reconciliation issue, never auto-cancel it.
    if any(t.state == 2 for t in [*click, *payme]):
        return False
    if any(t.created_at > now - PREPARE_TIMEOUT for t in click):
        return False
    if any(t.payme_time > int(now.timestamp()*1000) - TRANSACTION_TIMEOUT_MS for t in payme):
        return False
    if not (click or payme) and payment.created_at > now - ORDER_TTL:
        return False
    for transaction in click:
        transaction.state = -1
        transaction.cancel_reason = -9
        transaction.cancelled_at = now
    for transaction in payme:
        transaction.state = -1
        transaction.reason = CANCEL_REASON_TIMEOUT
        transaction.cancelled_at = now
    release_cashback(user, payment)
    payment.status = 'failed'
    return True
