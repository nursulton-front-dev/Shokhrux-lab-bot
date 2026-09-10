"""Payment state transitions. Telegram is never called inside money transactions."""
import datetime

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import config
from bot.database.models import CashbackTransaction, Payment, PaymentDelivery, Subscription, User
from bot.services.payment_policy import PaymentValidationError, TARIFF_PRICES


async def generate_invoice_link(amount: int, user_id: int, tariff_months: int, payment_id: int) -> str:
    # The previous URL was locally fabricated, without merchant credentials,
    # signature, invoice API, webhook or reconciliation. Never present it as payable.
    raise PaymentValidationError("Rahmat Pay is not configured; use verified manual payment.")


async def create_payment_intent(
    session: AsyncSession, *, user_id: int, months: int, method: str,
    use_cashback: bool, request_key: str,
) -> Payment:
    """Serialize intent creation and deduplicate clicks on the same UI action."""
    try:
        price = TARIFF_PRICES.get(months)
        if price is None or method not in {"manual_card", "cashback", "click", "payme"}:
            raise PaymentValidationError("Invalid tariff or payment method")
        user = await session.scalar(select(User).where(User.telegram_id == user_id)
                                    .with_for_update().execution_options(populate_existing=True))
        if user is None:
            raise PaymentValidationError("Register before paying")
        existing = await session.scalar(select(Payment).where(Payment.request_key == request_key))
        if existing is not None:
            if existing.user_id != user_id:
                raise PaymentValidationError("Invalid payment owner")
            await session.commit()
            return existing
        balance = max(0, user.balance or 0)
        if method == "cashback" and balance < price:
            raise PaymentValidationError("Insufficient cashback")
        cashback = min(price, balance) if use_cashback else 0
        if method == "cashback" and cashback != price:
            raise PaymentValidationError("Cashback must cover the entire tariff")
        payment = Payment(user_id=user_id, amount=price-cashback, tariff_months=months,
                          status="pending", payment_method=method, cashback_applied=cashback,
                          request_key=request_key)
        session.add(payment)
        await session.commit()
        return payment
    except BaseException:
        await session.rollback()
        raise


async def _lock_payment(session: AsyncSession, payment_id: int) -> tuple[Payment | None, User | None, User | None]:
    # No locks/autoflush before the sorted User locks: referral cycles cannot invert
    # the lock order. Refresh ORM identities loaded earlier by a handler.
    row = (await session.execute(select(Payment.user_id, User.referred_by)
                                 .join(User, User.telegram_id == Payment.user_id)
                                 .where(Payment.id == payment_id))).one_or_none()
    if row is None:
        return None, None, None
    user_id, referrer_id = row
    ids = sorted({user_id, *([referrer_id] if referrer_id is not None else [])})
    users = {user.telegram_id: user for user in (await session.scalars(
        select(User).where(User.telegram_id.in_(ids)).order_by(User.telegram_id)
        .with_for_update().execution_options(populate_existing=True))).all()}
    user = users.get(user_id)
    if user is None or user.referred_by != referrer_id:
        raise PaymentValidationError("Referral changed during payment; retry confirmation")
    payment = await session.scalar(select(Payment).where(Payment.id == payment_id)
                                   .with_for_update().execution_options(populate_existing=True))
    return payment, user, users.get(referrer_id) if referrer_id != user_id else None


async def reject_pending_payment(payment_id: int, session: AsyncSession) -> int | None:
    """Only one of confirmation/rejection can win; caller receives the DB owner."""
    try:
        payment, user, _ = await _lock_payment(session, payment_id)
        if payment is None or user is None or payment.status != "pending":
            await session.rollback()
            return None
        payment.status = "failed"
        await session.commit()
        return user.telegram_id
    except BaseException:
        await session.rollback()
        raise


async def process_successful_payment(payment_id: int, session: AsyncSession, bot: Bot) -> bool:
    """Commit status, balance, ledger, subscription and delivery job exactly once.

    This function owns the transaction, including rollback on cancellation. The
    caller must persist the intent first and have no unrelated pending writes.
    Telegram delivery is retried independently by the durable delivery worker.
    """
    try:
        payment, user, referrer = await _lock_payment(session, payment_id)
        if payment is None or user is None or payment.status != "pending":
            await session.rollback()
            return False
        price = TARIFF_PRICES.get(payment.tariff_months)
        cashback = payment.cashback_applied or 0
        if (price is None or payment.amount < 0 or cashback < 0
                or payment.amount + cashback != price
                or (payment.payment_method == "cashback" and payment.amount != 0)):
            raise PaymentValidationError("Payment amount does not match its tariff")
        if (user.balance or 0) < cashback:
            raise PaymentValidationError("Insufficient cashback; reconcile the pending payment")
        completed_count = await session.scalar(select(func.count()).select_from(Payment).where(
            Payment.user_id == user.telegram_id, Payment.status == "completed")) or 0
        user.balance = (user.balance or 0) - cashback
        if cashback:
            session.add(CashbackTransaction(user_id=user.telegram_id, amount=cashback, type="spend",
                                           description=f"Payment #{payment.id}"))
        current_expiry = await session.scalar(select(func.max(Subscription.expires_at)).where(
            Subscription.user_id == user.telegram_id, Subscription.status == "active"))
        now = datetime.datetime.now(datetime.timezone.utc)
        started_at = max(now, current_expiry) if current_expiry else now
        sub = Subscription(user_id=user.telegram_id, status="active", tariff_months=payment.tariff_months,
                           started_at=started_at, expires_at=started_at + datetime.timedelta(days=30*payment.tariff_months))
        session.add(sub)
        payment.status = "completed"
        reward_recipient = None
        if completed_count == 0 and referrer is not None:
            reward = config.cashback_reward_amount
            if reward > 0:
                referrer.balance = (referrer.balance or 0) + reward
                session.add(CashbackTransaction(user_id=referrer.telegram_id, amount=reward, type="accrual",
                                               description=f"First purchase by {user.telegram_id}, payment #{payment.id}"))
                reward_recipient = referrer.telegram_id
        await session.flush()
        session.add(PaymentDelivery(payment_id=payment.id, subscription_id=sub.id, referrer_id=reward_recipient))
        await session.commit()
        return True
    except BaseException:
        await session.rollback()
        raise
