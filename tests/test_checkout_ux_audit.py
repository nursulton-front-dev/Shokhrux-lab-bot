"""Tariff-flow UX: Payme "coming soon" stub, in-place «Orqaga», stale checkout alerts."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from bot import texts
from bot.config import config
from bot.handlers import user as handlers
from bot.services.payment_policy import PaymentValidationError

USER_ID = 501


@pytest.fixture
def merchants(monkeypatch):
    monkeypatch.setattr(config, "payme_merchant_id", "merchant-1")
    monkeypatch.setattr(config, "payme_test_key", "test-key")
    monkeypatch.setattr(config, "payme_sandbox", True)
    monkeypatch.setattr(config, "click_service_id", 111815)
    monkeypatch.setattr(config, "click_merchant_id", 64579)
    monkeypatch.setattr(config, "click_secret_key", "click-secret")


def bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message=text)


def make_message(*, photo: bool) -> MagicMock:
    """A bot message the payer tapped a button on: the tariff card is a photo."""
    # spec=Message keeps isinstance() checks honest; the API methods are declared
    # explicitly because aiogram returns awaitable method objects, not coroutines,
    # so a spec'd mock would make them synchronous.
    message = MagicMock(spec=Message)
    message.message_id = 4242
    message.chat = MagicMock(id=USER_ID)
    message.photo = [MagicMock()] if photo else None
    for name in ("answer", "answer_photo", "edit_text", "edit_caption",
                 "edit_reply_markup", "delete"):
        setattr(message, name, AsyncMock())
    return message


def make_callback(data: str, message: MagicMock) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.from_user = MagicMock(id=USER_ID)
    callback.message = message
    return callback


def session_with_user(lang: str, balance: int = 0) -> AsyncMock:
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=MagicMock(language=lang, balance=balance, telegram_id=USER_ID))
    return session


# ---------------------------------------------------------------- 1. Payme stub


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["uz", "ru"])
async def test_paused_payme_shows_the_coming_soon_alert_and_mints_nothing(merchants, monkeypatch, lang):
    monkeypatch.setattr(config, "payme_checkout_paused", True)
    intent = AsyncMock()
    monkeypatch.setattr(handlers, "create_payment_intent", intent)
    message = make_message(photo=True)
    callback = make_callback("pay_payme_1_0", message)

    await handlers.cb_pay_payme(callback, session_with_user(lang))

    callback.answer.assert_awaited_once_with(texts.PAYME_SOON_ALERT[lang], show_alert=True)
    intent.assert_not_awaited()
    message.answer.assert_not_awaited()
    message.edit_caption.assert_not_awaited()
    message.edit_text.assert_not_awaited()


def test_coming_soon_alert_fits_a_telegram_callback_answer():
    for text in texts.PAYME_SOON_ALERT.values():
        assert len(text) <= 200


@pytest.mark.asyncio
async def test_unpaused_payme_proceeds_to_mint_the_order(merchants, monkeypatch):
    monkeypatch.setattr(config, "payme_checkout_paused", False)
    order = AsyncMock(return_value=None)  # refused downstream; we only check it was consulted
    monkeypatch.setattr(handlers, "_create_gateway_order", order)
    callback = make_callback("pay_payme_3_1", make_message(photo=True))

    await handlers.cb_pay_payme(callback, session_with_user("uz"))

    order.assert_awaited_once()
    assert order.await_args.kwargs["method"] == "payme"
    assert order.await_args.kwargs["lang"] == "uz"


@pytest.mark.asyncio
async def test_payment_screen_marks_payme_as_coming_soon(merchants, monkeypatch):
    monkeypatch.setattr(config, "payme_checkout_paused", True)
    session = AsyncMock()
    user = MagicMock(language="uz", balance=0)
    session.scalar = AsyncMock(side_effect=[user, None])  # user lookup, then active subscription
    callback = make_callback("select_pay_1_0", make_message(photo=True))

    await handlers.render_payment_info(callback, "1", 0, session)

    rows = callback.message.edit_caption.await_args.kwargs["reply_markup"].inline_keyboard
    labels = [b.text for b in rows[0]]
    assert texts.CLICK_PAY_BTN["uz"] in labels
    assert f"{texts.PAYME_PAY_BTN['uz']} (Tez kunda)" in labels


# ---------------------------------------------------------------- 2. «Orqaga»


@pytest.mark.asyncio
async def test_back_redraws_the_tariff_card_in_the_same_photo_message(merchants, monkeypatch):
    message = make_message(photo=True)
    callback = make_callback("tariffs_back", message)

    await handlers.cb_tariffs_back(callback, session_with_user("uz", balance=0))

    message.edit_caption.assert_awaited_once()
    kwargs = message.edit_caption.await_args.kwargs
    assert kwargs["caption"] == handlers._tariff_card_caption("uz")
    rows = kwargs["reply_markup"].inline_keyboard
    assert [row[0].callback_data for row in rows] == ["tariff_1", "tariff_3", "tariff_6"]
    message.answer.assert_not_awaited()
    message.answer_photo.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_back_on_a_text_message_edits_its_text(merchants):
    message = make_message(photo=False)
    callback = make_callback("tariffs_back", message)

    await handlers.cb_tariffs_back(callback, session_with_user("ru"))

    message.edit_text.assert_awaited_once()
    message.edit_caption.assert_not_awaited()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_back_swallows_message_is_not_modified(merchants):
    message = make_message(photo=True)
    message.edit_caption.side_effect = bad_request("Bad Request: message is not modified")
    callback = make_callback("tariffs_back", message)

    await handlers.cb_tariffs_back(callback, session_with_user("uz"))

    message.answer.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_back_falls_back_to_a_new_message_when_the_old_one_cannot_be_edited(merchants):
    message = make_message(photo=True)
    message.edit_caption.side_effect = bad_request("Bad Request: message can't be edited")
    callback = make_callback("tariffs_back", message)

    await handlers.cb_tariffs_back(callback, session_with_user("uz"))

    message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_every_back_button_in_the_flow_edits_in_place(merchants, monkeypatch):
    """Tariff detail and cashback question point «Orqaga» at the in-place handler."""
    session = AsyncMock()
    user = MagicMock(language="uz", balance=0)
    session.scalar = AsyncMock(side_effect=[user, None])
    callback = make_callback("select_pay_1_0", make_message(photo=True))
    await handlers.render_payment_info(callback, "1", 0, session)
    rows = callback.message.edit_caption.await_args.kwargs["reply_markup"].inline_keyboard
    assert rows[-1][0].callback_data == "tariffs_back"

    session = session_with_user("uz", balance=50_000)
    callback = make_callback("tariff_3", make_message(photo=True))
    await handlers.cb_tariff_selected(callback, session)
    rows = callback.message.edit_caption.await_args.kwargs["reply_markup"].inline_keyboard
    assert rows[-1][0].callback_data == "tariffs_back"
    callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelling_a_support_ticket_does_not_resend_the_welcome(merchants):
    message = make_message(photo=False)
    callback = make_callback("cancel_ticket", message)
    state = AsyncMock()

    await handlers.cb_cancel_ticket(callback, state, session_with_user("ru"))

    state.clear.assert_awaited_once()
    message.edit_text.assert_awaited_once()
    assert message.edit_text.await_args.args[0] == texts.SUPPORT_CANCELLED["ru"]
    message.answer.assert_not_awaited()
    message.delete.assert_not_awaited()


# ---------------------------------------------------------------- 3. stale checkout


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["uz", "ru"])
async def test_stale_click_order_is_explained_in_the_payer_language(merchants, monkeypatch, lang):
    monkeypatch.setattr(handlers, "create_payment_intent",
                        AsyncMock(side_effect=PaymentValidationError("Register before paying")))
    message = make_message(photo=False)
    callback = make_callback("pay_click_1_0", message)

    await handlers.cb_pay_click(callback, session_with_user(lang))

    callback.answer.assert_awaited_once_with(texts.PAYMENT_STALE_ALERT[lang], show_alert=True)
    # The dead buttons are replaced with one that opens a fresh tariff menu.
    markup = message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert [[b.callback_data for b in row] for row in markup.inline_keyboard] == [["start_sub"]]
    assert markup.inline_keyboard[0][0].text == texts.OPEN_TARIFFS_AGAIN_BTN[lang]
    message.answer.assert_not_awaited()


def test_uzbek_stale_alert_wording():
    assert texts.PAYMENT_STALE_ALERT["uz"] == "To'lov muddati eskirgan. Iltimos, tarifni qaytadan tanlang."
    assert texts.PAYMENT_STALE_ALERT["ru"] == "Платёж устарел. Откройте тариф заново."


@pytest.mark.asyncio
@pytest.mark.parametrize("status,alert", [
    ("completed", texts.PAYMENT_ALREADY_PAID_ALERT),
    ("cancelled", texts.PAYMENT_CANCELLED_ALERT),
])
async def test_closed_orders_are_reported_and_their_buttons_retired(merchants, monkeypatch, status, alert):
    payment = MagicMock(status=status, amount=500_000)
    monkeypatch.setattr(handlers, "create_payment_intent", AsyncMock(return_value=payment))
    message = make_message(photo=True)
    callback = make_callback("pay_click_1_0", message)

    await handlers.cb_pay_click(callback, session_with_user("uz"))

    callback.answer.assert_awaited_once_with(alert["uz"], show_alert=True)
    message.edit_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_alert_on_an_inaccessible_message_does_not_crash(merchants, monkeypatch):
    """A very old message arrives as InaccessibleMessage: nothing to edit, alert still shown."""
    callback = make_callback("pay_click_1_0", MagicMock())  # not a Message
    callback.message.chat = MagicMock(id=USER_ID)

    await handlers.cb_pay_click(callback, session_with_user("ru"))

    callback.answer.assert_awaited_once_with(texts.PAYMENT_STALE_ALERT["ru"], show_alert=True)


@pytest.mark.asyncio
async def test_retiring_buttons_tolerates_message_is_not_modified(merchants, monkeypatch):
    monkeypatch.setattr(handlers, "create_payment_intent",
                        AsyncMock(side_effect=PaymentValidationError("stale")))
    message = make_message(photo=True)
    message.edit_reply_markup.side_effect = bad_request("Bad Request: message is not modified")
    callback = make_callback("pay_click_1_0", message)

    await handlers.cb_pay_click(callback, session_with_user("uz"))

    callback.answer.assert_awaited_once_with(texts.PAYMENT_STALE_ALERT["uz"], show_alert=True)


@pytest.mark.asyncio
async def test_cashback_activation_failure_is_localized_and_retires_buttons(merchants, monkeypatch):
    monkeypatch.setattr(handlers, "create_payment_intent",
                        AsyncMock(side_effect=PaymentValidationError("Insufficient cashback")))
    message = make_message(photo=True)
    callback = make_callback("pay_cashback_full_1", message)

    await handlers.cb_pay_cashback_full(callback, session_with_user("uz"), AsyncMock())

    callback.answer.assert_awaited_once_with(texts.CASHBACK_INSUFFICIENT_OR_STALE_ALERT["uz"], show_alert=True)
    message.edit_reply_markup.assert_awaited_once()
