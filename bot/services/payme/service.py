"""Payme Merchant API state machine.

Payme retries every method until it gets a final answer, so each handler is
idempotent and keyed on the Payme transaction id. Money state lives in
`payments`; this module only drives the protocol and delegates the financial
commit to `bot.services.rahmat.process_successful_payment`.
"""
import datetime
import logging
from typing import Any

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import config
from bot.database.models import Payment, PaymeTransaction
from bot.services.payme import errors
from bot.services.payme.protocol import (
    CANCEL_REASON_TIMEOUT,
    METHOD_PAYME_SANDBOX,
    PAYME_METHODS,
    STATE_CANCELLED,
    STATE_CANCELLED_AFTER_PERFORM,
    STATE_CREATED,
    STATE_PERFORMED,
    TRANSACTION_TIMEOUT_MS,
    now_ms,
    to_ms,
    to_tiyin,
)
from bot.services.payment_policy import PaymentValidationError, assert_order_matches_tariff, order_is_expired
from bot.services.rahmat import process_successful_payment, _lock_payment
from bot.services.cashback import release_cashback, reserve_cashback

logger = logging.getLogger(__name__)

MAX_STATEMENT_ROWS = 5000


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _require_transaction_id(params: dict[str, Any]) -> str:
    payme_id = params.get("id")
    if not isinstance(payme_id, str) or not 0 < len(payme_id) <= 64:
        raise errors.invalid_params("id")
    return payme_id


def _require_amount(params: dict[str, Any]) -> int:
    amount = params.get("amount")
    # bool is an int subclass; Payme never sends a boolean amount.
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise errors.invalid_params("amount")
    return amount


def _require_order_id(params: dict[str, Any]) -> int:
    """An unusable account object is an order error, not a params error:
    Payme shows `data` as the offending field to the payer."""
    account = params.get("account")
    if not isinstance(account, dict):
        raise errors.order_not_found()
    raw = account.get(errors.ACCOUNT_FIELD)
    if isinstance(raw, bool):
        raise errors.order_not_found()
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    raise errors.order_not_found()


async def _load_order(session: AsyncSession, order_id: int, *, lock: bool = False) -> Payment:
    statement = select(Payment).where(Payment.id == order_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    payment = await session.scalar(statement)
    if payment is None or payment.payment_method not in PAYME_METHODS:
        raise errors.order_not_found()
    if payment.payment_method == METHOD_PAYME_SANDBOX and not config.payme_sandbox:
        # A sandbox order must never be payable with production credentials.
        raise errors.order_not_found()
    return payment


def _assert_payable(payment: Payment, amount_tiyin: int) -> None:
    if payment.status != "pending":
        raise errors.unable_to_perform(f"order {payment.id} is {payment.status}")
    if order_is_expired(payment.created_at):
        raise errors.unable_to_perform("Order expired")
    if payment.payment_method != METHOD_PAYME_SANDBOX:
        # Sandbox orders carry no tariff; real ones must still price theirs,
        # or PerformTransaction would fail after Payme has taken the money.
        try:
            assert_order_matches_tariff(
                amount=payment.amount, cashback_applied=payment.cashback_applied,
                tariff_months=payment.tariff_months, payment_method=payment.payment_method)
        except PaymentValidationError:
            raise errors.wrong_amount() from None
    if amount_tiyin != to_tiyin(payment.amount):
        raise errors.wrong_amount()


def _is_expired(transaction: PaymeTransaction) -> bool:
    return now_ms() - transaction.payme_time >= TRANSACTION_TIMEOUT_MS


async def _lock_transaction(session: AsyncSession, payme_id: str) -> PaymeTransaction | None:
    payment_id = await session.scalar(select(PaymeTransaction.payment_id).where(PaymeTransaction.payme_id == payme_id))
    if payment_id is None:
        return None
    await _lock_payment(session, payment_id)
    return await session.scalar(
        select(PaymeTransaction)
        .where(PaymeTransaction.payme_id == payme_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _created_result(transaction: PaymeTransaction) -> dict[str, Any]:
    return {
        "create_time": to_ms(transaction.created_at),
        "transaction": str(transaction.id),
        "state": transaction.state,
    }


def _performed_result(transaction: PaymeTransaction) -> dict[str, Any]:
    return {
        "transaction": str(transaction.id),
        "perform_time": to_ms(transaction.performed_at),
        "state": transaction.state,
    }


def _cancelled_result(transaction: PaymeTransaction) -> dict[str, Any]:
    return {
        "transaction": str(transaction.id),
        "cancel_time": to_ms(transaction.cancelled_at),
        "state": transaction.state,
    }


def _statement_row(transaction: PaymeTransaction) -> dict[str, Any]:
    return {
        "id": transaction.payme_id,
        "time": transaction.payme_time,
        "amount": transaction.amount,
        "account": {errors.ACCOUNT_FIELD: str(transaction.payment_id)},
        "create_time": to_ms(transaction.created_at),
        "perform_time": to_ms(transaction.performed_at),
        "cancel_time": to_ms(transaction.cancelled_at),
        "transaction": str(transaction.id),
        "state": transaction.state,
        "reason": transaction.reason,
        "receivers": None,
    }


async def check_perform_transaction(session: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    """Answer whether the order can be paid, without changing any state."""
    amount = _require_amount(params)
    order_id = _require_order_id(params)
    payment = await _load_order(session, order_id)
    _assert_payable(payment, amount)
    active = await session.scalar(
        select(PaymeTransaction.payme_id).where(
            PaymeTransaction.payment_id == payment.id,
            PaymeTransaction.state.in_((STATE_CREATED, STATE_PERFORMED)),
        )
    )
    if active is not None:
        raise errors.unable_to_perform(f"order {payment.id} already has transaction {active}")
    return {"allow": True}


async def create_transaction(session: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    """Register the transaction, or replay the answer Payme already received."""
    payme_id = _require_transaction_id(params)
    amount = _require_amount(params)
    order_id = _require_order_id(params)
    payme_time = params.get("time")
    if isinstance(payme_time, bool) or not isinstance(payme_time, int) or payme_time <= 0:
        raise errors.invalid_params("time")

    existing = await _lock_transaction(session, payme_id)
    if existing is not None:
        if existing.payment_id != order_id or existing.amount != amount:
            raise errors.unable_to_perform("Transaction terms changed")
        if existing.state != STATE_CREATED:
            raise errors.unable_to_perform(f"transaction {payme_id} is in state {existing.state}")
        if _is_expired(existing):
            await _cancel_created(session, existing, CANCEL_REASON_TIMEOUT)
            raise errors.unable_to_perform(f"transaction {payme_id} timed out")
        return _created_result(existing)

    _, user, _ = await _lock_payment(session, order_id)
    concurrent_order = await session.scalar(select(PaymeTransaction.payment_id).where(
        PaymeTransaction.payme_id == payme_id))
    if concurrent_order is not None:
        if concurrent_order != order_id:
            raise errors.unable_to_perform("Transaction belongs to another order")
        return await create_transaction(session, params)
    payment = await _load_order(session, order_id)
    _assert_payable(payment, amount)
    # Read the id now: a rollback expires the ORM object, and touching it
    # afterwards would attempt IO outside the async context.
    paid_order_id = payment.id
    try:
        reserve_cashback(user, payment)
    except PaymentValidationError:
        raise errors.unable_to_perform("Insufficient available cashback") from None
    transaction = PaymeTransaction(
        payme_id=payme_id, payment_id=paid_order_id, amount=amount,
        state=STATE_CREATED, payme_time=payme_time, created_at=_utcnow(),
    )
    session.add(transaction)
    try:
        await session.commit()
    except IntegrityError:
        # The partial unique index rejected a second live transaction for this
        # order, or a concurrent request already created this payme_id.
        await session.rollback()
        logger.info("Payme order %s is already being paid; refusing %s", paid_order_id, payme_id)
        raise errors.order_already_being_paid() from None
    return _created_result(transaction)


async def _cancel_created(
    session: AsyncSession, transaction: PaymeTransaction, reason: int | None
) -> None:
    """Cancel an unpaid transaction and release its order for a new attempt."""
    transaction.state = STATE_CANCELLED
    transaction.reason = reason
    transaction.cancelled_at = _utcnow()
    payment = await _load_order(session, transaction.payment_id, lock=True)
    if payment.status == "pending":
        _, user, _ = await _lock_payment(session, payment.id)
        release_cashback(user, payment)
        payment.status = "failed"
    await session.commit()


async def perform_transaction(
    session: AsyncSession, params: dict[str, Any], bot: Bot | None
) -> dict[str, Any]:
    """Commit the payment exactly once and report the confirmation time."""
    payme_id = _require_transaction_id(params)
    transaction = await _lock_transaction(session, payme_id)
    if transaction is None:
        raise errors.transaction_not_found()
    if transaction.state == STATE_PERFORMED:
        return _performed_result(transaction)
    if transaction.state != STATE_CREATED:
        raise errors.unable_to_perform(f"transaction {payme_id} is in state {transaction.state}")
    if _is_expired(transaction):
        await _cancel_created(session, transaction, CANCEL_REASON_TIMEOUT)
        raise errors.unable_to_perform(f"transaction {payme_id} timed out")

    payment = await _load_order(session, transaction.payment_id)
    transaction.state = STATE_PERFORMED
    transaction.performed_at = _utcnow()
    if payment.payment_method == METHOD_PAYME_SANDBOX:
        return await _perform_sandbox_order(session, transaction)
    if bot is None:
        raise errors.unable_to_perform("bot runtime is unavailable")
    try:
        committed = await process_successful_payment(transaction.payment_id, session, bot)
    except PaymentValidationError as exc:
        logger.exception("Payme transaction %s rejected by payment policy", payme_id)
        raise errors.unable_to_perform(str(exc)) from None
    if committed:
        return _performed_result(transaction)
    return await _finish_already_paid_order(session, payme_id)


async def _perform_sandbox_order(
    session: AsyncSession, transaction: PaymeTransaction
) -> dict[str, Any]:
    """Sandbox orders only exercise the protocol: no subscription is granted."""
    payment = await _load_order(session, transaction.payment_id, lock=True)
    payment.status = "completed"
    await session.commit()
    logger.info(
        "Payme sandbox order %s marked paid by transaction %s; no subscription granted",
        payment.id, transaction.payme_id,
    )
    return _performed_result(transaction)


async def _finish_already_paid_order(session: AsyncSession, payme_id: str) -> dict[str, Any]:
    """Recover from a crash between committing the money and recording it here.

    `process_successful_payment` rolls back and returns False when the order is
    no longer pending. If the order is already completed, an earlier attempt
    paid it and only this row was left behind, so finish that write; anything
    else is an order that genuinely cannot be paid.
    """
    transaction = await _lock_transaction(session, payme_id)
    if transaction is None:
        raise errors.transaction_not_found()
    if transaction.state == STATE_PERFORMED:
        await session.commit()
        return _performed_result(transaction)
    payment = await _load_order(session, transaction.payment_id)
    if payment.status != "completed":
        # Describe the order before rolling back; the rollback expires it.
        detail = f"order {payment.id} is {payment.status}"
        await session.rollback()
        raise errors.unable_to_perform(detail)
    transaction.state = STATE_PERFORMED
    transaction.performed_at = _utcnow()
    await session.commit()
    logger.warning("Recovered Payme transaction %s for already paid order %s", payme_id, payment.id)
    return _performed_result(transaction)


async def cancel_transaction(session: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    """Cancel an unpaid transaction; a delivered order is never auto-refunded."""
    payme_id = _require_transaction_id(params)
    reason = params.get("reason")
    if reason is not None and (isinstance(reason, bool) or not isinstance(reason, int)):
        raise errors.invalid_params("reason")

    transaction = await _lock_transaction(session, payme_id)
    if transaction is None:
        raise errors.transaction_not_found()
    if transaction.state < 0:
        return _cancelled_result(transaction)
    if transaction.state == STATE_CREATED:
        await _cancel_created(session, transaction, reason)
        return _cancelled_result(transaction)

    payment = await _load_order(session, transaction.payment_id, lock=True)
    if payment.payment_method != METHOD_PAYME_SANDBOX:
        # Channel and VIP access are granted the moment the payment commits.
        # Reversing that is a support decision, not an automatic protocol step.
        raise errors.cannot_cancel_performed()
    transaction.state = STATE_CANCELLED_AFTER_PERFORM
    transaction.reason = reason
    transaction.cancelled_at = _utcnow()
    payment.status = "failed"
    await session.commit()
    logger.info("Payme sandbox order %s reverted by transaction %s", payment.id, payme_id)
    return _cancelled_result(transaction)


async def check_transaction(session: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    payme_id = _require_transaction_id(params)
    transaction = await session.scalar(
        select(PaymeTransaction).where(PaymeTransaction.payme_id == payme_id)
    )
    if transaction is None:
        raise errors.transaction_not_found()
    return {
        "create_time": to_ms(transaction.created_at),
        "perform_time": to_ms(transaction.performed_at),
        "cancel_time": to_ms(transaction.cancelled_at),
        "transaction": str(transaction.id),
        "state": transaction.state,
        "reason": transaction.reason,
    }


async def get_statement(session: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    """Return every transaction Payme timestamped inside the window."""
    period = []
    for field in ("from", "to"):
        value = params.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise errors.invalid_params(field)
        period.append(value)
    start, end = period
    if start > end:
        raise errors.invalid_params("from")
    transactions = (await session.scalars(
        select(PaymeTransaction)
        .where(PaymeTransaction.payme_time >= start, PaymeTransaction.payme_time <= end)
        .order_by(PaymeTransaction.payme_time, PaymeTransaction.id)
        .limit(MAX_STATEMENT_ROWS)
    )).all()
    return {"transactions": [_statement_row(transaction) for transaction in transactions]}
