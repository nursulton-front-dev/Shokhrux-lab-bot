import datetime
import os
from sqlalchemy import select
from aiogram import Bot

from bot.database.models import Subscription
from bot.database.db import AsyncSessionLocal

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))

async def run_cron_jobs(bot: Bot):
    """
    Checks for expired subscriptions, kicks members, and sends 3-day reminders.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    target_3d = now + datetime.timedelta(days=3)
    
    async with AsyncSessionLocal() as session:
        # 1. Handle expired subscriptions
        expired_stmt = select(Subscription).where(
            Subscription.status == "active",
            Subscription.expires_at <= now
        )
        expired_result = await session.execute(expired_stmt)
        expired_subs = expired_result.scalars().all()
        
        for sub in expired_subs:
            try:
                # Ban and unban immediately to kick the user from the channel
                await bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=sub.user_id)
                await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=sub.user_id)
            except Exception as e:
                print(f"Failed to kick user {sub.user_id}: {e}")
            
            sub.status = "expired"
            
            try:
                await bot.send_message(
                    chat_id=sub.user_id,
                    text="К сожалению, ваша подписка истекла, и вы были исключены из канала. Вы можете продлить подписку в любой момент!"
                )
            except Exception as e:
                print(f"Failed to notify user {sub.user_id} about expiration: {e}")
        
        # 2. Handle 3-day reminders
        reminder_stmt = select(Subscription).where(
            Subscription.status == "active",
            Subscription.notified_3d == False,
            Subscription.expires_at <= target_3d,
            Subscription.expires_at > now
        )
        reminder_result = await session.execute(reminder_stmt)
        reminder_subs = reminder_result.scalars().all()
        
        for sub in reminder_subs:
            try:
                await bot.send_message(
                    chat_id=sub.user_id,
                    text="Внимание! Ваша подписка на канал истекает через 3 дня. Не забудьте продлить её, чтобы не потерять доступ."
                )
                sub.notified_3d = True
            except Exception as e:
                print(f"Failed to remind user {sub.user_id} (3d): {e}")
                
        await session.commit()
