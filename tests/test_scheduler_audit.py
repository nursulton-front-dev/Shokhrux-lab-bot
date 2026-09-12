"""Fault-injection checks use fake Telegram and sessions, never production I/O."""

import asyncio
import datetime
import os
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import EditMessageMedia, SendMessage
from aiogram.types import InputMediaPhoto
from sqlalchemy.dialects import postgresql

with patch("pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}), patch.dict(
    os.environ,
    {"BOT_TOKEN": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
     "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test"},
):
    from bot.services import scheduler
    from bot.services.background_tasks import create_background_task, stop_background_tasks
    from bot.services.telegram_rate_limit import TelegramRateLimitMiddleware, kick_member, revoke_invite
    import run_polling


class FakeSession:
    def __init__(self, sub=None, entitled=()):
        self.sub = sub
        self.scalar = AsyncMock(side_effect=[42, SimpleNamespace(language="ru")])
        self.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: list(entitled)))
        self.get = AsyncMock(return_value=sub)
        self.execute = AsyncMock()
        self.committed = False
        self.rolled_back = False

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.committed = exc_type is None
        self.rolled_back = exc_type is not None


def subscription(**overrides):
    values = dict(
        id=1, user_id=42, status="active", tariff_months=6,
        expires_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
        invite_link="main-link", vip_invite_link="vip-link", notified_3d=False, notified_1d=False,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def chats(monkeypatch):
    monkeypatch.setattr(scheduler.config, "channel_id", -1001)
    monkeypatch.setattr(scheduler.config, "vip_chat_id", -1002)


@pytest.mark.asyncio
async def test_revoke_failure_keeps_cleanup_retryable(monkeypatch, chats):
    sub = subscription()
    session = FakeSession(sub)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: session)
    bot = SimpleNamespace(revoke_chat_invite_link=AsyncMock(side_effect=TimeoutError()),
                          unban_chat_member=AsyncMock(), send_message=AsyncMock())
    with pytest.raises(TimeoutError):
        await scheduler._expire_subscription(bot, 1)
    assert sub.status == "active"
    assert sub.invite_link == "main-link"
    assert session.rolled_back
    bot.unban_chat_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_paid_replacement_subscription_prevents_kick(monkeypatch, chats):
    sub = subscription()
    session = FakeSession(sub, entitled=[subscription(id=2)])
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: session)
    bot = SimpleNamespace(revoke_chat_invite_link=AsyncMock(), unban_chat_member=AsyncMock(),
                          send_message=AsyncMock())
    await scheduler._expire_subscription(bot, 1)
    assert sub.status == "expired"
    assert bot.revoke_chat_invite_link.await_count == 2
    bot.unban_chat_member.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_renewal_is_rechecked_after_user_lock(monkeypatch, chats):
    sub = subscription(expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30))
    session = FakeSession(sub)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: session)
    bot = SimpleNamespace(revoke_chat_invite_link=AsyncMock(), unban_chat_member=AsyncMock())
    await scheduler._expire_subscription(bot, 1)
    bot.revoke_chat_invite_link.assert_not_awaited()
    bot.unban_chat_member.assert_not_awaited()
    lock_sql = str(session.scalar.await_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in lock_sql


@pytest.mark.asyncio
async def test_admin_pending_revocation_retries_even_before_expiry(monkeypatch, chats):
    sub = subscription(status="revocation_pending", expires_at=datetime.datetime.now(datetime.timezone.utc)
                       + datetime.timedelta(days=30))
    session = FakeSession(sub)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: session)
    bot = SimpleNamespace(revoke_chat_invite_link=AsyncMock(), unban_chat_member=AsyncMock(),
                          send_message=AsyncMock())
    await scheduler._expire_subscription(bot, 1)
    assert sub.status == "expired"
    assert bot.unban_chat_member.await_count == 2
    assert session.committed


@pytest.mark.asyncio
async def test_one_user_failure_does_not_stop_batch(monkeypatch):
    async def ids(*conditions):
        yield 1
        yield 2

    expired = []

    async def expire(bot, subscription_id):
        expired.append(subscription_id)
        if subscription_id == 1:
            raise RuntimeError("Injected per-user failure")

    monkeypatch.setattr(scheduler, "_subscription_ids", ids)
    monkeypatch.setattr(scheduler, "_expire_subscription", expire)
    monkeypatch.setattr(scheduler, "_remind_subscription", AsyncMock())
    monkeypatch.setattr(scheduler, "_fail_stale_payments", AsyncMock())
    await scheduler.run_cron_jobs(Mock())
    assert expired == [1, 2]
    assert scheduler._remind_subscription.await_count == 4


@pytest.mark.asyncio
async def test_kick_uses_single_non_banning_operation():
    bot = SimpleNamespace(ban_chat_member=AsyncMock(), unban_chat_member=AsyncMock())
    await kick_member(bot, -1001, 42)
    bot.ban_chat_member.assert_not_awaited()
    bot.unban_chat_member.assert_awaited_once_with(
        chat_id=-1001, user_id=42, only_if_banned=False, request_timeout=15
    )


@pytest.mark.asyncio
async def test_revoke_does_not_suppress_missing_admin_rights():
    method = SendMessage(chat_id=42, text="test")
    bot = SimpleNamespace(revoke_chat_invite_link=AsyncMock(side_effect=TelegramBadRequest(
        method=method, message="not enough rights to manage invite links"
    )))
    with pytest.raises(TelegramBadRequest):
        await revoke_invite(bot, -1001, "link")


@pytest.mark.asyncio
async def test_global_limiter_serializes_independent_senders():
    middleware = TelegramRateLimitMiddleware(requests_per_second=25)
    observed = []

    async def send(bot, method):
        observed.append(asyncio.get_running_loop().time())
        return True

    await asyncio.gather(*(middleware(send, Mock(), SendMessage(chat_id=100 + index, text="test"))
                           for index in range(5)))
    assert all(b - a >= 0.035 for a, b in zip(observed, observed[1:]))


@pytest.mark.asyncio
async def test_429_is_retried_but_network_ambiguity_is_not():
    middleware = TelegramRateLimitMiddleware(requests_per_second=1000)
    method = SendMessage(chat_id=42, text="test")
    request = AsyncMock(side_effect=[TelegramRetryAfter(method=method, message="flood", retry_after=0), True])
    assert await middleware(request, Mock(), method) is True
    assert request.await_count == 2
    request = AsyncMock(side_effect=TimeoutError("response lost"))
    with pytest.raises(TimeoutError):
        await middleware(request, Mock(), SendMessage(chat_id=43, text="test"))
    request.assert_awaited_once()


@pytest.mark.asyncio
async def test_media_edit_is_not_treated_as_album():
    middleware = TelegramRateLimitMiddleware()
    request = AsyncMock(return_value=True)
    method = EditMessageMedia(chat_id=42, message_id=1, media=InputMediaPhoto(media="file-id"))
    assert await middleware(request, Mock(), method) is True


@pytest.mark.asyncio
async def test_shutdown_cancels_tracked_broadcast_before_transport_close():
    cancelled = asyncio.Event()

    async def broadcast():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = create_background_task(broadcast(), name="test-broadcast")
    await asyncio.sleep(0)
    await stop_background_tasks(timeout=0.001)
    assert cancelled.is_set()
    assert task.cancelled()


@pytest.mark.asyncio
async def test_shutdown_drains_aiogram_update_tasks():
    complete = asyncio.Event()

    async def handler():
        await asyncio.sleep(0.01)
        complete.set()

    task = asyncio.create_task(handler())
    await run_polling._drain_handlers(SimpleNamespace(_handle_update_tasks={task}))
    assert complete.is_set()
    assert task.done()


@pytest.mark.asyncio
async def test_polling_preserves_queued_updates_and_starts_workers_once(monkeypatch):
    bot = SimpleNamespace(delete_webhook=AsyncMock())
    dp = SimpleNamespace(start_polling=AsyncMock())
    monkeypatch.setattr(run_polling, "init_db", AsyncMock())
    monkeypatch.setattr(run_polling, "start_scheduler", AsyncMock())
    monkeypatch.setattr(run_polling, "start_payment_delivery", AsyncMock())
    monkeypatch.setattr(run_polling, "run_payment_server", AsyncMock())
    workers = []
    await run_polling._run_application(bot, dp, workers)
    await asyncio.gather(*workers)
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False, request_timeout=15)
    # scheduler, payment delivery, and the merchant callback endpoint.
    assert len(workers) == 3
    assert {task.get_name() for task in workers} == {
        "subscription-scheduler", "payment-delivery", "payments-endpoint"
    }
    dp.start_polling.assert_awaited_once_with(
        bot, handle_signals=False, close_bot_session=False, tasks_concurrency_limit=50
    )


@pytest.mark.asyncio
async def test_sigterm_during_startup_closes_http_and_database(monkeypatch):
    callbacks = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", lambda sig, callback: callbacks.update({sig: callback}))
    monkeypatch.setattr(loop, "remove_signal_handler", lambda sig: None)
    listener = Mock()
    monkeypatch.setattr(run_polling, "setup_logging", lambda: listener)
    monkeypatch.setattr(run_polling, "stop_logging", Mock())
    bot = SimpleNamespace(session=SimpleNamespace(middleware=Mock(), close=AsyncMock()))
    dp = SimpleNamespace(
        update=SimpleNamespace(middleware=Mock()), include_router=Mock(),
        stop_polling=AsyncMock(side_effect=RuntimeError("Polling is not started")),
        _handle_update_tasks=set(),
    )
    monkeypatch.setattr(run_polling, "Bot", lambda **kwargs: bot)
    monkeypatch.setattr(run_polling, "Dispatcher", lambda **kwargs: dp)
    monkeypatch.setattr(run_polling, "engine", SimpleNamespace(dispose=AsyncMock()))

    async def initializing():
        callbacks[signal.SIGTERM]()
        await asyncio.Event().wait()

    monkeypatch.setattr(run_polling, "init_db", initializing)
    await asyncio.wait_for(run_polling.main(), timeout=1)
    bot.session.close.assert_awaited_once()
    run_polling.engine.dispose.assert_awaited_once()
