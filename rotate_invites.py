"""Deployment utility to revoke legacy transferable invites and issue owner-checked ones.

Run after run_migration.py, with the old bot stopped. This script contacts Telegram
and sends replacement URLs to active subscribers. It never modifies payments.
An unsuccessful pass exits nonzero and can be retried.
"""
import asyncio
import datetime as dt
import logging

from aiogram import Bot
from sqlalchemy import or_, select

from bot.config import config
from bot.database.db import AsyncSessionLocal, engine
from bot.database.models import Subscription, User
from bot.services.telegram_rate_limit import TelegramRateLimitMiddleware, revoke_invite

logger = logging.getLogger(__name__)


async def rotate_one(subscription_id: int, bot: Bot) -> None:
    message: tuple[int, str] | None = None
    async with asyncio.timeout(60):
        async with AsyncSessionLocal() as session, session.begin():
            user_id = await session.scalar(select(Subscription.user_id).where(Subscription.id == subscription_id))
            if user_id is None:
                return
            user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
            sub = await session.get(Subscription, subscription_id)
            if sub is None or user is None:
                return
            active = sub.status == "active" and sub.expires_at > dt.datetime.now(dt.timezone.utc)
            for column, chat_id, eligible in (
                ("invite_link", config.channel_id, active),
                ("vip_invite_link", config.vip_chat_id, active and sub.tariff_months == 6),
            ):
                old = getattr(sub, column)
                if not old:
                    continue
                if not chat_id:
                    raise RuntimeError(f"Cannot revoke {column}: chat is not configured")
                await revoke_invite(bot, chat_id, old)
                setattr(sub, column, None)
                if eligible:
                    link = await bot.create_chat_invite_link(
                        chat_id=chat_id, creates_join_request=True, expire_date=sub.expires_at,
                        name=f"Rotate sub {sub.id}", request_timeout=15)
                    setattr(sub, column, link.invite_link)
            links = [url for url in (sub.invite_link, sub.vip_invite_link) if url]
            if active and links:
                title = "Обновлены ваши персональные ссылки:" if user.language == "ru" else "Shaxsiy havolalaringiz yangilandi:"
                message = user_id, title + "\n" + "\n".join(links)
        if message:
            await bot.send_message(*message, request_timeout=15)


async def main() -> None:
    bot = Bot(config.bot_token)
    bot.session.middleware(TelegramRateLimitMiddleware())
    failed = 0
    last_id = 0
    try:
        while True:
            async with AsyncSessionLocal() as session:
                ids = list((await session.scalars(select(Subscription.id).where(
                    Subscription.id > last_id,
                    or_(Subscription.invite_link.is_not(None), Subscription.vip_invite_link.is_not(None)),
                ).order_by(Subscription.id).limit(100))).all())
            if not ids:
                break
            for subscription_id in ids:
                try:
                    await rotate_one(subscription_id, bot)
                except Exception:
                    failed += 1
                    logger.exception("Invite rotation failed: subscription_id=%s", subscription_id)
            last_id = ids[-1]
        if failed:
            raise RuntimeError(f"Invite rotation incomplete: {failed} subscriptions; inspect logs and retry")
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
