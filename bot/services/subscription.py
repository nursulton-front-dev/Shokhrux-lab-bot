import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Subscription

async def is_user_subscription_active(session: AsyncSession, user_id: int) -> bool:
    """
    Returns True if the user has an active subscription that has not expired.
    """
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    
    current_sub = await session.scalar(stmt)
    if not current_sub:
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    return current_sub.expires_at > now
