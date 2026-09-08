"""Real PostgreSQL concurrency and failure injection; only a temporary local DB."""
import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import config
from bot.database.models import Base, CashbackTransaction, Payment, PaymentDelivery, Subscription, User
from bot.services import payment_delivery, rahmat, scheduler
from bot.services.payment_policy import PaymentValidationError

UTC = dt.timezone.utc


@pytest.fixture(scope="module")
def local_postgres(tmp_path_factory):
    pgembed = pytest.importorskip("pgembed", reason="Install requirements-dev.txt for real PostgreSQL tests")
    server = pgembed.get_server(tmp_path_factory.mktemp("audit-pg"), cleanup_mode="delete")
    try:
        yield server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)
    finally:
        server.cleanup()


@pytest_asyncio.fixture
async def db(local_postgres, monkeypatch):
    engine = create_async_engine(local_postgres, pool_size=5, max_overflow=0,
                                 connect_args={"timeout": 5, "command_timeout": 10})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(payment_delivery, "AsyncSessionLocal", factory)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", factory)
    monkeypatch.setattr(config, "channel_id", -1001)
    monkeypatch.setattr(config, "vip_chat_id", -1002)
    monkeypatch.setattr(config, "cashback_reward_amount", 30000)
    yield factory
    await engine.dispose()


async def seed(db, *, balance=500000, months=1, amount=0, cashback=500000, user_id=42, referrer=None):
    async with db() as session:
        user = await session.get(User, user_id)
        if user is None:
            session.add(User(telegram_id=user_id, balance=balance, language="ru", referred_by=referrer))
            await session.flush()
        payment = Payment(user_id=user_id, amount=amount, cashback_applied=cashback, tariff_months=months,
                          status="pending", payment_method="cashback" if amount == 0 else "manual_card")
        session.add(payment)
        await session.commit()
        return payment.id


async def confirm(db, payment_id):
    async with db() as session:
        return await rahmat.process_successful_payment(payment_id, session, AsyncMock())


async def count(db, model):
    async with db() as session:
        return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_twenty_admin_confirmations_commit_once(db):
    payment_id = await seed(db)
    results = await asyncio.gather(*(confirm(db, payment_id) for _ in range(20)))
    assert results.count(True) == 1
    assert await count(db, Subscription) == 1
    assert await count(db, CashbackTransaction) == 1
    assert await count(db, PaymentDelivery) == 1
    async with db() as session:
        assert (await session.get(User, 42)).balance == 0
        assert (await session.get(Payment, payment_id)).status == "completed"


@pytest.mark.asyncio
async def test_two_payments_cannot_spend_same_cashback(db):
    ids = [await seed(db), await seed(db)]
    results = await asyncio.gather(*(confirm(db, pid) for pid in ids), return_exceptions=True)
    assert results.count(True) == 1
    assert sum(isinstance(item, PaymentValidationError) for item in results) == 1
    assert await count(db, Subscription) == 1
    assert await count(db, CashbackTransaction) == 1


@pytest.mark.asyncio
async def test_replayed_ui_action_deduplicates_intents(db):
    async with db() as session:
        session.add(User(telegram_id=42, balance=1000000))
        await session.commit()
    async def create():
        async with db() as session:
            return (await rahmat.create_payment_intent(
                session, user_id=42, months=1, method="cashback", use_cashback=True, request_key="same-button")).id
    ids = await asyncio.gather(*(create() for _ in range(20)))
    assert len(set(ids)) == 1
    assert await count(db, Payment) == 1


@pytest.mark.asyncio
async def test_zero_balance_cannot_activate_cashback_tariff(db):
    async with db() as session:
        session.add(User(telegram_id=42, balance=0))
        await session.commit()
        with pytest.raises(PaymentValidationError):
            await rahmat.create_payment_intent(session, user_id=42, months=6, method="cashback",
                                               use_cashback=True, request_key="forged-or-stale-button")
    assert await count(db, Payment) == 0
    assert await count(db, Subscription) == 0


@pytest.mark.asyncio
async def test_legacy_underfunded_pending_payment_is_rejected(db):
    pid = await seed(db, balance=0, cashback=0)
    with pytest.raises(PaymentValidationError):
        await confirm(db, pid)
    assert await count(db, Subscription) == 0
    async with db() as session:
        assert (await session.get(Payment, pid)).status == "pending"


@pytest.mark.asyncio
async def test_distinct_paid_renewals_add_both_periods(db):
    ids = [await seed(db, amount=500000, cashback=0), await seed(db, amount=500000, cashback=0)]
    assert await asyncio.gather(*(confirm(db, pid) for pid in ids)) == [True, True]
    async with db() as session:
        subs = list((await session.scalars(select(Subscription).order_by(Subscription.expires_at))).all())
        assert len(subs) == 2
        assert subs[1].expires_at - subs[0].started_at == dt.timedelta(days=60)


@pytest.mark.asyncio
async def test_referrals_for_two_buyers_do_not_lose_credit(db):
    async with db() as session:
        session.add(User(telegram_id=5, balance=0))
        await session.commit()
    ids = [await seed(db, user_id=uid, amount=500000, cashback=0, referrer=5) for uid in (42, 43)]
    assert await asyncio.gather(*(confirm(db, pid) for pid in ids)) == [True, True]
    assert await count(db, CashbackTransaction) == 2
    async with db() as session:
        assert (await session.get(User, 5)).balance == 60000


@pytest.mark.asyncio
async def test_two_first_payments_award_referral_only_once(db):
    async with db() as session:
        session.add(User(telegram_id=5, balance=0))
        await session.commit()
    ids = [await seed(db, amount=500000, cashback=0, referrer=5) for _ in range(2)]
    assert await asyncio.gather(*(confirm(db, pid) for pid in ids)) == [True, True]
    async with db() as session:
        assert (await session.get(User, 5)).balance == 30000
    assert await count(db, CashbackTransaction) == 1


@pytest.mark.asyncio
async def test_confirm_reject_race_preserves_terminal_consistency(db):
    pid = await seed(db)
    async def reject():
        async with db() as session:
            return await rahmat.reject_pending_payment(pid, session)
    approved, rejected_user = await asyncio.gather(confirm(db, pid), reject())
    assert approved != (rejected_user is not None)
    async with db() as session:
        payment = await session.get(Payment, pid)
        assert payment.status == ("completed" if approved else "failed")
        assert (await session.get(User, 42)).balance == (0 if approved else 500000)
    assert await count(db, Subscription) == int(approved)


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_entire_financial_unit(db):
    pid = await seed(db)
    async with db() as session:
        def fail_commit(_session):
            raise RuntimeError("injected commit failure")
        event.listen(session.sync_session, "before_commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected"):
            await rahmat.process_successful_payment(pid, session, AsyncMock())
    async with db() as session:
        assert (await session.get(Payment, pid)).status == "pending"
        assert (await session.get(User, 42)).balance == 500000
    assert await count(db, Subscription) == 0
    assert await count(db, CashbackTransaction) == 0
    assert await count(db, PaymentDelivery) == 0


@pytest.mark.asyncio
async def test_api_timeout_keeps_money_and_retries_delivery(db):
    pid = await seed(db)
    assert await confirm(db, pid)
    bot = AsyncMock()
    bot.create_chat_invite_link.side_effect = TimeoutError("injected network timeout")
    await payment_delivery.deliver_pending_payments(bot)
    async with db() as session:
        assert (await session.get(Payment, pid)).status == "completed"
        assert (await session.get(User, 42)).balance == 0
        job = await session.get(PaymentDelivery, pid)
        assert job.attempts == 1 and job.completed_at is None
        job.next_attempt_at = dt.datetime.now(UTC) - dt.timedelta(seconds=1)
        await session.commit()
    bot.create_chat_invite_link.side_effect = None
    bot.create_chat_invite_link.return_value = SimpleNamespace(invite_link="https://t.me/+test")
    async def sent(*args, **kwargs):
        async with db() as observer:
            sub = await observer.scalar(select(Subscription))
            assert sub.invite_link == "https://t.me/+test"  # committed before exposure
    bot.send_message.side_effect = sent
    await payment_delivery.deliver_pending_payments(bot)
    async with db() as session:
        assert (await session.get(PaymentDelivery, pid)).completed_at is not None
    assert await count(db, Subscription) == 1
    assert await count(db, CashbackTransaction) == 1
    assert bot.create_chat_invite_link.await_args.kwargs["creates_join_request"] is True


@pytest.mark.asyncio
async def test_stale_unpaid_order_does_not_revoke_paid_membership(db):
    pid = await seed(db, amount=500000, cashback=0)
    await confirm(db, pid)
    stale = await seed(db, amount=500000, cashback=0)
    async with db() as session:
        payment = await session.get(Payment, stale)
        payment.created_at = dt.datetime.now(UTC) - dt.timedelta(days=2)
        await session.commit()
    bot = AsyncMock()
    await scheduler.run_cron_jobs(bot)
    async with db() as session:
        assert (await session.get(Payment, stale)).status == "failed"
        assert (await session.scalar(select(Subscription))).status == "active"
    bot.unban_chat_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_old_subscription_expiry_does_not_kick_renewed_user(db):
    pid = await seed(db, amount=500000, cashback=0)
    await confirm(db, pid)
    async with db() as session:
        old = Subscription(user_id=42, status="active", tariff_months=1,
                           started_at=dt.datetime.now(UTC)-dt.timedelta(days=31),
                           expires_at=dt.datetime.now(UTC)-dt.timedelta(days=1), invite_link="https://t.me/+old")
        session.add(old)
        await session.commit()
        old_id = old.id
    bot = AsyncMock()
    await scheduler._expire_subscription(bot, old_id)
    bot.unban_chat_member.assert_not_awaited()
    bot.revoke_chat_invite_link.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("joining_user,expected", [(42, True), (43, False)])
async def test_join_link_admits_only_paid_owner(db, joining_user, expected):
    from bot.handlers.user import authorize_paid_join
    pid = await seed(db)
    await confirm(db, pid)
    async with db() as session:
        session.add(User(telegram_id=43, balance=0))
        sub = await session.scalar(select(Subscription))
        sub.invite_link = "https://t.me/+personal"
        await session.commit()
    request = SimpleNamespace(chat=SimpleNamespace(id=-1001), from_user=SimpleNamespace(id=joining_user),
                              invite_link=SimpleNamespace(invite_link="https://t.me/+personal"))
    bot = AsyncMock()
    async with db() as session:
        await authorize_paid_join(request, session, bot)
    assert bot.approve_chat_join_request.await_count == int(expected)
    assert bot.decline_chat_join_request.await_count == int(not expected)


@pytest.mark.asyncio
async def test_cancellation_rolls_back_flushed_financial_changes(db, monkeypatch):
    pid = await seed(db)
    async with db() as session:
        monkeypatch.setattr(session, "commit", AsyncMock(side_effect=asyncio.CancelledError))
        with pytest.raises(asyncio.CancelledError):
            await rahmat.process_successful_payment(pid, session, AsyncMock())
    async with db() as session:
        assert (await session.get(User, 42)).balance == 500000
        assert (await session.get(Payment, pid)).status == "pending"
    assert await count(db, PaymentDelivery) == 0
    assert await count(db, CashbackTransaction) == 0


@pytest.mark.asyncio
async def test_additive_migration_upgrades_legacy_schema_and_repeats(db, monkeypatch):
    import run_migration
    from sqlalchemy import text
    engine = db.kw["bind"]
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE payments DROP COLUMN request_key CASCADE"))
        await conn.execute(text("DROP TABLE payment_deliveries"))
    async def initialize():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(run_migration, "engine", engine)
    monkeypatch.setattr(run_migration, "init_db", initialize)
    await run_migration.main()
    await run_migration.main()
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM payment_deliveries")) == 0
        assert await conn.scalar(text(
            "SELECT count(*) FROM information_schema.columns WHERE table_name='payments' AND column_name='request_key'"
        )) == 1
        assert await conn.scalar(text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname='ix_payments_request_key'"
        )) is True


@pytest.mark.asyncio
async def test_invite_rotation_cleans_expired_links_and_persists_new_owner_links(db, monkeypatch):
    import rotate_invites
    monkeypatch.setattr(rotate_invites, "AsyncSessionLocal", db)
    pid = await seed(db)
    await confirm(db, pid)
    async with db() as session:
        active = await session.scalar(select(Subscription))
        active.invite_link = "https://t.me/+legacy"
        active_id = active.id
        old = Subscription(user_id=42, status="expired", tariff_months=1,
                           started_at=dt.datetime.now(UTC)-dt.timedelta(days=31),
                           expires_at=dt.datetime.now(UTC)-dt.timedelta(days=1), invite_link="https://t.me/+expired")
        session.add(old)
        await session.commit()
        old_id = old.id
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = SimpleNamespace(invite_link="https://t.me/+rotated")
    await rotate_invites.rotate_one(active_id, bot)
    await rotate_invites.rotate_one(old_id, bot)
    async with db() as session:
        assert (await session.get(Subscription, active_id)).invite_link == "https://t.me/+rotated"
        assert (await session.get(Subscription, old_id)).invite_link is None
    assert bot.revoke_chat_invite_link.await_count == 2
    assert bot.create_chat_invite_link.await_args.kwargs["creates_join_request"] is True
    bot.send_message.assert_awaited_once()
