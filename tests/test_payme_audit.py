"""Payme Merchant API over real HTTP and real PostgreSQL; no external calls."""
import asyncio
import base64
import datetime as dt
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import config
from bot.database.models import Base, Payment, PaymeTransaction, Subscription, User
from bot.services.payme import api, errors, service
from bot.services.payme.protocol import (
    METHOD_PAYME,
    METHOD_PAYME_SANDBOX,
    STATE_CANCELLED,
    STATE_CANCELLED_AFTER_PERFORM,
    STATE_CREATED,
    STATE_PERFORMED,
    TRANSACTION_TIMEOUT_MS,
    now_ms,
)

UTC = dt.timezone.utc
TEST_KEY = "test-key-value"
MERCHANT_ID = "merchant-1"
USER_ID = 42
SANDBOX_AMOUNT = 150_000
REAL_TARIFF_MONTHS = 1
REAL_TARIFF_PRICE = 500_000


def auth_header(key: str = TEST_KEY, login: str = "Paycom") -> dict[str, str]:
    token = base64.b64encode(f"{login}:{key}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_checkout_url_carries_the_order_and_its_amount_in_tiyin():
    from bot.services.payme.protocol import build_checkout_url

    url = build_checkout_url(merchant_id=MERCHANT_ID, order_id=12345, amount_uzs=REAL_TARIFF_PRICE)
    prefix, _, blob = url.rpartition("/")
    assert prefix == "https://checkout.paycom.uz"
    assert base64.b64decode(blob).decode() == (
        f"m={MERCHANT_ID};ac.{errors.ACCOUNT_FIELD}=12345;a={REAL_TARIFF_PRICE * 100}")


@pytest.fixture(scope="module")
def local_postgres(tmp_path_factory):
    pgembed = pytest.importorskip("pgembed", reason="Install requirements-dev.txt for real PostgreSQL tests")
    server = pgembed.get_server(tmp_path_factory.mktemp("payme-pg"), cleanup_mode="delete")
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
    monkeypatch.setattr(config, "payme_merchant_id", MERCHANT_ID)
    monkeypatch.setattr(config, "payme_test_key", TEST_KEY)
    monkeypatch.setattr(config, "payme_sandbox", True)
    monkeypatch.setattr(config, "channel_id", -1001)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    server = TestServer(api.create_app(AsyncMock()))
    async with TestClient(server) as test_client:
        yield test_client


async def seed_order(db, *, order_id: int, amount: int, method: str = METHOD_PAYME_SANDBOX,
                     months: int = 0, status: str = "pending") -> int:
    async with db() as session:
        if await session.get(User, USER_ID) is None:
            session.add(User(telegram_id=USER_ID, balance=0, language="ru"))
            await session.flush()
        session.add(Payment(id=order_id, user_id=USER_ID, amount=amount, tariff_months=months,
                            status=status, payment_method=method))
        await session.commit()
    return order_id


async def call(client, method: str, params: dict, *, headers: dict | None = None,
               request_id: int = 1) -> dict:
    response = await client.post(
        api.PAYME_PATH,
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        headers=auth_header() if headers is None else headers,
    )
    assert response.status == 200
    return await response.json()


@pytest.mark.asyncio
async def test_missing_authorization_is_rejected(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    body = await call(client, "CheckPerformTransaction",
                      {"amount": SANDBOX_AMOUNT * 100, "account": {"order_id": 101}}, headers={})
    assert body["error"]["code"] == errors.INSUFFICIENT_PRIVILEGE


@pytest.mark.asyncio
async def test_wrong_key_is_rejected(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    body = await call(client, "CheckPerformTransaction",
                      {"amount": SANDBOX_AMOUNT * 100, "account": {"order_id": 101}},
                      headers=auth_header(key="wrong-key"))
    assert body["error"]["code"] == errors.INSUFFICIENT_PRIVILEGE


@pytest.mark.asyncio
async def test_production_key_cannot_authenticate_in_sandbox(client, db, monkeypatch):
    monkeypatch.setattr(config, "payme_prod_key", "production-key")
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    body = await call(client, "CheckPerformTransaction",
                      {"amount": SANDBOX_AMOUNT * 100, "account": {"order_id": 101}},
                      headers=auth_header(key="production-key"))
    assert body["error"]["code"] == errors.INSUFFICIENT_PRIVILEGE


@pytest.mark.asyncio
async def test_merchant_id_is_accepted_as_login(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    body = await call(client, "CheckPerformTransaction",
                      {"amount": SANDBOX_AMOUNT * 100, "account": {"order_id": 101}},
                      headers=auth_header(login=MERCHANT_ID))
    assert body["result"] == {"allow": True}


@pytest.mark.asyncio
async def test_unknown_method_reports_method_not_found(client, db):
    body = await call(client, "MakeMeRich", {})
    assert body["error"]["code"] == errors.METHOD_NOT_FOUND


@pytest.mark.asyncio
async def test_malformed_json_reports_parse_error(client, db):
    response = await client.post(api.PAYME_PATH, data=b"{not json", headers=auth_header())
    assert response.status == 200
    assert (await response.json())["error"]["code"] == errors.PARSE_ERROR


@pytest.mark.asyncio
async def test_check_perform_rejects_unknown_order(client, db):
    body = await call(client, "CheckPerformTransaction",
                      {"amount": SANDBOX_AMOUNT * 100, "account": {"order_id": 999}})
    assert body["error"]["code"] == errors.ORDER_NOT_FOUND
    assert body["error"]["data"] == "order_id"


@pytest.mark.asyncio
async def test_check_perform_rejects_missing_account_field(client, db):
    body = await call(client, "CheckPerformTransaction", {"amount": 100, "account": {"id": 101}})
    assert body["error"]["code"] == errors.ORDER_NOT_FOUND


@pytest.mark.asyncio
async def test_check_perform_rejects_wrong_amount(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    body = await call(client, "CheckPerformTransaction",
                      {"amount": 999, "account": {"order_id": 101}})
    assert body["error"]["code"] == errors.WRONG_AMOUNT


@pytest.mark.asyncio
async def test_check_perform_rejects_already_paid_order(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT, status="completed")
    body = await call(client, "CheckPerformTransaction",
                      {"amount": SANDBOX_AMOUNT * 100, "account": {"order_id": 101}})
    assert body["error"]["code"] == errors.UNABLE_TO_PERFORM


@pytest.mark.asyncio
async def test_sandbox_order_is_invisible_in_production_mode(client, db, monkeypatch):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    monkeypatch.setattr(config, "payme_sandbox", False)
    monkeypatch.setattr(config, "payme_prod_key", TEST_KEY)
    body = await call(client, "CheckPerformTransaction",
                      {"amount": SANDBOX_AMOUNT * 100, "account": {"order_id": 101}})
    assert body["error"]["code"] == errors.ORDER_NOT_FOUND


@pytest.mark.asyncio
async def test_create_transaction_is_idempotent(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    params = {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
              "account": {"order_id": 101}}
    first = await call(client, "CreateTransaction", params)
    second = await call(client, "CreateTransaction", params)
    assert first["result"]["state"] == STATE_CREATED
    assert first["result"] == second["result"]
    async with db() as session:
        assert await session.scalar(select(func.count()).select_from(PaymeTransaction)) == 1


@pytest.mark.asyncio
async def test_second_transaction_for_same_order_is_refused(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    amount = SANDBOX_AMOUNT * 100
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": amount, "account": {"order_id": 101}})
    body = await call(client, "CreateTransaction",
                      {"id": "tx-2", "time": now_ms(), "amount": amount, "account": {"order_id": 101}})
    assert body["error"]["code"] == errors.UNABLE_TO_PERFORM
    # The refusal must come from the duplicate-order guard, not a crash that
    # the catch-all handler reported with the same code.
    assert body["error"]["data"] == "order 101 is already being paid"


@pytest.mark.asyncio
async def test_concurrent_creates_produce_one_transaction(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    amount = SANDBOX_AMOUNT * 100
    bodies = await asyncio.gather(*(
        call(client, "CreateTransaction",
             {"id": f"tx-{index}", "time": now_ms(), "amount": amount, "account": {"order_id": 101}})
        for index in range(10)
    ))
    assert sum("result" in body for body in bodies) == 1
    assert all(body["error"]["data"] == "order 101 is already being paid"
               for body in bodies if "error" in body)
    async with db() as session:
        live = await session.scalar(select(func.count()).select_from(PaymeTransaction).where(
            PaymeTransaction.state.in_((STATE_CREATED, STATE_PERFORMED))))
    assert live == 1


@pytest.mark.asyncio
async def test_expired_transaction_is_cancelled_on_create(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    stale = now_ms() - TRANSACTION_TIMEOUT_MS - 1000
    params = {"id": "tx-1", "time": stale, "amount": SANDBOX_AMOUNT * 100,
              "account": {"order_id": 101}}
    await call(client, "CreateTransaction", params)
    body = await call(client, "CreateTransaction", params)
    assert body["error"]["code"] == errors.UNABLE_TO_PERFORM
    async with db() as session:
        transaction = await session.scalar(select(PaymeTransaction))
        assert transaction.state == STATE_CANCELLED
        assert transaction.reason == 4
        assert (await session.get(Payment, 101)).status == "failed"


@pytest.mark.asyncio
async def test_perform_marks_sandbox_order_paid_without_subscription(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    body = await call(client, "PerformTransaction", {"id": "tx-1"})
    assert body["result"]["state"] == STATE_PERFORMED
    assert body["result"]["perform_time"] > 0
    async with db() as session:
        assert (await session.get(Payment, 101)).status == "completed"
        assert await session.scalar(select(func.count()).select_from(Subscription)) == 0


@pytest.mark.asyncio
async def test_perform_is_idempotent(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    results = await asyncio.gather(*(call(client, "PerformTransaction", {"id": "tx-1"})
                                     for _ in range(10)))
    performed = [body["result"] for body in results if "result" in body]
    assert performed and all(item == performed[0] for item in performed)


@pytest.mark.asyncio
async def test_perform_rejects_unknown_transaction(client, db):
    body = await call(client, "PerformTransaction", {"id": "nope"})
    assert body["error"]["code"] == errors.TRANSACTION_NOT_FOUND


@pytest.mark.asyncio
async def test_real_order_grants_subscription_once(client, db):
    await seed_order(db, order_id=201, amount=REAL_TARIFF_PRICE, method=METHOD_PAYME,
                     months=REAL_TARIFF_MONTHS)
    await call(client, "CreateTransaction",
               {"id": "tx-real", "time": now_ms(), "amount": REAL_TARIFF_PRICE * 100,
                "account": {"order_id": 201}})
    results = await asyncio.gather(*(call(client, "PerformTransaction", {"id": "tx-real"})
                                     for _ in range(10)))
    assert all("result" in body for body in results)
    async with db() as session:
        assert await session.scalar(select(func.count()).select_from(Subscription)) == 1
        assert (await session.get(Payment, 201)).status == "completed"


@pytest.mark.asyncio
async def test_performed_real_order_cannot_be_cancelled(client, db):
    await seed_order(db, order_id=201, amount=REAL_TARIFF_PRICE, method=METHOD_PAYME,
                     months=REAL_TARIFF_MONTHS)
    await call(client, "CreateTransaction",
               {"id": "tx-real", "time": now_ms(), "amount": REAL_TARIFF_PRICE * 100,
                "account": {"order_id": 201}})
    await call(client, "PerformTransaction", {"id": "tx-real"})
    body = await call(client, "CancelTransaction", {"id": "tx-real", "reason": 5})
    assert body["error"]["code"] == errors.CANNOT_CANCEL_PERFORMED


@pytest.mark.asyncio
async def test_cancel_created_transaction_releases_order(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    body = await call(client, "CancelTransaction", {"id": "tx-1", "reason": 1})
    assert body["result"]["state"] == STATE_CANCELLED
    assert body["result"]["cancel_time"] > 0
    repeated = await call(client, "CancelTransaction", {"id": "tx-1", "reason": 1})
    assert repeated["result"] == body["result"]
    async with db() as session:
        assert (await session.get(Payment, 101)).status == "failed"


@pytest.mark.asyncio
async def test_cancel_performed_sandbox_order_reverts_it(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    await call(client, "PerformTransaction", {"id": "tx-1"})
    body = await call(client, "CancelTransaction", {"id": "tx-1", "reason": 5})
    assert body["result"]["state"] == STATE_CANCELLED_AFTER_PERFORM
    async with db() as session:
        assert (await session.get(Payment, 101)).status == "failed"


@pytest.mark.asyncio
async def test_cancelled_transaction_cannot_be_performed(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    await call(client, "CancelTransaction", {"id": "tx-1", "reason": 1})
    body = await call(client, "PerformTransaction", {"id": "tx-1"})
    assert body["error"]["code"] == errors.UNABLE_TO_PERFORM


@pytest.mark.asyncio
async def test_check_transaction_reports_full_lifecycle(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    created = (await call(client, "CheckTransaction", {"id": "tx-1"}))["result"]
    assert created["state"] == STATE_CREATED
    assert created["perform_time"] == 0 and created["cancel_time"] == 0
    assert created["reason"] is None
    await call(client, "PerformTransaction", {"id": "tx-1"})
    performed = (await call(client, "CheckTransaction", {"id": "tx-1"}))["result"]
    assert performed["state"] == STATE_PERFORMED and performed["perform_time"] > 0


@pytest.mark.asyncio
async def test_check_transaction_rejects_unknown_id(client, db):
    body = await call(client, "CheckTransaction", {"id": "nope"})
    assert body["error"]["code"] == errors.TRANSACTION_NOT_FOUND


@pytest.mark.asyncio
async def test_get_statement_returns_window_only(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await seed_order(db, order_id=102, amount=300_000)
    inside, outside = now_ms(), now_ms() - 10 * 24 * 60 * 60 * 1000
    await call(client, "CreateTransaction",
               {"id": "tx-in", "time": inside, "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    await call(client, "CreateTransaction",
               {"id": "tx-out", "time": outside, "amount": 300_000 * 100,
                "account": {"order_id": 102}})
    body = await call(client, "GetStatement", {"from": inside - 1000, "to": inside + 1000})
    rows = body["result"]["transactions"]
    assert [row["id"] for row in rows] == ["tx-in"]
    assert rows[0]["account"] == {"order_id": "101"}
    assert rows[0]["amount"] == SANDBOX_AMOUNT * 100


@pytest.mark.asyncio
async def test_get_statement_validates_window(client, db):
    body = await call(client, "GetStatement", {"from": "yesterday", "to": now_ms()})
    assert body["error"]["code"] == errors.INVALID_PARAMS


@pytest.mark.asyncio
async def test_seeded_sandbox_orders_are_payable(client, db):
    """The two orders Payme's sandbox checklist drives against this endpoint."""
    for order_id, amount in ((101, 150_000), (102, 300_000)):
        await seed_order(db, order_id=order_id, amount=amount)
        body = await call(client, "CheckPerformTransaction",
                          {"amount": amount * 100, "account": {"order_id": order_id}})
        assert body["result"] == {"allow": True}


@pytest.mark.asyncio
async def test_perform_recovers_when_order_was_already_paid(client, db):
    """A crash between committing the money and recording it here must not
    strand the transaction: the next PerformTransaction finishes the write."""
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    async with db() as session:
        payment = await session.get(Payment, 101)
        payment.payment_method = METHOD_PAYME
        payment.status = "completed"
        await session.commit()
    body = await call(client, "PerformTransaction", {"id": "tx-1"})
    assert body["result"]["state"] == STATE_PERFORMED
    async with db() as session:
        assert (await session.get(PaymeTransaction, 1)).state == STATE_PERFORMED


@pytest.mark.asyncio
async def test_perform_refuses_when_order_was_cancelled(client, db):
    await seed_order(db, order_id=101, amount=SANDBOX_AMOUNT)
    await call(client, "CreateTransaction",
               {"id": "tx-1", "time": now_ms(), "amount": SANDBOX_AMOUNT * 100,
                "account": {"order_id": 101}})
    async with db() as session:
        payment = await session.get(Payment, 101)
        payment.payment_method = METHOD_PAYME
        payment.status = "failed"
        await session.commit()
    body = await call(client, "PerformTransaction", {"id": "tx-1"})
    assert body["error"]["code"] == errors.UNABLE_TO_PERFORM
    assert body["error"]["data"] == "order 101 is failed"
