from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

from bot import texts
from bot.config import config
from bot.handlers import user as handlers
from bot.services.click_tutorial import tutorial_video
from test_checkout_ux_audit import make_callback, make_message


@pytest.fixture
def click_config(monkeypatch):
    monkeypatch.setattr(config, 'click_service_id', 1)
    monkeypatch.setattr(config, 'click_merchant_id', 2)
    monkeypatch.setattr(config, 'click_secret_key', 'secret')
    monkeypatch.setattr(config, 'click_tutorial_video_id', None)
    monkeypatch.setattr(config, 'click_tutorial_video_path', '/missing/video.mp4')


@pytest.mark.asyncio
async def test_asset_file_id_has_priority(click_config, monkeypatch):
    monkeypatch.setattr(config, 'click_tutorial_video_id', 'telegram-video-id')
    assert await tutorial_video() == 'telegram-video-id'


@pytest.mark.asyncio
async def test_local_video_exists(click_config, monkeypatch, tmp_path):
    video = tmp_path / 'instruction.mp4'
    video.write_bytes(b'video-test-placeholder')
    monkeypatch.setattr(config, 'click_tutorial_video_path', str(video))
    assert isinstance(await tutorial_video(), FSInputFile)


@pytest.mark.asyncio
async def test_missing_video_uses_text(click_config):
    assert await tutorial_video() is None
    callback = make_callback('pay_click_1_0', make_message(photo=True))
    order = SimpleNamespace(id=42, amount=400_000, cashback_applied=100_000)
    await handlers._show_click_checkout(callback, order, 'uz')
    content = callback.message.edit_caption.await_args.kwargs['caption']
    assert texts.CLICK_CARD_INSTRUCTION['uz'] in content
    assert texts.CLICK_VIDEO_INSTRUCTION['uz'] not in content
    buttons = callback.message.edit_caption.await_args.kwargs['reply_markup'].inline_keyboard
    assert buttons[0][0].url.startswith('https://my.click.uz/')
    assert buttons[1][0].callback_data == 'click_back_42'


@pytest.mark.asyncio
async def test_video_is_sent_with_checkout_and_order_bound_back(click_config, monkeypatch):
    monkeypatch.setattr(config, 'click_tutorial_video_id', 'telegram-video-id')
    message = make_message(photo=True)
    message.answer_video = AsyncMock()
    callback = make_callback('pay_click_1_0', message)
    order = SimpleNamespace(id=42, amount=500_000, cashback_applied=0)
    await handlers._show_click_checkout(callback, order, 'uz')
    kwargs = message.answer_video.await_args.kwargs
    assert kwargs['video'] == 'telegram-video-id'
    assert texts.CLICK_CARD_INSTRUCTION['uz'] in kwargs['caption']
    assert texts.CLICK_VIDEO_INSTRUCTION['uz'] in kwargs['caption']
    assert len(kwargs['caption']) < 1024
    assert kwargs['reply_markup'].inline_keyboard[1][0].callback_data == 'click_back_42'
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_bad_video_falls_back_to_payable_text(click_config, monkeypatch):
    monkeypatch.setattr(config, 'click_tutorial_video_id', 'invalid-video')
    message = make_message(photo=False)
    message.answer_video = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message='wrong file identifier'))
    callback = make_callback('pay_click_1_0', message)
    await handlers._show_click_checkout(callback, SimpleNamespace(id=42, amount=500_000, cashback_applied=0), 'uz')
    assert texts.CLICK_CARD_INSTRUCTION['uz'] in message.edit_text.await_args.args[0]
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_video_back_and_reopen_edit_caption_without_minting(click_config, monkeypatch):
    message = make_message(photo=False)
    message.video = SimpleNamespace(file_id='video')
    message.answer_video = AsyncMock()
    callback = make_callback('click_back_42', message)
    order = SimpleNamespace(id=42, amount=400_000, cashback_applied=100_000)
    monkeypatch.setattr(handlers, '_payer_language', AsyncMock(return_value='uz'))
    monkeypatch.setattr(handlers, '_click_order_from_callback', AsyncMock(return_value=order))
    mint = AsyncMock()
    monkeypatch.setattr(handlers, 'create_payment_intent', mint)
    await handlers.cb_click_back(callback, AsyncMock())
    rows = message.edit_caption.await_args.kwargs['reply_markup'].inline_keyboard
    assert rows[0][0].callback_data == 'pay_click_order_42'
    callback.data = 'pay_click_order_42'
    await handlers.cb_reopen_click_order(callback, AsyncMock())
    assert message.edit_caption.await_count == 2
    message.answer_video.assert_not_awaited()
    message.answer.assert_not_awaited()
    mint.assert_not_awaited()
