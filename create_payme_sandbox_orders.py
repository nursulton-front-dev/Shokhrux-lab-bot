"""Seed the two orders Payme's sandbox checklist expects. Idempotent.

The orders are deliberately not tied to a real tariff: `tariff_months = 0`
matches no entry in TARIFF_PRICES, so if one ever reached the production
payment path it would be rejected instead of granting a free subscription.
"""
import asyncio
import datetime

from sqlalchemy import select, text

from bot.database.db import AsyncSessionLocal, engine, init_db
from bot.database.models import Payment, User
from bot.services.payme.protocol import METHOD_PAYME_SANDBOX, to_tiyin

# A synthetic owner: a negative id can never collide with a real Telegram user,
# and no delivery job is ever queued for a sandbox order.
SANDBOX_USER_ID = -1
SANDBOX_ORDERS = ((101, 150_000), (102, 300_000))


async def _ensure_sandbox_user(session) -> None:
    user = await session.get(User, SANDBOX_USER_ID)
    if user is None:
        session.add(User(
            telegram_id=SANDBOX_USER_ID, username="payme_sandbox",
            full_name="Payme sandbox", language="ru",
        ))
        await session.flush()


async def _ensure_order(session, order_id: int, amount: int) -> str:
    payment = await session.get(Payment, order_id)
    if payment is not None:
        if payment.payment_method != METHOD_PAYME_SANDBOX:
            raise SystemExit(f"Order {order_id} already exists and is not a sandbox order")
        if payment.status != "pending":
            payment.status = "pending"
            return f"reset to pending ({payment.amount} UZS)"
        return f"already pending ({payment.amount} UZS)"
    session.add(Payment(
        id=order_id, user_id=SANDBOX_USER_ID, amount=amount, tariff_months=0,
        status="pending", payment_method=METHOD_PAYME_SANDBOX,
        request_key=f"payme-sandbox-{order_id}",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    ))
    return f"created ({amount} UZS = {to_tiyin(amount)} tiyin)"


async def main() -> None:
    try:
        await init_db()
        async with AsyncSessionLocal() as session, session.begin():
            await _ensure_sandbox_user(session)
            for order_id, amount in SANDBOX_ORDERS:
                print(f"order_id={order_id}: {await _ensure_order(session, order_id, amount)}")
            # Keep the sequence ahead of the seeded ids so a real payment
            # can never be issued order_id 101 or 102 a second time.
            highest = await session.scalar(select(text("max(id)")).select_from(Payment)) or 0
            await session.execute(text("SELECT setval('payments_id_seq', :value, true)"),
                                  {"value": max(highest, SANDBOX_ORDERS[-1][0])})
        print("Sandbox orders ready.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
