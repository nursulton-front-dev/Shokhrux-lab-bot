"""Checkout buttons on the tariff card and on renewal reminders."""
from unittest.mock import AsyncMock

import pytest

from bot.config import config
from bot.services.payment_menu import CLICK_LABEL, PAYME_LABEL, gateway_buttons


@pytest.fixture
def both_merchants(monkeypatch):
    monkeypatch.setattr(config, "payme_merchant_id", "merchant-1")
    monkeypatch.setattr(config, "payme_test_key", "test-key")
    monkeypatch.setattr(config, "payme_sandbox", True)
    monkeypatch.setattr(config, "click_service_id", 111815)
    monkeypatch.setattr(config, "click_merchant_id", 64579)
    monkeypatch.setattr(config, "click_secret_key", "click-secret")


def test_gateway_buttons_target_the_existing_checkout_handlers(both_merchants):
    buttons = gateway_buttons(3, use_cashback=False)
    assert [b.text for b in buttons] == [PAYME_LABEL, CLICK_LABEL]
    assert [b.callback_data for b in buttons] == ["pay_payme_3_0", "pay_click_3_0"]


def test_gateway_buttons_encode_the_cashback_choice(both_merchants):
    buttons = gateway_buttons(6, use_cashback=True)
    assert [b.callback_data for b in buttons] == ["pay_payme_6_1", "pay_click_6_1"]


def test_unconfigured_merchant_is_not_offered(both_merchants, monkeypatch):
    monkeypatch.setattr(config, "click_secret_key", None)
    buttons = gateway_buttons(1, use_cashback=False)
    assert [b.callback_data for b in buttons] == ["pay_payme_1_0"]


def test_no_merchant_configured_yields_no_buttons(monkeypatch):
    for field in ("payme_merchant_id", "payme_test_key", "payme_prod_key",
                  "click_service_id", "click_merchant_id", "click_secret_key"):
        monkeypatch.setattr(config, field, None)
    assert gateway_buttons(1, use_cashback=False) == []


@pytest.mark.asyncio
async def test_tariff_card_carries_checkout_for_every_tariff(both_merchants, monkeypatch):
    from bot.handlers import user as user_handlers

    # No banner file in the test environment, so the text branch is exercised.
    monkeypatch.setattr(user_handlers.config, "tariffs_img_ru", "/nonexistent/banner.jpg")
    message = AsyncMock()
    await user_handlers.show_tariffs(message, "ru", cashback_balance=0)

    markup = message.answer.await_args.kwargs["reply_markup"]
    rows = markup.inline_keyboard
    assert len(rows) == 3, "one row per tariff keeps the menu on a single screen"
    for row, months in zip(rows, ("1", "3", "6")):
        assert row[0].callback_data == f"tariff_{months}"
        assert [b.callback_data for b in row[1:]] == [f"pay_payme_{months}_0", f"pay_click_{months}_0"]


@pytest.mark.asyncio
async def test_tariff_card_spends_cashback_when_the_payer_has_some(both_merchants, monkeypatch):
    from bot.handlers import user as user_handlers

    monkeypatch.setattr(user_handlers.config, "tariffs_img_ru", "/nonexistent/banner.jpg")
    message = AsyncMock()
    await user_handlers.show_tariffs(message, "ru", cashback_balance=30_000)

    rows = message.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert [b.callback_data for b in rows[0][1:]] == ["pay_payme_1_1", "pay_click_1_1"]


def test_renewal_reminder_offers_the_same_tariff_and_a_fallback(both_merchants):
    from bot.services.scheduler import _renewal_keyboard

    rows = _renewal_keyboard(6, "ru", cashback_balance=0).inline_keyboard
    assert [b.callback_data for b in rows[0]] == ["pay_payme_6_0", "pay_click_6_0"]
    assert rows[-1][0].callback_data == "start_sub"


def test_renewal_reminder_without_merchants_still_offers_the_tariff_menu(monkeypatch):
    from bot.services.scheduler import _renewal_keyboard

    for field in ("payme_merchant_id", "payme_test_key", "payme_prod_key",
                  "click_service_id", "click_merchant_id", "click_secret_key"):
        monkeypatch.setattr(config, field, None)
    rows = _renewal_keyboard(1, "uz", cashback_balance=0).inline_keyboard
    assert len(rows) == 1
    assert rows[0][0].callback_data == "start_sub"
