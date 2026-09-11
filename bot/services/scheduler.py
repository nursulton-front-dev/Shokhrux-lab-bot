import asyncio
import datetime
import logging
from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, or_, select, update
from sqlalchemy.sql.elements import ColumnElement

from bot import texts
from bot.config import config
from bot.database.db import AsyncSessionLocal
from bot.database.models import Payment, Subscription, User
from bot.services.payment_menu import gateway_buttons
from bot.services.telegram_rate_limit import kick_member, revoke_invite

logger = logging.getLogger(__name__)
UTC = datetime.timezone.utc
LOCAL_TIMEZONE = ZoneInfo("Asia/Tashkent")
PAGE_SIZE = 100


async def _subscription_ids(*conditions: ColumnElement[bool]) -> AsyncIterator[int]:
    """Keyset pagination closes each read transaction before external I/O."""
    last_id = 0
    while True:
        async with AsyncSessionLocal() as session:
            ids = list((await session.scalars(
                select(Subscription.id)
                .where(Subscription.id > last_id, *conditions)
                .order_by(Subscription.id).limit(PAGE_SIZE)
            )).all())
        if not ids:
            return
        for subscription_id in ids:
            yield subscription_id
        last_id = ids[-1]


async def _expire_subscription(bot: Bot, subscription_id: int) -> None:
    notify: tuple[int, str, bool] | None = None
    # Serialize this user's entitlement check and removal with payment renewal.
    # A bounded per-user transaction prevents a stalled Telegram API from holding
    # the entire scheduler batch or a DB connection indefinitely.
    async with asyncio.timeout(60):
        async with AsyncSessionLocal() as session, session.begin():
            user_id = await session.scalar(
                select(Subscription.user_id).where(Subscription.id == subscription_id)
            )
            if user_id is None:
                return
            user = await session.scalar(
                select(User).where(User.telegram_id == user_id).with_for_update()
            )
            if user is None:
                return
            sub = await session.get(Subscription, subscription_id, populate_existing=True)
            now = datetime.datetime.now(UTC)
            if sub is None or not (
                sub.status == "revocation_pending"
                or (sub.status == "active" and sub.expires_at <= now)
            ):
                return
            entitled = list((await session.scalars(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.status == "active", Subscription.expires_at > now,
                )
            )).all())
            main_entitled = bool(entitled)
            vip_entitled = any(item.tariff_months == 6 for item in entitled)
            if config.channel_id:
                await revoke_invite(bot, config.channel_id, sub.invite_link)
                if not main_entitled:
                    await kick_member(bot, config.channel_id, user_id)
            if config.vip_chat_id and (sub.tariff_months == 6 or sub.vip_invite_link):
                await revoke_invite(bot, config.vip_chat_id, sub.vip_invite_link)
                if not vip_entitled:
                    await kick_member(bot, config.vip_chat_id, user_id)
            sub.invite_link = None
            sub.vip_invite_link = None
            sub.status = "expired"
            if not main_entitled:
                language = user.language if user.language in ("ru", "uz") else "uz"
                notify = user_id, language, sub.tariff_months == 6
    # Notifications cannot roll back successful access removal.
    if notify is not None:
        user_id, language, is_vip = notify
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=texts.SUB_PROLONG[language], callback_data="start_sub")
            ]]) if is_vip else None
            async with asyncio.timeout(30):
                await bot.send_message(
                    chat_id=user_id,
                    text=(texts.VIP_EXPIRED if is_vip else texts.EXPIRED)[language],
                    reply_markup=keyboard, request_timeout=15,
                )
        except Exception:
            logger.exception("Failed to notify user %s about expiration", user_id)


def _renewal_keyboard(months: int, language: str, cashback_balance: int) -> InlineKeyboardMarkup:
    """Renew the same tariff in one tap, with the tariff menu as the fallback.

    The buttons carry callbacks rather than ready-made checkout URLs: an order is
    minted when the payer taps, so a reminder that is never acted on leaves no
    pending payment behind.
    """
    rows = []
    quick = gateway_buttons(months, use_cashback=cashback_balance > 0, lang=language)
    if quick:
        rows.append(quick)
    rows.append([InlineKeyboardButton(text=texts.SUB_PROLONG[language], callback_data="start_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _remind_subscription(bot: Bot, subscription_id: int, days: int) -> None:
    async with asyncio.timeout(30):
        async with AsyncSessionLocal() as session, session.begin():
            user_id = await session.scalar(
                select(Subscription.user_id).where(Subscription.id == subscription_id)
            )
            if user_id is None:
                return
            user = await session.scalar(
                select(User).where(User.telegram_id == user_id).with_for_update()
            )
            sub = await session.get(Subscription, subscription_id, populate_existing=True)
            now = datetime.datetime.now(UTC)
            if user is None or sub is None or sub.status != "active" or sub.expires_at <= now:
                return
            if days == 1:
                if sub.notified_1d or sub.expires_at > now + datetime.timedelta(days=1):
                    return
            elif sub.notified_3d or not (
                now + datetime.timedelta(days=1) < sub.expires_at <= now + datetime.timedelta(days=3)
            ):
                return
            language = user.language if user.language in ("ru", "uz") else "uz"
            message = (texts.REMIND_1D if days == 1 else texts.REMIND_3D)[language].format(
                expiry=sub.expires_at.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M")
            )
            keyboard = _renewal_keyboard(sub.tariff_months, language, user.balance or 0)
            try:
                await bot.send_message(chat_id=user_id, text=message,
                                       reply_markup=keyboard, request_timeout=15)
            except TelegramForbiddenError:
                # A blocked bot cannot deliver this reminder; continue other users.
                logger.info("Skipping reminder for unavailable user %s", user_id)
            sub.notified_3d = True
            if days == 1:
                sub.notified_1d = True


async def _fail_stale_payments(now: datetime.datetime) -> None:
    # Pending payments never grant access. An abandoned renewal must not remove
    # an independently paid subscription. CAS also preserves concurrent approval.
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            update(Payment).where(
                Payment.status == "pending",
                Payment.created_at <= now - datetime.timedelta(hours=24),
            ).values(status="failed")
        )


async def run_cron_jobs(bot: Bot) -> None:
    now = datetime.datetime.now(UTC)
    try:
        await _fail_stale_payments(now)
    except Exception:
        logger.exception("Failed to expire stale pending payments")

    jobs = (
        (0, or_(Subscription.status == "revocation_pending", and_(
            Subscription.status == "active", Subscription.expires_at <= now,
        ))),
        (3, and_(
            Subscription.status == "active", Subscription.notified_3d.is_(False),
            Subscription.expires_at <= now + datetime.timedelta(days=3),
            Subscription.expires_at > now + datetime.timedelta(days=1),
        )),
        (1, and_(
            Subscription.status == "active", Subscription.notified_1d.is_(False),
            Subscription.expires_at <= now + datetime.timedelta(days=1),
            Subscription.expires_at > now,
        )),
    )
    for days, condition in jobs:
        try:
            async for subscription_id in _subscription_ids(condition):
                try:
                    if days:
                        await _remind_subscription(bot, subscription_id, days)
                    else:
                        await _expire_subscription(bot, subscription_id)
                except Exception:
                    # The per-user transaction rolls back, retaining retry state.
                    logger.exception("Scheduler item failed: subscription=%s, reminder=%s",
                                     subscription_id, days)
        except Exception:
            logger.exception("Failed to load scheduler work: reminder=%s", days)


async def start_scheduler(bot: Bot, interval_seconds: int = 60) -> None:
    logger.info("Starting background scheduler")
    while True:
        await run_cron_jobs(bot)
        await asyncio.sleep(interval_seconds)


async def start_payment_delivery(bot: Bot, interval_seconds: int = 60) -> None:
    from bot.services.payment_delivery import deliver_pending_payments

    while True:
        try:
            await deliver_pending_payments(bot)
        except Exception:
            logger.exception("Payment delivery pass failed; retrying next pass")
        await asyncio.sleep(interval_seconds)
