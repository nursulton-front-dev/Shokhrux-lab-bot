import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Subscription

async def get_active_subscription(session: AsyncSession, user_id: int) -> Subscription | None:
    """Return the latest paid entitlement; FAOL is the UI label for active."""
    now = datetime.datetime.now(datetime.timezone.utc)
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active",
        Subscription.expires_at > now,
    ).order_by(Subscription.expires_at.desc()).limit(1)
    return await session.scalar(stmt)


async def is_user_subscription_active(session: AsyncSession, user_id: int) -> bool:
    return await get_active_subscription(session, user_id) is not None
