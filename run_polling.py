import asyncio
import logging
import os
import queue
import signal
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import TelegramObject

from bot.config import config
from bot.database.db import AsyncSessionLocal, engine, init_db
from bot.handlers.admin import router as admin_router
from bot.handlers.fitness_tools import router as fitness_router
from bot.handlers.user import router as user_router
from bot.services.background_tasks import stop_background_tasks
from bot.services.scheduler import start_payment_delivery, start_scheduler
from bot.services.telegram_rate_limit import TelegramRateLimitMiddleware

logger = logging.getLogger(__name__)


class NonBlockingQueueHandler(QueueHandler):
    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # Bound memory under log storms without blocking Telegram's loop.
            pass


class DrainQueueListener(QueueListener):
    def enqueue_sentinel(self) -> None:
        # stop() is called in a worker thread, never on the event loop.
        self.queue.put(self._sentinel)


def setup_logging() -> QueueListener:
    """Open/rotate/write both log sinks on threads, with a bounded event-loop queue."""
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    handlers: list[logging.Handler] = [stream_handler]
    log_file = os.getenv("LOG_FILE", "bot.log")
    if log_file and log_file != "-":
        handlers.append(RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        ))
    for handler in handlers:
        handler.setFormatter(formatter)
    log_queue: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=10_000)
    root_logger = logging.getLogger()
    for previous in root_logger.handlers[:]:
        root_logger.removeHandler(previous)
        previous.close()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(NonBlockingQueueHandler(log_queue))
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    listener = DrainQueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()
    return listener


def stop_logging(listener: QueueListener) -> None:
    listener.stop()
    for handler in listener.handlers:
        handler.close()


class DBSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)


async def _drain_handlers(dp: Dispatcher, timeout: float = 15.0) -> None:
    # aiogram 3.30 tracks update tasks but start_polling() does not await them.
    # Drain before closing transports, even for tasks waiting for FSM isolation.
    tasks = tuple(dp._handle_update_tasks)
    if tasks:
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def _run_application(bot: Bot, dp: Dispatcher, workers: list[asyncio.Task[None]]) -> None:
    logger.info("Initializing database")
    await init_db()
    # Keep receipts and other updates queued while the bot was offline.
    await bot.delete_webhook(drop_pending_updates=False, request_timeout=15)
    workers.extend((
        asyncio.create_task(start_scheduler(bot), name="subscription-scheduler"),
        asyncio.create_task(start_payment_delivery(bot), name="payment-delivery"),
    ))
    # aiogram retries transient getUpdates failures internally. A second outer
    # polling loop would duplicate workers and restart closed transports.
    await dp.start_polling(
        bot, handle_signals=False, close_bot_session=False, tasks_concurrency_limit=50
    )


async def main() -> None:
    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_requested.set)
            installed_signals.append(sig)
    listener: QueueListener | None = None
    bot: Bot | None = None
    dp: Dispatcher | None = None
    runner: asyncio.Task[None] | None = None
    stop_waiter: asyncio.Task[bool] | None = None
    workers: list[asyncio.Task[None]] = []
    try:
        listener = await asyncio.to_thread(setup_logging)
        bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
        bot.session.middleware(TelegramRateLimitMiddleware())
        dp = Dispatcher(events_isolation=SimpleEventIsolation())
        dp.update.middleware(DBSessionMiddleware())
        dp.include_router(admin_router)
        dp.include_router(fitness_router)
        dp.include_router(user_router)
        runner = asyncio.create_task(_run_application(bot, dp, workers), name="bot-runtime")
        stop_waiter = asyncio.create_task(stop_requested.wait(), name="stop-signal")
        done, _ = await asyncio.wait((runner, stop_waiter), return_when=asyncio.FIRST_COMPLETED)
        if runner in done:
            await runner
        else:
            logger.info("Shutdown requested")
            try:
                await dp.stop_polling()
            except RuntimeError:
                # SIGTERM can arrive during DB initialization/webhook setup.
                runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner
    finally:
        if stop_waiter is not None:
            stop_waiter.cancel()
            await asyncio.gather(stop_waiter, return_exceptions=True)
        if runner is not None and not runner.done():
            if dp is not None:
                with suppress(RuntimeError):
                    await dp.stop_polling()
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)
        for task in workers:
            task.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        if dp is not None:
            await _drain_handlers(dp)
        await stop_background_tasks(timeout=15)
        if bot is not None:
            await bot.session.close()
        await engine.dispose()
        for sig in installed_signals:
            loop.remove_signal_handler(sig)
        if listener is not None:
            logger.info("Bot process stopped; transports and database pool closed")
            await asyncio.to_thread(stop_logging, listener)


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
