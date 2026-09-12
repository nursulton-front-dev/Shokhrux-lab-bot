"""Leased outbox delivery. No Telegram I/O holds a DB transaction or User lock.

At-least-once messages: Telegram has no sendMessage idempotency key. Every DB
write is fenced by a lease token so an expired worker cannot finish a new claim.
"""
import asyncio
import datetime
import logging
import uuid
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import or_, select

from bot.config import config
from bot.database.db import AsyncSessionLocal
from bot.database.models import PaymentDelivery, Subscription, User

logger = logging.getLogger(__name__)
UTC = datetime.timezone.utc
WORK_TIMEOUT = 45
LEASE_SECONDS = 90


def _now():
    return datetime.datetime.now(UTC)


@dataclass(frozen=True)
class Delivery:
    payment_id: int
    token: str
    subscription_id: int
    user_id: int
    lang: str
    expires_at: datetime.datetime
    months: int
    invite_link: str | None
    vip_invite_link: str | None
    completed: bool
    referrer_id: int | None
    referral_notified: bool


def _snapshot(job, sub, user):
    return Delivery(job.payment_id, job.lease_token, sub.id, sub.user_id,
                    user.language if user.language in ('uz', 'ru') else 'uz',
                    sub.expires_at, sub.tariff_months, sub.invite_link, sub.vip_invite_link,
                    job.completed_at is not None, job.referrer_id, job.referral_notified)


async def _claim(payment_id: int) -> Delivery | None:
    async with AsyncSessionLocal() as session, session.begin():
        now = _now()
        job = await session.scalar(select(PaymentDelivery).where(
            PaymentDelivery.payment_id == payment_id, PaymentDelivery.next_attempt_at <= now,
            or_(PaymentDelivery.completed_at.is_(None), PaymentDelivery.referral_notified.is_(False)),
            or_(PaymentDelivery.locked_until.is_(None), PaymentDelivery.locked_until <= now),
        ).with_for_update(skip_locked=True))
        if job is None:
            return None
        sub = await session.get(Subscription, job.subscription_id)
        user = await session.get(User, sub.user_id) if sub else None
        if sub is None or user is None:
            job.completed_at = now
            job.referral_notified = True
            return None
        if sub.status != 'active' or sub.expires_at <= now:
            job.completed_at = job.completed_at or now
        job.lease_token = uuid.uuid4().hex
        job.locked_until = now + datetime.timedelta(seconds=LEASE_SECONDS)
        return _snapshot(job, sub, user)


async def _owned_job(session, item: Delivery):
    return await session.scalar(select(PaymentDelivery).where(
        PaymentDelivery.payment_id == item.payment_id, PaymentDelivery.lease_token == item.token,
        PaymentDelivery.locked_until > _now(),
    ).with_for_update())


async def _save_link(item: Delivery, column: str, link: str) -> bool:
    async with AsyncSessionLocal() as session, session.begin():
        # Serialize the brief entitlement write with scheduler/admin revocation.
        await session.scalar(select(User).where(User.telegram_id == item.user_id).with_for_update())
        job = await _owned_job(session, item)
        sub = await session.get(Subscription, item.subscription_id, populate_existing=True)
        if job is None or sub is None or sub.status != 'active' or sub.expires_at <= _now():
            return False
        if getattr(sub, column) not in (None, link):
            return False
        setattr(sub, column, link)
        return True


async def _create_access_link(bot: Bot, **kwargs):
    try:
        return await bot.create_chat_invite_link(**kwargs)
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception('Invite creation failed for chat_id=%s; check administrator can_invite_users',
                         kwargs.get('chat_id'))
        raise


async def _ensure_links(item: Delivery, bot: Bot) -> None:
    targets = [(config.channel_id, 'invite_link', item.invite_link)]
    if item.months == 6:
        targets.append((config.vip_chat_id, 'vip_invite_link', item.vip_invite_link))
    for chat_id, column, existing in targets:
        if not chat_id:
            raise RuntimeError(f'Chat for {column} is not configured')
        if existing:
            continue
        link = await _create_access_link(bot, chat_id=chat_id, creates_join_request=True,
            expire_date=item.expires_at, name=f'Payment {item.payment_id}', request_timeout=10)
        if not await _save_link(item, column, link.invite_link):
            # A concurrently revoked subscription must never regain a stored link.
            # Even if revocation fails, an untracked URL fails the join-request guard.
            try:
                await bot.revoke_chat_invite_link(chat_id=chat_id, invite_link=link.invite_link, request_timeout=10)
            except Exception:
                logger.exception('Could not revoke unused delivery link for payment %s', item.payment_id)
            raise RuntimeError('Delivery lease or entitlement changed while creating an invite')


async def _message_snapshot(item: Delivery) -> Delivery | None:
    async with AsyncSessionLocal() as session, session.begin():
        job = await _owned_job(session, item)
        sub = await session.get(Subscription, item.subscription_id)
        user = await session.get(User, item.user_id)
        if job is None:
            return None
        if sub is None or user is None or sub.status != 'active' or sub.expires_at <= _now():
            job.completed_at = _now()
            return None
        if not sub.invite_link or (sub.tariff_months == 6 and not sub.vip_invite_link):
            raise RuntimeError('Delivery links are not ready')
        return _snapshot(job, sub, user)


async def _mark_sent(item: Delivery, *, referral: bool = False) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        job = await _owned_job(session, item)
        if job is not None:
            if referral:
                job.referral_notified = True
            else:
                job.completed_at = _now()


async def _notify_referral(item: Delivery, bot: Bot) -> None:
    if item.referral_notified:
        return
    async with AsyncSessionLocal() as session, session.begin():
        job = await _owned_job(session, item)
        if job is None or job.referral_notified:
            return
        referrer = await session.get(User, item.referrer_id) if item.referrer_id else None
        recipient = (referrer.telegram_id, referrer.language if referrer.language in ('uz', 'ru') else 'uz') if referrer else None
    if recipient:
        from bot import texts
        try:
            await bot.send_message(recipient[0], texts.CASHBACK_NOTIFY_REFERRER[recipient[1]], request_timeout=10)
        except TelegramForbiddenError:
            logger.info('Referrer %s cannot receive notifications', recipient[0])
    await _mark_sent(item, referral=True)


async def _release(item: Delivery, error: str | None = None) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        # Allow our own expired token to release, but never a replacement token.
        job = await session.scalar(select(PaymentDelivery).where(
            PaymentDelivery.payment_id == item.payment_id, PaymentDelivery.lease_token == item.token,
        ).with_for_update())
        if job is None:
            return
        job.lease_token = None
        job.locked_until = None
        job.last_error = error[:500] if error else None
        if error:
            job.attempts += 1
            job.next_attempt_at = _now() + datetime.timedelta(seconds=min(3600, 5 * 2**min(job.attempts-1, 10)))


async def deliver_payment(payment_id: int, bot: Bot) -> None:
    item = None
    try:
        async with asyncio.timeout(WORK_TIMEOUT):
            item = await _claim(payment_id)
            if item is None:
                return
            if not item.completed:
                await _ensure_links(item, bot)
                current = await _message_snapshot(item)
                if current is not None:
                    from bot import texts
                    from bot.handlers.user import main_menu_keyboard
                    template = texts.PAYMENT_SUCCESS_VIP if current.vip_invite_link else texts.PAYMENT_SUCCESS
                    message = template[current.lang].format(invite_link=current.invite_link,
                        vip_link=current.vip_invite_link, expires_at=current.expires_at.strftime('%Y-%m-%d %H:%M UTC'))
                    await bot.send_message(current.user_id, message,
                        reply_markup=main_menu_keyboard(current.lang, is_active=True, has_bought=True), request_timeout=10)
                    await _mark_sent(item)
            await _notify_referral(item, bot)
        await _release(item)
    except asyncio.CancelledError:
        # A killed process is recovered after the persisted lease expires.
        raise
    except Exception as exc:
        logger.exception('Payment delivery failed: payment_id=%s', payment_id)
        if item is not None:
            await _release(item, f'{type(exc).__name__}: {exc}')


async def deliver_pending_payments(bot: Bot) -> None:
    async with AsyncSessionLocal() as session:
        now = _now()
        ids = list((await session.scalars(select(PaymentDelivery.payment_id).where(
            or_(PaymentDelivery.completed_at.is_(None), PaymentDelivery.referral_notified.is_(False)),
            PaymentDelivery.next_attempt_at <= now,
            or_(PaymentDelivery.locked_until.is_(None), PaymentDelivery.locked_until <= now),
        ).order_by(PaymentDelivery.next_attempt_at, PaymentDelivery.payment_id)
          .limit(config.payment_delivery_batch_size))).all())
    semaphore = asyncio.Semaphore(config.payment_delivery_concurrency)

    async def send(payment_id):
        async with semaphore:
            try:
                await deliver_payment(payment_id, bot)
            except Exception:
                logger.exception('Delivery worker failure: payment_id=%s', payment_id)

    await asyncio.gather(*(send(payment_id) for payment_id in ids))
