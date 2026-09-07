"""Tracked tasks kept alive until completion and drained before HTTP shutdown."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task[Any]] = set()


def create_background_task(
    coro: Coroutine[Any, Any, Any], *, name: str | None = None
) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_task_done)
    return task


def _task_done(task: asyncio.Task[Any]) -> None:
    _tasks.discard(task)
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("Background task %s failed", task.get_name(), exc_info=error)


async def stop_background_tasks(timeout: float = 15.0) -> None:
    if not _tasks:
        return
    _, pending = await asyncio.wait(tuple(_tasks), timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
