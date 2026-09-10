"""Drop smoke-test Payme transactions and return the sandbox orders to pending."""
import asyncio

from sqlalchemy import delete, select

from bot.database.db import AsyncSessionLocal, engine
from bot.database.models import Payment, PaymeTransaction

SANDBOX_ORDER_IDS = (101, 102)


async def main() -> None:
    try:
        async with AsyncSessionLocal() as session, session.begin():
            removed = await session.execute(
                delete(PaymeTransaction).where(PaymeTransaction.payment_id.in_(SANDBOX_ORDER_IDS))
            )
            print(f"Removed {removed.rowcount} sandbox transaction(s)")
            for payment in (await session.scalars(
                select(Payment).where(Payment.id.in_(SANDBOX_ORDER_IDS)).with_for_update()
            )).all():
                payment.status = "pending"
                print(f"order_id={payment.id}: pending ({payment.amount} UZS)")
    finally:
        await engine.dispose()


asyncio.run(main())
