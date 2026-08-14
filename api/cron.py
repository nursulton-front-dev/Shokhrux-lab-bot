import datetime
import os
from sqlalchemy import select
from aiogram import Bot

from bot.database.models import Subscription, Payment
from bot.database.db import AsyncSessionLocal

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))

async def run_cron_jobs(bot: Bot):
    """
    Checks for expired subscriptions, kicks members, sends reminders, and kicks unconfirmed.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    target_3d = now + datetime.timedelta(days=3)
    target_1d = now + datetime.timedelta(days=1)
    unconfirmed_limit = now - datetime.timedelta(hours=24)
    
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
        reminder_3d_stmt = select(Subscription).where(
            Subscription.status == "active",
            Subscription.notified_3d == False,
            Subscription.expires_at <= target_3d,
            Subscription.expires_at > target_1d
        )
        reminder_3d_result = await session.execute(reminder_3d_stmt)
        for sub in reminder_3d_result.scalars().all():
            try:
                await bot.send_message(
                    chat_id=sub.user_id,
                    text="Внимание! Ваша подписка на канал истекает через 3 дня. Не забудьте продлить её, чтобы не потерять доступ."
                )
                sub.notified_3d = True
            except Exception as e:
                print(f"Failed to remind user {sub.user_id} (3d): {e}")

        # 3. Handle 24-hour reminders
        reminder_1d_stmt = select(Subscription).where(
            Subscription.status == "active",
            Subscription.notified_1d == False,
            Subscription.expires_at <= target_1d,
            Subscription.expires_at > now
        )
        reminder_1d_result = await session.execute(reminder_1d_stmt)
        for sub in reminder_1d_result.scalars().all():
            try:
                await bot.send_message(
                    chat_id=sub.user_id,
                    text="⏳ Внимание! Ваша подписка на канал истекает через 24 часа. Продлите её прямо сейчас, чтобы не потерять доступ к эксклюзивному контенту."
                )
                sub.notified_1d = True
                sub.notified_3d = True  # In case it was missed
            except Exception as e:
                print(f"Failed to remind user {sub.user_id} (1d): {e}")

        # 4. Handle unconfirmed payments (kick after 24 hours)
        unconfirmed_stmt = select(Payment).where(
            Payment.status == "pending",
            Payment.created_at <= unconfirmed_limit
        )
        unconfirmed_result = await session.execute(unconfirmed_stmt)
        for payment in unconfirmed_result.scalars().all():
            payment.status = "failed"
            try:
                await bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=payment.user_id)
                await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=payment.user_id)
                await bot.send_message(
                    chat_id=payment.user_id,
                    text="❌ Ваша оплата не была подтверждена в течение 24 часов. Вы были исключены из канала."
                )
            except Exception as e:
                print(f"Failed to auto-kick unconfirmed user {payment.user_id}: {e}")
                
            # Update their active subscription if it exists
            sub_stmt = select(Subscription).where(
                Subscription.user_id == payment.user_id,
                Subscription.status == "active"
            ).order_by(Subscription.expires_at.desc()).limit(1)
            sub_res = await session.execute(sub_stmt)
            sub = sub_res.scalar_one_or_none()
            if sub:
                sub.status = "expired"
                
        await session.commit()
