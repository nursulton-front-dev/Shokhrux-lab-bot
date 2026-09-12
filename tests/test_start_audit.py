"""Resident entry and entitlement boundaries on an isolated PostgreSQL database."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.filters import CommandObject

from bot import texts
from bot.database.models import Subscription, User
from bot.handlers import user as handlers
from bot.services.subscription import get_active_subscription
from test_payments_audit import db, local_postgres

UTC = dt.timezone.utc


@pytest.mark.asyncio
@pytest.mark.parametrize('lang', ['uz', 'ru', None])
async def test_active_start_bypasses_onboarding_and_resets_state(db, monkeypatch, lang):
    now = dt.datetime.now(UTC)
    expiry = now + dt.timedelta(days=10)
    async with db() as session:
        session.add(User(telegram_id=501, language=lang, balance=0))
        await session.flush()
        session.add(Subscription(user_id=501, status='active', tariff_months=1,
                                 started_at=now, expires_at=expiry))
        await session.commit()
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=501)
    state = AsyncMock()
    tariffs = AsyncMock()
    monkeypatch.setattr(handlers, 'show_tariffs', tariffs)
    async with db() as session:
        await handlers.cmd_start(message, CommandObject(command='start'), session, state)
    state.clear.assert_awaited_once()
    state.set_state.assert_not_awaited()
    tariffs.assert_not_awaited()
    message.answer.assert_awaited_once()
    content = message.answer.await_args.args[0]
    effective = lang or 'uz'
    assert texts.STATUS_ACTIVE[effective] in content
    assert expiry.astimezone(dt.timezone(dt.timedelta(hours=5))).strftime('%d.%m.%Y %H:%M') in content
    buttons = {b.text for row in message.answer.await_args.kwargs['reply_markup'].keyboard for b in row}
    assert {texts.MENU_BUTTONS[key][effective] for key in ('profile', 'fitness_hub', 'training', 'referral', 'prolong')} <= buttons


@pytest.mark.asyncio
@pytest.mark.parametrize('status,delta', [('active', -1), ('expired', 10), ('revocation_pending', 10), (None, 0)])
async def test_non_resident_start_shows_tariffs(db, monkeypatch, status, delta):
    now = dt.datetime.now(UTC)
    async with db() as session:
        session.add(User(telegram_id=501, language='uz', full_name='Test', phone_number='+998901234567', balance=0))
        await session.flush()
        if status:
            session.add(Subscription(user_id=501, status=status, tariff_months=1,
                                     started_at=now-dt.timedelta(days=30), expires_at=now+dt.timedelta(days=delta)))
        await session.commit()
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=501)
    tariffs = AsyncMock()
    monkeypatch.setattr(handlers, 'show_tariffs', tariffs)
    async with db() as session:
        assert await get_active_subscription(session, 501) is None
        await handlers.cmd_start(message, CommandObject(command='start'), session, AsyncMock())
    assert message.answer.await_args.args[0] == texts.WELCOME_TEXT['uz']
    tariffs.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_has_priority_over_ai_state_handler(db, monkeypatch):
    from aiogram import Bot, Dispatcher, F, Router
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Message, Update
    dp = Dispatcher(storage=MemoryStorage())
    # Copy the registration into a fresh router to avoid attaching the app router twice.
    first, ai = Router(), Router()
    first.message.register(handlers.cmd_start, handlers.CommandStart())
    catchall = AsyncMock()
    async def consume(message):
        await catchall(message)
    ai.message.register(consume, F.text)
    dp.include_routers(first, ai)
    bot = Bot('123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
    try:
        state = dp.fsm.get_context(bot=bot, chat_id=501, user_id=501)
        await state.set_state('FitnessStates:active_ai')
        async with db() as session:
            session.add(User(telegram_id=501, language='uz', full_name='Test', phone_number='123', balance=0))
            await session.commit()
            monkeypatch.setattr(Message, 'answer', AsyncMock())
            monkeypatch.setattr(handlers, 'show_tariffs', AsyncMock())
            await dp.feed_update(bot, Update(update_id=1, message=Message(
                message_id=1, date=dt.datetime.now(UTC), chat={'id': 501, 'type': 'private'},
                from_user={'id': 501, 'is_bot': False, 'first_name': 'Test'}, text='/start',
                entities=[{'type': 'bot_command', 'offset': 0, 'length': 6}])), session=session)
        assert await state.get_state() is None
        catchall.assert_not_awaited()
    finally:
        await bot.session.close()
        await dp.storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('active,link', [(True, 'https://t.me/+owned'), (True, None), (False, 'https://t.me/+expired')])
async def test_training_only_exposes_active_persisted_access(db, monkeypatch, active, link):
    now = dt.datetime.now(UTC)
    async with db() as session:
        session.add(User(telegram_id=501, language='uz', full_name='Test', phone_number='123', balance=0))
        await session.flush()
        session.add(Subscription(user_id=501, status='active', tariff_months=1,
            started_at=now-dt.timedelta(days=30), expires_at=now+dt.timedelta(days=1 if active else -1), invite_link=link))
        await session.commit()
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=501)
    tariffs = AsyncMock()
    monkeypatch.setattr(handlers, 'show_tariffs', tariffs)
    async with db() as session:
        await handlers.msg_training(message, session, AsyncMock())
    if active and link:
        assert message.answer.await_args.kwargs['reply_markup'].inline_keyboard[0][0].url == link
    elif active:
        message.answer.assert_awaited_once_with(texts.TRAINING_ACCESS_PENDING['uz'])
    else:
        message.answer.assert_not_awaited()
        tariffs.assert_awaited_once()
