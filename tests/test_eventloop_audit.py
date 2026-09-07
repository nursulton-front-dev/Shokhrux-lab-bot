"""Offline regressions for event-loop, Gemini lifecycle, and fitness FSM failures."""

import asyncio
import datetime
import io
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Message

# Imports must never consult the developer's .env or contact real services.
with patch("pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}), patch.dict(
    os.environ,
    {
        "BOT_TOKEN": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        "GEMINI_API_KEY": "offline-test-key",
    },
):
    from bot.handlers import fitness_tools as fitness
    from bot.services import charts, gemini_service as gemini


def fake_message(text: str | None = "75") -> MagicMock:
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=42)
    message.text = text
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock()
    return message


def fake_state() -> SimpleNamespace:
    return SimpleNamespace(
        update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock(), get_data=AsyncMock(return_value={})
    )


def fake_client(response: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=AsyncMock(return_value=SimpleNamespace(text=response))),
            aclose=AsyncMock(),
        ),
        close=Mock(),
    )


async def call_gemini(operation: str) -> object:
    if operation == "photo":
        return await gemini.analyze_food_image(b"fake-image")
    if operation == "coach":
        return await gemini.ask_nutritionist_ai([], "hello")
    return await gemini.generate_weekly_meal_plan(170, 75, "keep_fit")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["photo", "coach", "meal"])
@pytest.mark.parametrize("fails", [False, True])
async def test_gemini_closes_both_transports_on_success_and_failure(monkeypatch, operation, fails):
    client = fake_client('{"dish":"Soup","calories":200}')
    main_thread = threading.get_ident()
    constructor_threads = []
    close_threads = []

    def construct():
        constructor_threads.append(threading.get_ident())
        return client

    client.close.side_effect = lambda: close_threads.append(threading.get_ident())
    monkeypatch.setattr(gemini, "get_gemini_client", construct)
    if fails:
        client.aio.models.generate_content.side_effect = RuntimeError("offline timeout")
        with pytest.raises(RuntimeError, match="offline timeout"):
            await call_gemini(operation)
        assert client.aio.models.generate_content.await_count == 2
    else:
        await call_gemini(operation)
    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()
    assert constructor_threads[0] != main_thread
    assert close_threads[0] != main_thread


@pytest.mark.asyncio
async def test_gemini_cancellation_closes_active_request(monkeypatch):
    client = fake_client()
    started = asyncio.Event()

    async def hanging_request(**kwargs):
        started.set()
        await asyncio.Event().wait()

    client.aio.models.generate_content.side_effect = hanging_request
    monkeypatch.setattr(gemini, "get_gemini_client", lambda: client)
    task = asyncio.create_task(call_gemini("coach"))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_gemini_cancellation_during_constructor_does_not_leak(monkeypatch):
    client = fake_client()
    started = threading.Event()
    release = threading.Event()

    def construct():
        started.set()
        assert release.wait(timeout=2)
        return client

    monkeypatch.setattr(gemini, "get_gemini_client", construct)
    task = asyncio.create_task(call_gemini("coach"))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()
    client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_gemini_still_closes_sync_transport_if_async_close_fails(monkeypatch):
    client = fake_client()
    client.aio.aclose.side_effect = RuntimeError("close failed")
    monkeypatch.setattr(gemini, "get_gemini_client", lambda: client)
    with pytest.raises(RuntimeError, match="close failed"):
        await call_gemini("coach")
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_chart_handler_keeps_event_loop_responsive(monkeypatch):
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=42)
    callback.message = fake_message()
    callback.answer = AsyncMock()
    session = SimpleNamespace(execute=AsyncMock(return_value=MagicMock()), rollback=AsyncMock())
    records = [SimpleNamespace(recorded_at=datetime.datetime.now(), weight=75)]
    session.execute.return_value.scalars.return_value.all.return_value = records
    monkeypatch.setattr(fitness, "check_guard_and_get_user", AsyncMock(return_value=(object(), "ru", object())))
    main_thread = threading.get_ident()
    ticks = []

    def slow_render(*args, **kwargs):
        assert threading.get_ident() != main_thread
        session.rollback.assert_awaited_once()
        time.sleep(0.08)
        return io.BytesIO(b"PNG"), "summary"

    async def heartbeat():
        for _ in range(4):
            await asyncio.sleep(0.01)
            ticks.append(True)

    monkeypatch.setattr(fitness, "generate_weight_chart", slow_render)
    pulse = asyncio.create_task(heartbeat())
    await fitness.cb_show_weight_chart(callback, session)
    assert len(ticks) == 4
    await pulse
    callback.message.answer_photo.assert_awaited_once()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_real_charts_do_not_mix_figures_or_summaries():
    now = datetime.datetime.now(datetime.timezone.utc)
    jobs = [
        asyncio.to_thread(charts.generate_weight_chart, [(now, 80), (now + datetime.timedelta(days=1), 80 - index)])
        for index in range(1, 5)
    ]
    results = await asyncio.gather(*jobs)
    for index, (buffer, summary) in enumerate(results, start=1):
        with buffer:
            assert buffer.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
        assert f"{index} кг" in summary
    assert charts.plt.get_fignums() == []


def test_chart_exception_releases_figure(monkeypatch):
    from matplotlib.figure import Figure

    monkeypatch.setattr(Figure, "savefig", Mock(side_effect=OSError("disk/render failure")))
    with pytest.raises(OSError):
        charts.generate_weight_chart([(datetime.datetime.now(), 80)])
    assert charts.plt.get_fignums() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["process_profile_weight", "process_profile_height_text", "process_weight_input"])
@pytest.mark.parametrize("value", [None, "NaN", "-50", "1e9", "inf", "invalid"])
async def test_invalid_measurements_do_not_change_state_or_database(monkeypatch, handler, value):
    message = fake_message(value)
    state = fake_state()
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(language="ru")), add=Mock(), commit=AsyncMock())
    monkeypatch.setattr(fitness, "check_guard_and_get_user", AsyncMock(return_value=(object(), "ru", object())))
    await getattr(fitness, handler)(message, state, session)
    state.update_data.assert_not_awaited()
    state.set_state.assert_not_awaited()
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_profile_lookup_uses_clicking_user():
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=42)
    callback.message = fake_message()
    callback.message.from_user = SimpleNamespace(id=999)
    profile = SimpleNamespace(goal="keep_fit", weight_kg=75)
    session = SimpleNamespace(scalar=AsyncMock(return_value=profile))
    assert await fitness.ensure_fitness_profile(callback, session, fake_state(), "weight_log") is profile
    statement = session.scalar.await_args.args[0]
    assert list(statement.compile().params.values()) == [42]


@pytest.mark.asyncio
async def test_weight_tool_can_resume_after_questionnaire_photo(monkeypatch):
    message = fake_message(None)
    state = fake_state()
    monkeypatch.setattr(fitness, "check_guard_and_get_user", AsyncMock(return_value=(object(), "ru", object())))
    monkeypatch.setattr(fitness, "ensure_fitness_profile", AsyncMock(return_value=object()))
    await fitness.start_add_weight(message, object(), state)
    state.set_state.assert_awaited_once_with(fitness.FitnessStates.waiting_for_weight)
    message.answer.assert_awaited_once()


@pytest.mark.parametrize("text", ["x" * 12000, "😃" * 5000, "<b>" + "x" * 10000 + "</b>"])
def test_unbroken_model_output_is_bounded(text):
    chunks = fitness.split_text_into_chunks(text)
    assert "".join(chunks) == text
    assert all(len(chunk.encode("utf-16-le")) // 2 <= 3500 for chunk in chunks)


@pytest.mark.asyncio
async def test_invalid_model_html_falls_back_to_explicit_plain_text():
    message = fake_message()
    message.answer.side_effect = [TelegramBadRequest(SendMessage(chat_id=42, text="x"), "can't parse entities"), None]
    await fitness.send_safe_message(message, "<b>unclosed &amp; <user>")
    assert message.answer.await_count == 2
    assert message.answer.await_args.kwargs["parse_mode"] is None


@pytest.mark.asyncio
async def test_forbidden_delivery_is_not_retried_as_html_error():
    message = fake_message()
    message.answer.side_effect = TelegramForbiddenError(SendMessage(chat_id=42, text="x"), "blocked")
    with pytest.raises(TelegramForbiddenError):
        await fitness.send_safe_message(message, "answer")
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["photo", "coach", "meal"])
async def test_ai_handlers_release_database_connection_before_google_wait(monkeypatch, operation):
    message = fake_message("hello")
    message.chat = SimpleNamespace(id=42)
    message.photo = [SimpleNamespace(file_id="photo")]
    wait_message = SimpleNamespace(delete=AsyncMock())
    message.answer.return_value = wait_message
    profile = SimpleNamespace(height_cm=170, weight_kg=75, goal="keep_fit", gender="M")
    session = SimpleNamespace(scalar=AsyncMock(return_value=profile), rollback=AsyncMock())
    state = fake_state()
    bot = SimpleNamespace(
        send_chat_action=AsyncMock(),
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="photo.jpg")),
        download_file=AsyncMock(),
    )
    monkeypatch.setattr(fitness, "check_guard_and_get_user", AsyncMock(return_value=(object(), "ru", object())))

    async def generate(**kwargs):
        session.rollback.assert_awaited_once()
        if operation == "meal":
            assert kwargs["height_cm"] == 170
            assert kwargs["weight_kg"] == 75
        raise RuntimeError("offline service timeout")

    api = AsyncMock(side_effect=generate)
    if operation == "photo":
        monkeypatch.setattr(fitness, "analyze_food_image", api)
        await fitness.process_food_photo(message, state, session, bot)
    elif operation == "meal":
        # Simulate expire-on-rollback: snapshots must precede transaction close.
        session.rollback.side_effect = lambda: profile.__dict__.clear()
        monkeypatch.setattr(fitness, "generate_weekly_meal_plan", api)
        await fitness.handle_meal_plan(message, session, state)
    else:
        monkeypatch.setattr(fitness, "ask_nutritionist_ai", api)
        await fitness.process_ai_nutritionist_query(message, state, session, bot)
    api.assert_awaited_once()
