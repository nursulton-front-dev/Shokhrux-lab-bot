"""Order-owned cashback holds. Callers lock User, then Payment before mutations."""
from bot.database.models import Payment, User
from bot.services.payment_policy import PaymentValidationError


def available_cashback(user: User) -> int:
    return max(0, (user.balance or 0) - (user.reserved_cashback or 0))


def reserve_cashback(user: User, payment: Payment) -> None:
    required = payment.cashback_applied or 0
    held = payment.cashback_reserved or 0
    if held == required:
        return
    if held or available_cashback(user) < required:
        raise PaymentValidationError('Insufficient available cashback for this order')
    user.reserved_cashback = (user.reserved_cashback or 0) + required
    payment.cashback_reserved = required


def release_cashback(user: User, payment: Payment) -> None:
    held = payment.cashback_reserved or 0
    if held > (user.reserved_cashback or 0):
        raise PaymentValidationError('Cashback reservation invariant violated')
    user.reserved_cashback = (user.reserved_cashback or 0) - held
    payment.cashback_reserved = 0


def consume_cashback(user: User, payment: Payment) -> None:
    # Legacy orders must acquire a hold too; they cannot spend another order's hold.
    reserve_cashback(user, payment)
    amount = payment.cashback_reserved or 0
    if (user.balance or 0) < amount:
        raise PaymentValidationError('Cashback reservation exceeds balance')
    release_cashback(user, payment)
    user.balance = (user.balance or 0) - amount
