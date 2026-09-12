"""Cashback/TTL/leases on real isolated PostgreSQL; Telegram never uses the network."""
import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select, text

from bot.config import config
from bot.database.models import User, Payment, ClickTransaction, PaymeTransaction, PaymentDelivery, Subscription
from bot.services import rahmat, scheduler, payment_delivery
from bot.services.click import api, errors, protocol
from bot.services.payment_policy import CashbackCoversTariff
from test_click_audit import db, local_postgres, client, call, form, ACTION_PREPARE, ACTION_COMPLETE, USER_ID

UTC = dt.timezone.utc


@pytest.fixture(autouse=True)
def workers(db, monkeypatch):
    monkeypatch.setattr(scheduler, 'AsyncSessionLocal', db)
    monkeypatch.setattr(payment_delivery, 'AsyncSessionLocal', db)


async def mint(db, key, *, user_id=USER_ID, balance=100_000, method='click'):
    async with db() as session:
        if await session.get(User, user_id) is None:
            session.add(User(telegram_id=user_id, balance=balance, language='uz'))
            await session.commit()
        return await rahmat.create_payment_intent(session, user_id=user_id, months=1,
            method=method, use_cashback=True, request_key=key)


async def prepare(client, order, tid):
    return await call(client, ACTION_PREPARE, form(ACTION_PREPARE, click_trans_id=tid,
        merchant_trans_id=order.id, amount=f'{order.amount}.00'))


async def complete(client, order, tid, prepared, **extra):
    return await call(client, ACTION_COMPLETE, form(ACTION_COMPLETE, click_trans_id=tid,
        merchant_trans_id=order.id, amount=f'{order.amount}.00',
        merchant_prepare_id=prepared['merchant_prepare_id'], **extra))


@pytest.mark.asyncio
async def test_concurrent_distinct_invoices_reserve_once_and_both_complete(client, db):
    async with db() as session:
        session.add(User(telegram_id=USER_ID, balance=100_000, language='uz'))
        await session.commit()
    a, b = await asyncio.gather(mint(db, 'a'), mint(db, 'b'))
    assert sorted([a.amount, b.amount]) == [400_000, 500_000]
    assert a.cashback_reserved + b.cashback_reserved == 100_000
    pa, pb = await asyncio.gather(prepare(client, a, 601), prepare(client, b, 602))
    results = await asyncio.gather(complete(client, a, 601, pa), complete(client, b, 602, pb))
    assert [r['error'] for r in results] == [0, 0]
    async with db() as session:
        user = await session.get(User, USER_ID)
        assert user.balance == user.reserved_cashback == 0
        assert await session.scalar(select(func.count()).select_from(Subscription)) == 2


@pytest.mark.asyncio
async def test_same_button_replay_keeps_one_hold(db):
    a = await mint(db, 'same')
    b = await mint(db, 'same')
    assert a.id == b.id
    async with db() as session:
        assert (await session.get(User, USER_ID)).reserved_cashback == 100_000


@pytest.mark.asyncio
async def test_click_cancel_releases_hold_exactly_once(client, db):
    order = await mint(db, 'cancel')
    prepared = await prepare(client, order, 603)
    for _ in range(2):
        result = await complete(client, order, 603, prepared, error=-9)
        assert result['error'] == errors.TRANSACTION_CANCELLED
    async with db() as session:
        user = await session.get(User, USER_ID)
        assert user.balance == 100_000 and user.reserved_cashback == 0
        assert (await session.get(Payment, order.id)).cashback_reserved == 0
    assert (await mint(db, 'new')).amount == 400_000


@pytest.mark.asyncio
async def test_active_prepare_outlives_order_ttl_and_complete_succeeds(client, db):
    order = await mint(db, 'ttl')
    async with db() as session:
        (await session.get(Payment, order.id)).created_at = dt.datetime.now(UTC)-dt.timedelta(hours=23, minutes=59)
        await session.commit()
    prepared = await prepare(client, order, 604)
    async with db() as session:
        (await session.get(Payment, order.id)).created_at -= dt.timedelta(minutes=2)
        await session.commit()
    await scheduler._fail_stale_payments(dt.datetime.now(UTC))
    assert (await complete(client, order, 604, prepared))['error'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['click', 'payme', None])
async def test_cron_releases_expired_order_and_provider_hold(db, client, provider):
    order = await mint(db, 'expire', method=provider or 'manual_card')
    if provider == 'click':
        await prepare(client, order, 605)
    async with db() as session:
        if provider == 'click':
            (await session.scalar(select(ClickTransaction))).created_at -= dt.timedelta(hours=13)
        elif provider == 'payme':
            session.add(PaymeTransaction(payme_id='expired', payment_id=order.id, amount=order.amount*100,
                state=1, payme_time=int((dt.datetime.now(UTC)-dt.timedelta(hours=13)).timestamp()*1000)))
        else:
            (await session.get(Payment, order.id)).created_at -= dt.timedelta(hours=25)
        await session.commit()
    await scheduler._fail_stale_payments(dt.datetime.now(UTC))
    await scheduler._fail_stale_payments(dt.datetime.now(UTC))
    async with db() as session:
        assert (await session.get(Payment, order.id)).status == 'failed'
        assert (await session.get(User, USER_ID)).reserved_cashback == 0
        assert (await session.get(User, USER_ID)).balance == 100_000


@pytest.mark.asyncio
async def test_zero_external_invoice_does_not_hold_cashback(db):
    with pytest.raises(CashbackCoversTariff):
        await mint(db, 'zero', balance=500_000)
    async with db() as session:
        assert (await session.get(User, USER_ID)).reserved_cashback == 0
        assert await session.scalar(select(Payment)) is None


async def paid(db, key, user_id=USER_ID):
    order = await mint(db, key, user_id=user_id, balance=0)
    async with db() as session:
        assert await rahmat.process_successful_payment(order.id, session, AsyncMock())
    return order.id


@pytest.mark.asyncio
async def test_delivery_network_holds_no_connection_or_user_lock(db):
    pid = await paid(db, 'paid')
    bot = AsyncMock()
    async def unlocked(*args, **kwargs):
        assert db.kw['bind'].pool.checkedout() == 0
        async with db() as session, session.begin():
            await session.scalar(select(User).where(User.telegram_id == USER_ID).with_for_update(nowait=True))
            await session.scalar(select(PaymentDelivery).where(PaymentDelivery.payment_id == pid).with_for_update(nowait=True))
        return SimpleNamespace(invite_link='https://t.me/+owned')
    bot.create_chat_invite_link.side_effect = unlocked
    bot.send_message.side_effect = unlocked
    await payment_delivery.deliver_payment(pid, bot)
    async with db() as session:
        job = await session.get(PaymentDelivery, pid)
        assert job.completed_at is not None and job.lease_token is None
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_workers_claim_same_job_once(db):
    pid = await paid(db, 'claim')
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = SimpleNamespace(invite_link='https://t.me/+one')
    await asyncio.gather(*(payment_delivery.deliver_payment(pid, bot) for _ in range(6)))
    bot.create_chat_invite_link.assert_awaited_once()
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_lease_recovers_and_fences_old_worker(db):
    pid = await paid(db, 'lease')
    old = await payment_delivery._claim(pid)
    async with db() as session:
        (await session.get(PaymentDelivery, pid)).locked_until = dt.datetime.now(UTC)-dt.timedelta(seconds=1)
        await session.commit()
    new = await payment_delivery._claim(pid)
    assert new.token != old.token
    await payment_delivery._mark_sent(old)
    await payment_delivery._release(old, 'old error')
    async with db() as session:
        job = await session.get(PaymentDelivery, pid)
        assert job.completed_at is None and job.lease_token == new.token


@pytest.mark.asyncio
async def test_revocation_during_invite_creation_cannot_restore_link(db):
    pid = await paid(db, 'revoke')
    bot = AsyncMock()
    async def revoke(*args, **kwargs):
        async with db() as session:
            sub = await session.scalar(select(Subscription))
            sub.status = 'revocation_pending'
            await session.commit()
        return SimpleNamespace(invite_link='https://t.me/+unused')
    bot.create_chat_invite_link.side_effect = revoke
    await payment_delivery.deliver_payment(pid, bot)
    bot.send_message.assert_not_awaited()
    bot.revoke_chat_invite_link.assert_awaited_once()
    async with db() as session:
        assert (await session.scalar(select(Subscription))).invite_link is None


@pytest.mark.asyncio
async def test_delivery_batch_is_parallel_and_bounded(db, monkeypatch):
    for index in range(6):
        await paid(db, f'batch-{index}', user_id=100+index)
    monkeypatch.setattr(config, 'payment_delivery_concurrency', 2)
    active = maximum = 0
    async def send(*args, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(active, maximum)
        await asyncio.sleep(.03)
        active -= 1
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = SimpleNamespace(invite_link='https://t.me/+batch')
    bot.send_message.side_effect = send
    await payment_delivery.deliver_pending_payments(bot)
    assert maximum == 2
    assert bot.send_message.await_count == 6


@pytest.mark.asyncio
async def test_migration_backfills_holds_and_repeats(db):
    from bot.database.audit_migration import migrate_audit_fields
    async with db() as session:
        session.add(User(telegram_id=USER_ID, balance=100_000))
        await session.flush()
        session.add(Payment(user_id=USER_ID, amount=400_000, cashback_applied=100_000,
                            tariff_months=1, payment_method='click', status='pending'))
        await session.commit()
    for _ in range(2):
        async with db.kw['bind'].begin() as conn:
            await migrate_audit_fields(conn)
    async with db() as session:
        assert (await session.get(User, USER_ID)).reserved_cashback == 100_000
        assert (await session.scalar(select(Payment))).cashback_reserved == 100_000


@pytest.mark.asyncio
async def test_migration_refuses_overcommitted_legacy_orders(db):
    from bot.database.audit_migration import migrate_audit_fields
    await mint(db, 'held')
    async with db() as session:
        session.add(Payment(user_id=USER_ID, amount=400_000, cashback_applied=100_000,
                            tariff_months=1, payment_method='click', status='pending'))
        await session.commit()
    with pytest.raises(RuntimeError, match='reconciliation'):
        async with db.kw['bind'].begin() as conn:
            await migrate_audit_fields(conn)
    async with db() as session:
        assert (await session.get(User, USER_ID)).reserved_cashback == 100_000


@pytest.mark.asyncio
async def test_payme_cancel_releases_order_hold(db):
    from bot.services.payme import service
    from bot.services.payme.protocol import now_ms
    order = await mint(db, 'payme-cancel', method='payme')
    async with db() as session:
        await service.create_transaction(session, {'id': 'cancel-id', 'amount': order.amount*100,
            'time': now_ms(), 'account': {'order_id': order.id}})
    for _ in range(2):
        async with db() as session:
            await service.cancel_transaction(session, {'id': 'cancel-id', 'reason': 1})
    async with db() as session:
        assert (await session.get(User, USER_ID)).reserved_cashback == 0
        assert (await session.get(User, USER_ID)).balance == 100_000


@pytest.mark.asyncio
async def test_complete_vs_cron_has_one_consistent_outcome(client, db):
    order = await mint(db, 'cron-race')
    prepared = await prepare(client, order, 610)
    async with db() as session:
        (await session.get(Payment, order.id)).created_at -= dt.timedelta(hours=25)
        await session.commit()
    result, _ = await asyncio.gather(complete(client, order, 610, prepared),
        scheduler._fail_stale_payments(dt.datetime.now(UTC)))
    assert result['error'] == 0
    async with db() as session:
        assert (await session.get(Payment, order.id)).status == 'completed'
        assert (await session.get(User, USER_ID)).reserved_cashback == 0


@pytest.mark.asyncio
async def test_duplicate_first_prepare_replays_same_id(client, db):
    order = await mint(db, 'prepare-race')
    results = await asyncio.gather(*(prepare(client, order, 611) for _ in range(8)))
    assert all(item == results[0] for item in results)
    assert results[0]['error'] == 0


@pytest.mark.asyncio
async def test_delivery_failure_retries_without_losing_saved_link(db):
    pid = await paid(db, 'send-fail')
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = SimpleNamespace(invite_link='https://t.me/+saved')
    bot.send_message.side_effect = TimeoutError('ambiguous Telegram response')
    await payment_delivery.deliver_payment(pid, bot)
    async with db() as session:
        job = await session.get(PaymentDelivery, pid)
        assert job.completed_at is None and job.lease_token is None
        assert 'TimeoutError' in job.last_error
        assert (await session.scalar(select(Subscription))).invite_link == 'https://t.me/+saved'
        job.next_attempt_at = dt.datetime.now(UTC)-dt.timedelta(seconds=1)
        await session.commit()
    bot.send_message.side_effect = None
    await payment_delivery.deliver_payment(pid, bot)
    bot.create_chat_invite_link.assert_awaited_once()
    assert bot.send_message.await_count == 2
    async with db() as session:
        assert (await session.get(PaymentDelivery, pid)).completed_at is not None


@pytest.mark.asyncio
async def test_referral_retry_does_not_repeat_member_message(db):
    async with db() as session:
        session.add(User(telegram_id=10, balance=0, language='uz'))
        session.add(User(telegram_id=USER_ID, referred_by=10, balance=0, language='uz'))
        await session.commit()
    pid = await paid(db, 'referral')
    bot = AsyncMock()
    bot.create_chat_invite_link.return_value = SimpleNamespace(invite_link='https://t.me/+ref')
    async def send(user_id, *args, **kwargs):
        assert db.kw['bind'].pool.checkedout() == 0
        if user_id == 10:
            raise TimeoutError('referral timeout')
    bot.send_message.side_effect = send
    await payment_delivery.deliver_payment(pid, bot)
    async with db() as session:
        job = await session.get(PaymentDelivery, pid)
        assert job.completed_at is not None and not job.referral_notified
        job.next_attempt_at = dt.datetime.now(UTC)-dt.timedelta(seconds=1)
        await session.commit()
    bot.send_message.side_effect = None
    await payment_delivery.deliver_payment(pid, bot)
    assert sum(c.args[0] == USER_ID for c in bot.send_message.await_args_list) == 1
    async with db() as session:
        assert (await session.get(PaymentDelivery, pid)).referral_notified
