"""Retryable Telegram effects for committed payments.

Delivery is at least once: Telegram offers no idempotency key for sendMessage.
Financial state is never modified here. Untracked join-request links cannot admit
anyone because the join handler checks the persisted URL and its owner.
"""
import asyncio
import datetime
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select

from bot.config import config
from bot.database.db import AsyncSessionLocal
from bot.database.models import Payment, PaymentDelivery, Subscription, User

logger = logging.getLogger(__name__)


async def deliver_payment(payment_id: int, bot: Bot) -> None:
    async with AsyncSessionLocal() as session:
        try:
            async with asyncio.timeout(45):
                async with session.begin():
                    user_id = await session.scalar(select(Payment.user_id).where(Payment.id == payment_id))
                    if user_id is None:
                        return
                    user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
                    job = await session.scalar(select(PaymentDelivery).where(PaymentDelivery.payment_id == payment_id)
                                               .with_for_update(skip_locked=True).execution_options(populate_existing=True))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    if job is None or job.completed_at is not None or job.next_attempt_at > now:
                        return
                    sub = await session.get(Subscription, job.subscription_id)
                    if user is None or sub is None or sub.status != "active" or sub.expires_at <= now:
                        job.completed_at = now
                        return
                    if not config.channel_id:
                        raise RuntimeError("CHANNEL_ID is not configured")
                    if not sub.invite_link:
                        link = await bot.create_chat_invite_link(
                            chat_id=config.channel_id, creates_join_request=True,
                            expire_date=sub.expires_at, name=f"Payment {payment_id}", request_timeout=10)
                        sub.invite_link = link.invite_link
                    if sub.tariff_months == 6:
                        if not config.vip_chat_id:
                            raise RuntimeError("VIP_CHAT_ID is not configured")
                        if not sub.vip_invite_link:
                            link = await bot.create_chat_invite_link(
                                chat_id=config.vip_chat_id, creates_join_request=True,
                                expire_date=sub.expires_at, name=f"VIP payment {payment_id}", request_timeout=10)
                            sub.vip_invite_link = link.invite_link
                    # Persist links before exposing them: incoming join requests
                    # must find them even if sendMessage returns an ambiguous timeout.
                async with session.begin():
                    await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
                    job = await session.scalar(select(PaymentDelivery).where(PaymentDelivery.payment_id == payment_id)
                                               .with_for_update(skip_locked=True).execution_options(populate_existing=True))
                    if job is None or job.completed_at is not None:
                        return
                    sub = await session.get(Subscription, job.subscription_id, populate_existing=True)
                    if sub is None or sub.status != "active" or sub.expires_at <= datetime.datetime.now(datetime.timezone.utc):
                        job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                        return
                    from bot import texts
                    from bot.handlers.user import get_main_menu_keyboard
                    lang = user.language if user.language in {"uz", "ru"} else "uz"
                    template = texts.PAYMENT_SUCCESS_VIP[lang] if sub.vip_invite_link else texts.PAYMENT_SUCCESS[lang]
                    message = template.format(invite_link=sub.invite_link, vip_link=sub.vip_invite_link,
                                              expires_at=sub.expires_at.strftime("%Y-%m-%d %H:%M UTC"))
                    keyboard = await get_main_menu_keyboard(session, user_id, lang)
                    await bot.send_message(user_id, message, reply_markup=keyboard, request_timeout=10)
                    job.completed_at = datetime.datetime.now(datetime.timezone.utc)
            # Referral notification failure must not replay payment delivery.
            await _notify_referral(payment_id, bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment delivery failed; queued for retry: payment_id=%s", payment_id)
            await session.rollback()
            async with session.begin():
                job = await session.scalar(select(PaymentDelivery).where(PaymentDelivery.payment_id == payment_id)
                                           .with_for_update())
                if job is not None:
                    job.attempts += 1
                    job.next_attempt_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                        seconds=min(3600, 30 * 2 ** min(job.attempts, 7)))


async def _notify_referral(payment_id: int, bot: Bot) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            job = await session.scalar(select(PaymentDelivery).where(PaymentDelivery.payment_id == payment_id)
                                       .with_for_update(skip_locked=True).execution_options(populate_existing=True))
            if job is None or job.referral_notified:
                return
            if job.referrer_id is not None:
                referrer = await session.get(User, job.referrer_id)
                if referrer is not None:
                    from bot import texts
                    lang = referrer.language if referrer.language in {"uz", "ru"} else "uz"
                    try:
                        await bot.send_message(referrer.telegram_id, texts.CASHBACK_NOTIFY_REFERRER[lang], request_timeout=10)
                    except TelegramForbiddenError:
                        logger.info("Referrer %s cannot receive notifications", referrer.telegram_id)
            job.referral_notified = True


async def deliver_pending_payments(bot: Bot) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    async with AsyncSessionLocal() as session:
        ids = list((await session.scalars(select(PaymentDelivery.payment_id).where(
            PaymentDelivery.completed_at.is_(None), PaymentDelivery.next_attempt_at <= now
        ).order_by(PaymentDelivery.next_attempt_at, PaymentDelivery.payment_id).limit(50))).all())
        referral_ids = list((await session.scalars(select(PaymentDelivery.payment_id).where(
            PaymentDelivery.completed_at.is_not(None), PaymentDelivery.referral_notified.is_(False),
            PaymentDelivery.next_attempt_at <= now,
        ).order_by(PaymentDelivery.next_attempt_at, PaymentDelivery.payment_id).limit(50))).all())
    for payment_id in ids:
        try:
            await deliver_payment(payment_id, bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Delivery worker failure: payment_id=%s", payment_id)
    for payment_id in referral_ids:
        try:
            async with asyncio.timeout(20):
                await _notify_referral(payment_id, bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Referral notification failed: payment_id=%s", payment_id)
            async with AsyncSessionLocal() as session, session.begin():
                job = await session.get(PaymentDelivery, payment_id, with_for_update=True)
                if job is not None:
                    job.attempts += 1
                    job.next_attempt_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                        seconds=min(3600, 30 * 2 ** min(job.attempts, 7)))
