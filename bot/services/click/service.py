"""Click SHOP API state machine.

Click retries prepare and complete until it receives a final answer, so each
handler is idempotent and keyed on `click_trans_id`. Money state lives in
`payments`; this module only drives the protocol and delegates the financial
commit to `bot.services.rahmat.process_successful_payment`.
"""
import datetime
import logging

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import ClickTransaction, Payment
from bot.services.click import errors
from bot.services.click.protocol import (
    CANCEL_REASON_REJECTED,
    CANCEL_REASON_TIMEOUT,
    CLICK_METHODS,
    PREPARE_TIMEOUT,
    STATE_CANCELLED,
    STATE_CONFIRMED,
    STATE_PREPARED,
    ClickRequest,
    sum_to_tiyin,
)
from bot.services.payment_policy import PaymentValidationError, assert_order_matches_tariff, order_is_expired
from bot.services.rahmat import process_successful_payment, _lock_payment
from bot.services.cashback import release_cashback, reserve_cashback

logger = logging.getLogger(__name__)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _is_expired(transaction: ClickTransaction) -> bool:
    created_at = transaction.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=datetime.timezone.utc)
    return _utcnow() - created_at >= PREPARE_TIMEOUT


async def _lock_transaction(session: AsyncSession, click_trans_id: int) -> ClickTransaction | None:
    payment_id = await session.scalar(select(ClickTransaction.payment_id).where(ClickTransaction.click_trans_id == click_trans_id))
    if payment_id is None:
        return None
    await _lock_payment(session, payment_id)
    return await session.scalar(
        select(ClickTransaction)
        .where(ClickTransaction.click_trans_id == click_trans_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _load_order(session: AsyncSession, order_id: int, *, lock: bool = False) -> Payment:
    statement = select(Payment).where(Payment.id == order_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    payment = await session.scalar(statement)
    if payment is None or payment.payment_method not in CLICK_METHODS:
        raise errors.ClickError(errors.ORDER_NOT_FOUND, f"order {order_id} is not a Click order")
    return payment


def _assert_order_terms(payment: Payment) -> None:
    """The order must still price its tariff; otherwise no money may move for it.

    Checked before Prepare answers, so an order edited after it was minted is
    refused before Click debits the payer, not after.
    """
    try:
        assert_order_matches_tariff(amount=payment.amount, cashback_applied=payment.cashback_applied,
                                    tariff_months=payment.tariff_months,
                                    payment_method=payment.payment_method)
    except PaymentValidationError as exc:
        raise errors.ClickError(
            errors.INCORRECT_AMOUNT,
            f"order {payment.id}: {exc} (amount={payment.amount}, cashback={payment.cashback_applied},"
            f" tariff_months={payment.tariff_months})") from None


def _assert_payable(payment: Payment, amount_tiyin: int) -> None:
    if payment.status == "completed":
        raise errors.ClickError(errors.ALREADY_PAID, f"order {payment.id} is already paid")
    if payment.status != "pending":
        raise errors.ClickError(errors.TRANSACTION_CANCELLED, f"order {payment.id} is {payment.status}")
    if order_is_expired(payment.created_at):
        raise errors.ClickError(errors.TRANSACTION_CANCELLED, f"order {payment.id} expired")
    _assert_order_terms(payment)
    # Both sides in tiyin: Click quotes "500000.00", the order stores 500000 UZS.
    if amount_tiyin != sum_to_tiyin(payment.amount):
        raise errors.ClickError(errors.INCORRECT_AMOUNT, f"order {payment.id} costs {payment.amount} UZS")


async def _cancel_prepared(
    session: AsyncSession, transaction: ClickTransaction, reason: int | None
) -> None:
    """Cancel an unconfirmed transaction and close its order.

    The order is not returned to `pending`: the payer reopens the tariff, which
    mints a fresh order, so a stale checkout link can never be paid later.
    """
    transaction.state = STATE_CANCELLED
    transaction.cancel_reason = reason
    transaction.cancelled_at = _utcnow()
    payment = await _load_order(session, transaction.payment_id, lock=True)
    if payment.status == "pending":
        _, user, _ = await _lock_payment(session, payment.id)
        release_cashback(user, payment)
        payment.status = "failed"
    await session.commit()


async def prepare(session: AsyncSession, request: ClickRequest) -> int:
    """Reserve the order for this Click transaction and return its prepare id."""
    existing = await _lock_transaction(session, request.click_trans_id)
    if existing is not None:
        if existing.payment_id != request.order_id:
            raise errors.ClickError(errors.TRANSACTION_NOT_FOUND, "merchant_trans_id changed between retries")
        # Click retried; replay the answer it already received.
        if existing.state == STATE_PREPARED and not _is_expired(existing):
            if existing.amount != request.amount_tiyin:
                raise errors.ClickError(errors.INCORRECT_AMOUNT, "amount changed between retries")
            return existing.id
        if existing.state == STATE_CONFIRMED:
            raise errors.ClickError(errors.ALREADY_PAID, f"transaction {request.click_trans_id} is paid")
        if existing.state == STATE_PREPARED:
            await _cancel_prepared(session, existing, CANCEL_REASON_TIMEOUT)
        raise errors.ClickError(
            errors.TRANSACTION_CANCELLED, f"transaction {request.click_trans_id} is cancelled")

    _, user, _ = await _lock_payment(session, request.order_id)
    concurrent_order = await session.scalar(select(ClickTransaction.payment_id).where(
        ClickTransaction.click_trans_id == request.click_trans_id))
    if concurrent_order is not None:
        if concurrent_order != request.order_id:
            raise errors.ClickError(errors.TRANSACTION_NOT_FOUND, "merchant_trans_id changed between retries")
        return await prepare(session, request)
    payment = await _load_order(session, request.order_id)
    _assert_payable(payment, request.amount_tiyin)
    # Read the id now: a rollback expires the ORM object, and touching it
    # afterwards would attempt IO outside the async context.
    order_id = payment.id
    active = await session.scalar(
        select(ClickTransaction)
        .where(ClickTransaction.payment_id == order_id,
               ClickTransaction.state.in_((STATE_PREPARED, STATE_CONFIRMED)))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if active is not None:
        if active.state == STATE_CONFIRMED:
            raise errors.ClickError(errors.ALREADY_PAID, f"order {order_id} is already paid")
        if not _is_expired(active):
            raise errors.ClickError(errors.ALREADY_PAID, f"order {order_id} is already being paid")
        await _cancel_prepared(session, active, CANCEL_REASON_TIMEOUT)
        raise errors.ClickError(errors.TRANSACTION_CANCELLED, f"order {order_id} checkout timed out")

    try:
        reserve_cashback(user, payment)
    except PaymentValidationError as exc:
        raise errors.ClickError(errors.INCORRECT_AMOUNT, str(exc)) from None
    transaction = ClickTransaction(
        click_trans_id=request.click_trans_id, payment_id=order_id,
        amount=request.amount_tiyin, state=STATE_PREPARED,
        click_paydoc_id=request.click_paydoc_id, created_at=_utcnow(),
    )
    session.add(transaction)
    try:
        await session.commit()
    except IntegrityError:
        # The partial unique index rejected a second live transaction for this
        # order, or a concurrent request already created this click_trans_id.
        await session.rollback()
        existing = await _lock_transaction(session, request.click_trans_id)
        if (existing is not None and existing.payment_id == order_id
                and existing.amount == request.amount_tiyin and existing.state == STATE_PREPARED
                and not _is_expired(existing)):
            return existing.id
        raise errors.ClickError(errors.ALREADY_PAID, f"order {order_id} is already being paid") from None
    return transaction.id


async def complete(session: AsyncSession, request: ClickRequest, bot: Bot | None) -> int:
    """Commit the payment exactly once and return the merchant confirm id."""
    transaction = await _lock_transaction(session, request.click_trans_id)
    if transaction is None:
        raise errors.ClickError(errors.TRANSACTION_NOT_FOUND, f"no transaction {request.click_trans_id}")
    if request.merchant_prepare_id != transaction.id:
        raise errors.ClickError(errors.TRANSACTION_NOT_FOUND, "merchant_prepare_id does not match")
    if request.order_id != transaction.payment_id:
        raise errors.ClickError(errors.TRANSACTION_NOT_FOUND, "merchant_trans_id does not match")
    if request.amount_tiyin != transaction.amount:
        raise errors.ClickError(errors.INCORRECT_AMOUNT, "amount differs from the prepared transaction")

    if request.error < 0:
        # Click reports its own failure here; release the order instead of
        # leaving it reserved by a transaction that will never be confirmed.
        if transaction.state == STATE_PREPARED:
            await _cancel_prepared(session, transaction, request.error)
        raise errors.ClickError(errors.TRANSACTION_CANCELLED, f"click reported error {request.error}")
    if transaction.state == STATE_CONFIRMED:
        return transaction.id
    if transaction.state != STATE_PREPARED:
        raise errors.ClickError(errors.TRANSACTION_CANCELLED, f"transaction is in state {transaction.state}")
    if _is_expired(transaction):
        await _cancel_prepared(session, transaction, CANCEL_REASON_TIMEOUT)
        raise errors.ClickError(errors.TRANSACTION_CANCELLED, "prepared transaction timed out")
    if bot is None:
        raise errors.ClickError(errors.UPDATE_FAILED, "bot runtime is unavailable")

    # Re-check the terms Prepare accepted: the row may have been edited since.
    # A violation is permanent, so answer with a final code and release the
    # order instead of leaving it reserved for Click to retry against.
    payment = await _load_order(session, transaction.payment_id)
    try:
        _assert_order_terms(payment)
        if sum_to_tiyin(payment.amount) != transaction.amount:
            raise errors.ClickError(errors.INCORRECT_AMOUNT, "order amount changed after Prepare")
    except errors.ClickError as exc:
        await _cancel_prepared(session, transaction, CANCEL_REASON_REJECTED)
        raise exc

    transaction.state = STATE_CONFIRMED
    transaction.performed_at = _utcnow()
    try:
        committed = await process_successful_payment(transaction.payment_id, session, bot)
    except PaymentValidationError as exc:
        # process_successful_payment rolled the session back, which also
        # discarded the state change above; reload the row before cancelling.
        logger.exception("Click transaction %s rejected by payment policy", request.click_trans_id)
        rejected = await _lock_transaction(session, request.click_trans_id)
        if rejected is not None and rejected.state == STATE_PREPARED:
            await _cancel_prepared(session, rejected, CANCEL_REASON_REJECTED)
        raise errors.ClickError(errors.INCORRECT_AMOUNT, str(exc)) from None
    if committed:
        return transaction.id
    return await _finish_already_paid_order(session, request.click_trans_id)


async def _finish_already_paid_order(session: AsyncSession, click_trans_id: int) -> int:
    """Recover from a crash between committing the money and recording it here.

    `process_successful_payment` rolls back and returns False when the order is
    no longer pending. If the order is already completed, an earlier attempt
    paid it and only this row was left behind, so finish that write; anything
    else is an order that genuinely cannot be paid.
    """
    transaction = await _lock_transaction(session, click_trans_id)
    if transaction is None:
        raise errors.ClickError(errors.TRANSACTION_NOT_FOUND, f"no transaction {click_trans_id}")
    if transaction.state == STATE_CONFIRMED:
        await session.commit()
        return transaction.id
    payment = await _load_order(session, transaction.payment_id)
    if payment.status != "completed":
        # Describe the order before rolling back; the rollback expires it.
        detail = f"order {payment.id} is {payment.status}"
        await session.rollback()
        raise errors.ClickError(errors.UPDATE_FAILED, detail)
    transaction.state = STATE_CONFIRMED
    transaction.performed_at = _utcnow()
    await session.commit()
    logger.warning("Recovered Click transaction %s for already paid order %s", click_trans_id, payment.id)
    return transaction.id
