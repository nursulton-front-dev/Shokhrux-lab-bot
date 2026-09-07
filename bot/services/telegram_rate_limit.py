"""One outgoing Telegram budget shared by handlers and background workers."""

import asyncio
from collections import OrderedDict
from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import TelegramMethod


class TelegramRateLimitMiddleware(BaseRequestMiddleware):
    def __init__(self, requests_per_second: float = 25.0, retries: int = 3) -> None:
        if requests_per_second <= 0 or retries < 0:
            raise ValueError("Invalid Telegram rate limit configuration")
        self._interval = 1.0 / requests_per_second
        self._retries = retries
        self._lock = asyncio.Lock()
        self._next_request = 0.0
        self._blocked_until = 0.0
        self._chats: OrderedDict[int | str, float] = OrderedDict()

    async def _acquire(self, method: TelegramMethod[Any]) -> None:
        name = method.__api_method__
        chat_id = getattr(method, "chat_id", None)
        sends_message = name.startswith(("send", "copy", "forward")) and name != "sendChatAction"
        chat_interval = 3.1 if isinstance(chat_id, str) or (isinstance(chat_id, int) and chat_id < 0) else 1.05
        batch = getattr(method, "media", None) or getattr(method, "message_ids", None)
        cost = max(1, len(batch)) if isinstance(batch, (list, tuple)) else 1
        while True:
            async with self._lock:
                now = asyncio.get_running_loop().time()
                # Bounded by traffic in the last few seconds, not lifetime users.
                for stale_chat, deadline in list(self._chats.items()):
                    if deadline <= now:
                        self._chats.pop(stale_chat, None)
                ready_at = max(self._next_request, self._blocked_until)
                if sends_message and chat_id is not None:
                    ready_at = max(ready_at, self._chats.get(chat_id, 0.0))
                delay = ready_at - now
                if delay <= 0:
                    self._next_request = now + self._interval * cost
                    if sends_message and chat_id is not None:
                        self._chats[chat_id] = now + chat_interval * cost
                    return
            # Sleeping outside the lock lets other chats use their available quota.
            await asyncio.sleep(delay)

    async def __call__(
        self, make_request: NextRequestMiddlewareType, bot: Bot, method: TelegramMethod[Any]
    ) -> Any:
        if method.__api_method__ == "getUpdates":
            return await make_request(bot, method)
        for attempt in range(self._retries + 1):
            await self._acquire(method)
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as exc:
                async with self._lock:
                    self._blocked_until = max(
                        self._blocked_until,
                        asyncio.get_running_loop().time() + exc.retry_after + 0.1,
                    )
                # The server rejected the operation, so a 429 is safe to retry.
                # Timeouts are deliberately allowed through: send may have succeeded.
                if attempt == self._retries or exc.retry_after > 60:
                    raise
        raise RuntimeError("Unreachable Telegram retry state")


async def kick_member(bot: Bot, chat_id: int, user_id: int) -> None:
    """Remove membership without ever creating a permanent ban.

    Telegram unbanChatMember with only_if_banned=False also removes a current
    member. It is a single retryable action, unlike the ban/unban pair.
    """
    await bot.unban_chat_member(
        chat_id=chat_id, user_id=user_id, only_if_banned=False, request_timeout=15
    )


async def revoke_invite(bot: Bot, chat_id: int, invite_link: str | None) -> None:
    if not invite_link:
        return
    try:
        await bot.revoke_chat_invite_link(
            chat_id=chat_id, invite_link=invite_link, request_timeout=15
        )
    except TelegramBadRequest as exc:
        # An already invalid link cannot grant access. Rights/network errors must
        # propagate so the durable cleanup state is retried on the next pass.
        if not any(code in exc.message.upper() for code in (
            "INVITE_HASH_EXPIRED", "INVITE_HASH_INVALID", "INVITE_REVOKED"
        )):
            raise
