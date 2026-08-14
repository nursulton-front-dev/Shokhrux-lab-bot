import asyncio
import datetime
import logging
from sqlalchemy import select
from aiogram import Bot

from bot.database.models import Subscription, Payment, User
from bot.database.db import AsyncSessionLocal, init_db
from bot.config import config

logger = logging.getLogger(__name__)

async def run_cron_jobs(bot: Bot):
    """
    Checks for expired subscriptions, kicks members, sends reminders, and kicks unconfirmed payments.
    """
    try:
        await init_db()
        now = datetime.datetime.now(datetime.timezone.utc)
        target_3d = now + datetime.timedelta(days=3)
        target_1d = now + datetime.timedelta(days=1)
        unconfirmed_limit = now - datetime.timedelta(hours=24)
        
        channel_id = config.channel_id
        
        async with AsyncSessionLocal() as session:
            # 1. Handle expired subscriptions
            expired_stmt = select(Subscription, User).join(User).where(
                Subscription.status == "active",
                Subscription.expires_at <= now
            )
            expired_result = await session.execute(expired_stmt)
            expired_subs = expired_result.all()
            
            for sub, user in expired_subs:
                lang = user.language if user.language else "uz"
                if channel_id:
                    try:
                        await bot.ban_chat_member(chat_id=channel_id, user_id=sub.user_id)
                        await bot.unban_chat_member(chat_id=channel_id, user_id=sub.user_id)
                    except Exception as e:
                        logger.error(f"Failed to kick user {sub.user_id}: {e}")
                
                sub.status = "expired"
                
                try:
                    from bot import texts
                    await bot.send_message(chat_id=sub.user_id, text=texts.EXPIRED[lang])
                except Exception as e:
                    logger.error(f"Failed to notify user {sub.user_id} about expiration: {e}")
            
            # 2. Handle 3-day reminders
            reminder_3d_stmt = select(Subscription, User).join(User).where(
                Subscription.status == "active",
                Subscription.notified_3d == False,
                Subscription.expires_at <= target_3d,
                Subscription.expires_at > target_1d
            )
            reminder_3d_result = await session.execute(reminder_3d_stmt)
            for sub, user in reminder_3d_result.all():
                lang = user.language if user.language else "uz"
                try:
                    expiry_date_str = sub.expires_at.strftime("%Y-%m-%d %H:%M")
                    from bot import texts
                    await bot.send_message(
                        chat_id=sub.user_id,
                        text=texts.REMIND_3D[lang].format(expiry=expiry_date_str)
                    )
                    sub.notified_3d = True
                except Exception as e:
                    logger.error(f"Failed to remind user {sub.user_id} (3d): {e}")

            # 3. Handle 24-hour reminders
            reminder_1d_stmt = select(Subscription, User).join(User).where(
                Subscription.status == "active",
                Subscription.notified_1d == False,
                Subscription.expires_at <= target_1d,
                Subscription.expires_at > now
            )
            reminder_1d_result = await session.execute(reminder_1d_stmt)
            for sub, user in reminder_1d_result.all():
                lang = user.language if user.language else "uz"
                try:
                    expiry_date_str = sub.expires_at.strftime("%Y-%m-%d %H:%M")
                    from bot import texts
                    await bot.send_message(
                        chat_id=sub.user_id,
                        text=texts.REMIND_1D[lang].format(expiry=expiry_date_str)
                    )
                    sub.notified_1d = True
                    sub.notified_3d = True
                except Exception as e:
                    logger.error(f"Failed to remind user {sub.user_id} (1d): {e}")

            # 4. Handle unconfirmed payments (kick after 24 hours)
            unconfirmed_stmt = select(Payment, User).join(User).where(
                Payment.status == "pending",
                Payment.created_at <= unconfirmed_limit
            )
            unconfirmed_result = await session.execute(unconfirmed_stmt)
            for payment, user in unconfirmed_result.all():
                lang = user.language if user.language else "uz"
                payment.status = "failed"
                if channel_id:
                    try:
                        await bot.ban_chat_member(chat_id=channel_id, user_id=payment.user_id)
                        await bot.unban_chat_member(chat_id=channel_id, user_id=payment.user_id)
                        from bot import texts
                        await bot.send_message(
                            chat_id=payment.user_id,
                            text=texts.PAYMENT_FAILED[lang]
                        )
                    except Exception as e:
                        logger.error(f"Failed to auto-kick unconfirmed user {payment.user_id}: {e}")
                    
                sub_stmt = select(Subscription).where(
                    Subscription.user_id == payment.user_id,
                    Subscription.status == "active"
                ).order_by(Subscription.expires_at.desc()).limit(1)
                sub_res = await session.execute(sub_stmt)
                sub = sub_res.scalar_one_or_none()
                if sub:
                    sub.status = "expired"
                    
            await session.commit()
    except Exception as e:
        logger.error(f"Error running background scheduler jobs: {e}")

async def start_scheduler(bot: Bot, interval_seconds: int = 3600):
    """
    Runs scheduler tasks periodically in the background.
    """
    logger.info("Starting background scheduler...")
    while True:
        await run_cron_jobs(bot)
        await asyncio.sleep(interval_seconds)
