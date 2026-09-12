"""Click SHOP API over real HTTP and real PostgreSQL; no external calls."""
import datetime as dt
import hashlib
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import config
from bot.database.models import Base, ClickTransaction, Payment, Subscription, User
from bot.services.click import api, errors, protocol
from bot.services.click.protocol import (
    ACTION_COMPLETE,
    ACTION_PREPARE,
    METHOD_CLICK,
    STATE_CANCELLED,
    STATE_CONFIRMED,
    STATE_PREPARED,
)

UTC = dt.timezone.utc
SECRET = "click-secret-value"
SERVICE_ID = 111815
MERCHANT_ID = 64579
USER_ID = 77
TARIFF_MONTHS = 1
TARIFF_PRICE = 500_000
SIGN_TIME = "2026-09-10 12:00:00"


def sign(action: int, *, click_trans_id: int, merchant_trans_id: int, amount: str,
         merchant_prepare_id: int | None = None, secret: str = SECRET) -> str:
    parts = [str(click_trans_id), str(SERVICE_ID), secret, str(merchant_trans_id)]
    if action == ACTION_COMPLETE:
        parts.append(str(merchant_prepare_id))
    parts += [amount, str(action), SIGN_TIME]
    return hashlib.md5("".join(parts).encode("utf-8")).hexdigest()


def form(action: int, *, click_trans_id: int, merchant_trans_id: int, amount: str,
         merchant_prepare_id: int | None = None, error: int = 0,
         sign_string: str | None = None) -> dict[str, str]:
    fields = {
        "click_trans_id": str(click_trans_id),
        "service_id": str(SERVICE_ID),
        "click_paydoc_id": "9001",
        "merchant_trans_id": str(merchant_trans_id),
        "amount": amount,
        "action": str(action),
        "error": str(error),
        "error_note": "Success",
        "sign_time": SIGN_TIME,
        "sign_string": sign_string if sign_string is not None else sign(
            action, click_trans_id=click_trans_id, merchant_trans_id=merchant_trans_id,
            amount=amount, merchant_prepare_id=merchant_prepare_id),
    }
    if merchant_prepare_id is not None:
        fields["merchant_prepare_id"] = str(merchant_prepare_id)
    return fields


@pytest.fixture(scope="module")
def local_postgres(tmp_path_factory):
    pgembed = pytest.importorskip("pgembed", reason="Install requirements-dev.txt for real PostgreSQL tests")
    server = pgembed.get_server(tmp_path_factory.mktemp("click-pg"), cleanup_mode="delete")
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
    monkeypatch.setattr(api, "AsyncSessionLocal", factory)
    monkeypatch.setattr(config, "click_service_id", SERVICE_ID)
    monkeypatch.setattr(config, "click_merchant_id", MERCHANT_ID)
    monkeypatch.setattr(config, "click_secret_key", SECRET)
    monkeypatch.setattr(config, "channel_id", -1001)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    app = web.Application(client_max_size=64 * 1024)
    api.register_routes(app, AsyncMock())
    async with TestClient(TestServer(app)) as test_client:
        yield test_client


async def seed_order(db, *, order_id: int, amount: int = TARIFF_PRICE,
                     method: str = METHOD_CLICK, months: int = TARIFF_MONTHS,
                     status: str = "pending") -> int:
    async with db() as session:
        if await session.get(User, USER_ID) is None:
            session.add(User(telegram_id=USER_ID, balance=0, language="ru"))
            await session.flush()
        session.add(Payment(id=order_id, user_id=USER_ID, amount=amount, tariff_months=months,
                            status=status, payment_method=method))
        await session.commit()
    return order_id


async def call(client, action: int, fields: dict[str, str]) -> dict:
    path = api.CLICK_PREPARE_PATH if action == ACTION_PREPARE else api.CLICK_COMPLETE_PATH
    response = await client.post(path, data=fields)
    assert response.status == 200
    return await response.json()


# --------------------------------------------------------------- transport


def test_pay_url_matches_the_click_checkout_contract():
    assert protocol.build_pay_url(service_id=SERVICE_ID, merchant_id=MERCHANT_ID,
                                  amount=500_000, order_id=42) == (
        "https://my.click.uz/services/pay?service_id=111815&merchant_id=64579"
        "&amount=500000.00&transaction_param=42")


@pytest.mark.parametrize("order_id", ["42", "tariff_1", 0, -1, True, None])
def test_pay_url_refuses_anything_but_a_positive_int_order_id(order_id):
    with pytest.raises(ValueError):
        protocol.build_pay_url(service_id=SERVICE_ID, merchant_id=MERCHANT_ID,
                               amount=500_000, order_id=order_id)


@pytest.mark.parametrize("amount", ["500000", 500_000.0, 0, -1])
def test_pay_url_refuses_a_non_integer_or_non_positive_amount(amount):
    with pytest.raises(ValueError):
        protocol.build_pay_url(service_id=SERVICE_ID, merchant_id=MERCHANT_ID,
                               amount=amount, order_id=42)


def test_link_prepare_and_complete_quote_the_same_amount_string():
    url = protocol.build_pay_url(service_id=SERVICE_ID, merchant_id=MERCHANT_ID,
                                 amount=TARIFF_PRICE, order_id=42)
    quoted = url.split("amount=")[1].split("&")[0]
    assert protocol.to_tiyin(quoted) == protocol.sum_to_tiyin(TARIFF_PRICE) == 50_000_000


@pytest.mark.asyncio
async def test_bad_signature_is_rejected(client, db):
    await seed_order(db, order_id=201)
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=1, merchant_trans_id=201, amount="500000.00",
        sign_string="0" * 32))
    assert body["error"] == errors.SIGN_CHECK_FAILED
    async with db() as session:
        assert await session.scalar(select(ClickTransaction)) is None


@pytest.mark.asyncio
async def test_signature_from_another_secret_is_rejected(client, db):
    await seed_order(db, order_id=202)
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=2, merchant_trans_id=202, amount="500000.00",
        sign_string=sign(ACTION_PREPARE, click_trans_id=2, merchant_trans_id=202,
                         amount="500000.00", secret="not-the-secret")))
    assert body["error"] == errors.SIGN_CHECK_FAILED


@pytest.mark.asyncio
async def test_missing_fields_are_rejected(client, db):
    body = await call(client, ACTION_PREPARE, {"click_trans_id": "3"})
    assert body["error"] == errors.BAD_REQUEST


@pytest.mark.asyncio
async def test_complete_action_on_the_prepare_endpoint_is_rejected(client, db):
    await seed_order(db, order_id=203)
    body = await call(client, ACTION_PREPARE, form(
        ACTION_COMPLETE, click_trans_id=4, merchant_trans_id=203, amount="500000.00",
        merchant_prepare_id=1))
    assert body["error"] == errors.ACTION_NOT_FOUND


# ----------------------------------------------------------------- prepare


@pytest.mark.asyncio
async def test_unknown_order_is_rejected(client, db):
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=5, merchant_trans_id=999, amount="500000.00"))
    assert body["error"] == errors.ORDER_NOT_FOUND


@pytest.mark.asyncio
async def test_order_of_another_payment_method_is_invisible(client, db):
    await seed_order(db, order_id=204, method="manual_card")
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=6, merchant_trans_id=204, amount="500000.00"))
    assert body["error"] == errors.ORDER_NOT_FOUND


@pytest.mark.asyncio
async def test_wrong_amount_is_rejected(client, db):
    await seed_order(db, order_id=205)
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=7, merchant_trans_id=205, amount="1.00"))
    assert body["error"] == errors.INCORRECT_AMOUNT


@pytest.mark.asyncio
async def test_prepare_refuses_an_order_that_no_longer_prices_its_tariff(client, db):
    # Order edited after minting (e.g. "UPDATE payments SET amount=1000"): the
    # checkout link and Prepare agree on 1000, but the tariff costs 500000.
    await seed_order(db, order_id=230, amount=1_000)
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=30, merchant_trans_id=230, amount="1000.00"))
    assert body["error"] == errors.INCORRECT_AMOUNT
    assert "merchant_prepare_id" not in body
    async with db() as session:
        assert await session.scalar(select(ClickTransaction)) is None
        assert (await session.get(Payment, 230)).status == "pending"


@pytest.mark.asyncio
async def test_prepare_accepts_an_order_partly_covered_by_cashback(client, db):
    async with db() as session:
        session.add(User(telegram_id=USER_ID, balance=100_000, language="ru"))
        session.add(Payment(id=231, user_id=USER_ID, amount=400_000, tariff_months=1,
                            status="pending", payment_method=METHOD_CLICK, cashback_applied=100_000))
        await session.commit()
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=31, merchant_trans_id=231, amount="400000.00"))
    assert body["error"] == errors.SUCCESS


@pytest.mark.asyncio
async def test_prepare_reserves_the_order_and_is_idempotent(client, db):
    await seed_order(db, order_id=206)
    fields = form(ACTION_PREPARE, click_trans_id=8, merchant_trans_id=206, amount="500000.00")
    first = await call(client, ACTION_PREPARE, fields)
    assert first["error"] == errors.SUCCESS
    assert first["merchant_trans_id"] == 206
    assert first["click_trans_id"] == 8
    repeated = await call(client, ACTION_PREPARE, fields)
    assert repeated == first
    async with db() as session:
        transaction = await session.scalar(select(ClickTransaction))
        assert transaction.state == STATE_PREPARED
        assert transaction.id == first["merchant_prepare_id"]
        assert transaction.amount == 500_000 * 100


@pytest.mark.asyncio
async def test_second_transaction_cannot_reserve_a_busy_order(client, db):
    await seed_order(db, order_id=207)
    await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=9, merchant_trans_id=207, amount="500000.00"))
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=10, merchant_trans_id=207, amount="500000.00"))
    assert body["error"] == errors.ALREADY_PAID


@pytest.mark.asyncio
async def test_prepare_on_a_paid_order_is_rejected(client, db):
    await seed_order(db, order_id=208, status="completed")
    body = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=11, merchant_trans_id=208, amount="500000.00"))
    assert body["error"] == errors.ALREADY_PAID


# ---------------------------------------------------------------- complete


@pytest.mark.asyncio
async def test_complete_grants_the_subscription_exactly_once(client, db):
    await seed_order(db, order_id=209)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=12, merchant_trans_id=209, amount="500000.00"))
    confirm = form(ACTION_COMPLETE, click_trans_id=12, merchant_trans_id=209,
                   amount="500000.00", merchant_prepare_id=prepared["merchant_prepare_id"])
    body = await call(client, ACTION_COMPLETE, confirm)
    assert body["error"] == errors.SUCCESS
    assert body["merchant_confirm_id"] == prepared["merchant_prepare_id"]

    repeated = await call(client, ACTION_COMPLETE, confirm)
    assert repeated == body
    async with db() as session:
        payment = await session.get(Payment, 209)
        assert payment.status == "completed"
        transaction = await session.scalar(select(ClickTransaction))
        assert transaction.state == STATE_CONFIRMED
        subscriptions = (await session.scalars(
            select(Subscription).where(Subscription.user_id == USER_ID))).all()
        assert len(subscriptions) == 1
        assert subscriptions[0].tariff_months == TARIFF_MONTHS


@pytest.mark.asyncio
async def test_complete_cancels_an_order_edited_after_prepare(client, db):
    await seed_order(db, order_id=232)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=32, merchant_trans_id=232, amount="500000.00"))
    async with db() as session:
        (await session.get(Payment, 232)).tariff_months = 6  # now worth 2 300 000
        await session.commit()
    confirm = form(ACTION_COMPLETE, click_trans_id=32, merchant_trans_id=232,
                   amount="500000.00", merchant_prepare_id=prepared["merchant_prepare_id"])
    body = await call(client, ACTION_COMPLETE, confirm)
    assert body["error"] == errors.INCORRECT_AMOUNT
    assert "merchant_confirm_id" not in body
    async with db() as session:
        assert (await session.get(Payment, 232)).status == "failed"
        transaction = await session.scalar(select(ClickTransaction))
        assert transaction.state == STATE_CANCELLED
        assert transaction.cancel_reason == protocol.CANCEL_REASON_REJECTED
        assert (await session.scalars(
            select(Subscription).where(Subscription.user_id == USER_ID))).all() == []
    # Click retrying the same Complete now gets a final answer, not -7 forever.
    retried = await call(client, ACTION_COMPLETE, confirm)
    assert retried["error"] == errors.TRANSACTION_CANCELLED


@pytest.mark.asyncio
async def test_policy_rejection_inside_the_money_commit_is_final(client, db, monkeypatch):
    # Defence in depth: even if the pre-check is bypassed, a rejection raised by
    # process_successful_payment releases the order instead of freezing it.
    from bot.services.click import service
    from bot.services.payment_policy import PaymentValidationError

    await seed_order(db, order_id=233)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=33, merchant_trans_id=233, amount="500000.00"))

    async def refuse(payment_id, session, bot):
        await session.rollback()
        raise PaymentValidationError("Payment amount does not match its tariff")

    monkeypatch.setattr(service, "process_successful_payment", refuse)
    body = await call(client, ACTION_COMPLETE, form(
        ACTION_COMPLETE, click_trans_id=33, merchant_trans_id=233, amount="500000.00",
        merchant_prepare_id=prepared["merchant_prepare_id"]))
    assert body["error"] == errors.INCORRECT_AMOUNT
    async with db() as session:
        assert (await session.get(Payment, 233)).status == "failed"
        transaction = await session.scalar(select(ClickTransaction))
        assert transaction.state == STATE_CANCELLED
        assert transaction.cancel_reason == protocol.CANCEL_REASON_REJECTED


@pytest.mark.asyncio
async def test_complete_without_a_prepared_transaction_is_rejected(client, db):
    await seed_order(db, order_id=210)
    body = await call(client, ACTION_COMPLETE, form(
        ACTION_COMPLETE, click_trans_id=13, merchant_trans_id=210, amount="500000.00",
        merchant_prepare_id=1))
    assert body["error"] == errors.TRANSACTION_NOT_FOUND


@pytest.mark.asyncio
async def test_complete_with_a_foreign_prepare_id_is_rejected(client, db):
    await seed_order(db, order_id=211)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=14, merchant_trans_id=211, amount="500000.00"))
    body = await call(client, ACTION_COMPLETE, form(
        ACTION_COMPLETE, click_trans_id=14, merchant_trans_id=211, amount="500000.00",
        merchant_prepare_id=prepared["merchant_prepare_id"] + 1000))
    assert body["error"] == errors.TRANSACTION_NOT_FOUND
    async with db() as session:
        assert (await session.get(Payment, 211)).status == "pending"


@pytest.mark.asyncio
async def test_complete_with_a_changed_amount_is_rejected(client, db):
    await seed_order(db, order_id=212)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=15, merchant_trans_id=212, amount="500000.00"))
    body = await call(client, ACTION_COMPLETE, form(
        ACTION_COMPLETE, click_trans_id=15, merchant_trans_id=212, amount="1.00",
        merchant_prepare_id=prepared["merchant_prepare_id"]))
    assert body["error"] == errors.INCORRECT_AMOUNT
    async with db() as session:
        assert (await session.get(Payment, 212)).status == "pending"


@pytest.mark.asyncio
async def test_click_reported_failure_cancels_the_transaction(client, db):
    await seed_order(db, order_id=213)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=16, merchant_trans_id=213, amount="500000.00"))
    body = await call(client, ACTION_COMPLETE, form(
        ACTION_COMPLETE, click_trans_id=16, merchant_trans_id=213, amount="500000.00",
        merchant_prepare_id=prepared["merchant_prepare_id"], error=-5017))
    assert body["error"] == errors.TRANSACTION_CANCELLED
    async with db() as session:
        assert (await session.get(Payment, 213)).status == "failed"
        transaction = await session.scalar(select(ClickTransaction))
        assert transaction.state == STATE_CANCELLED
        assert transaction.cancel_reason == -5017
        assert (await session.scalars(
            select(Subscription).where(Subscription.user_id == USER_ID))).all() == []


@pytest.mark.asyncio
async def test_cancelled_transaction_cannot_be_confirmed_later(client, db):
    await seed_order(db, order_id=214)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=17, merchant_trans_id=214, amount="500000.00"))
    confirm = form(ACTION_COMPLETE, click_trans_id=17, merchant_trans_id=214,
                   amount="500000.00", merchant_prepare_id=prepared["merchant_prepare_id"])
    await call(client, ACTION_COMPLETE, {**confirm, "error": "-9"})
    body = await call(client, ACTION_COMPLETE, confirm)
    assert body["error"] == errors.TRANSACTION_CANCELLED
    async with db() as session:
        assert (await session.get(Payment, 214)).status == "failed"


@pytest.mark.asyncio
async def test_concurrent_complete_commits_one_subscription_and_delivery(client, db):
    import asyncio
    from sqlalchemy import func
    from bot.database.models import PaymentDelivery
    await seed_order(db, order_id=240)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=40, merchant_trans_id=240, amount='500000.00'))
    confirm = form(ACTION_COMPLETE, click_trans_id=40, merchant_trans_id=240,
                   amount='500000.00', merchant_prepare_id=prepared['merchant_prepare_id'])
    results = await asyncio.gather(*(call(client, ACTION_COMPLETE, confirm) for _ in range(12)))
    assert all(item == results[0] for item in results)
    assert results[0]['error'] == errors.SUCCESS
    async with db() as session:
        assert await session.scalar(select(func.count()).select_from(Subscription)) == 1
        assert await session.scalar(select(func.count()).select_from(PaymentDelivery)) == 1


@pytest.mark.asyncio
async def test_prepare_retry_cannot_change_order(client, db):
    await seed_order(db, order_id=241)
    await seed_order(db, order_id=242)
    await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=41, merchant_trans_id=241, amount='500000.00'))
    result = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=41, merchant_trans_id=242, amount='500000.00'))
    assert result['error'] == errors.TRANSACTION_NOT_FOUND


@pytest.mark.asyncio
async def test_prepare_refuses_expired_order_before_scheduler_runs(client, db):
    await seed_order(db, order_id=243)
    async with db() as session:
        (await session.get(Payment, 243)).created_at = dt.datetime.now(UTC)-dt.timedelta(days=2)
        await session.commit()
    result = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=43, merchant_trans_id=243, amount='500000.00'))
    assert result['error'] == errors.TRANSACTION_CANCELLED


@pytest.mark.asyncio
async def test_complete_rollback_restores_gateway_state_and_money(client, db):
    from sqlalchemy import event
    from bot.database.models import PaymentDelivery
    await seed_order(db, order_id=244)
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=44, merchant_trans_id=244, amount='500000.00'))
    confirm = form(ACTION_COMPLETE, click_trans_id=44, merchant_trans_id=244,
                   amount='500000.00', merchant_prepare_id=prepared['merchant_prepare_id'])
    def fail(*args):
        raise RuntimeError('injected outbox insert failure')
    event.listen(PaymentDelivery, 'before_insert', fail)
    try:
        result = await call(client, ACTION_COMPLETE, confirm)
    finally:
        event.remove(PaymentDelivery, 'before_insert', fail)
    assert result['error'] == errors.UPDATE_FAILED
    async with db() as session:
        assert (await session.get(Payment, 244)).status == 'pending'
        assert (await session.scalar(select(ClickTransaction))).state == STATE_PREPARED
        assert await session.scalar(select(Subscription)) is None
        assert await session.scalar(select(PaymentDelivery)) is None
    assert (await call(client, ACTION_COMPLETE, confirm))['error'] == errors.SUCCESS


@pytest.mark.parametrize('amount', ['NaN', 'sNaN', 'Infinity', '1e99999999', '9'*128, '1.001'])
def test_nonfinite_or_oversized_amount_is_not_an_exception(amount):
    assert protocol.to_tiyin(amount) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('transaction', ['9'*5000, '²', '--12'])
async def test_malformed_unsigned_id_still_returns_protocol_error(client, transaction):
    response = await client.post(api.CLICK_PREPARE_PATH, data={
        'click_trans_id': transaction, 'merchant_trans_id': transaction})
    assert response.status == 200
    assert (await response.json())['error'] == errors.BAD_REQUEST


@pytest.mark.asyncio
async def test_complete_rejects_changed_cashback_terms_even_if_tariff_still_matches(client, db):
    async with db() as session:
        session.add(User(telegram_id=USER_ID, balance=100_000, language='uz'))
        await session.flush()
        session.add(Payment(id=245, user_id=USER_ID, amount=400_000, cashback_applied=100_000,
                            tariff_months=1, status='pending', payment_method=METHOD_CLICK))
        await session.commit()
    prepared = await call(client, ACTION_PREPARE, form(
        ACTION_PREPARE, click_trans_id=45, merchant_trans_id=245, amount='400000.00'))
    async with db() as session:
        order = await session.get(Payment, 245)
        order.amount = 500_000
        order.cashback_applied = 0
        await session.commit()
    result = await call(client, ACTION_COMPLETE, form(
        ACTION_COMPLETE, click_trans_id=45, merchant_trans_id=245, amount='400000.00',
        merchant_prepare_id=prepared['merchant_prepare_id']))
    assert result['error'] == errors.INCORRECT_AMOUNT
    async with db() as session:
        assert await session.scalar(select(Subscription)) is None
        assert (await session.get(User, USER_ID)).balance == 100_000
