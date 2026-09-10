"""HTTP transport for the Click SHOP API.

Click expects HTTP 200 with a negative `error` code for every business failure,
including a failed signature check, so the status code carries no protocol
meaning here. Bodies arrive form-encoded; JSON is accepted as well because the
cabinet's test tool sends it.
"""
import json
import logging
from typing import Any
from urllib.parse import parse_qsl

from aiogram import Bot
from aiohttp import web

from bot.config import config
from bot.database.db import AsyncSessionLocal
from bot.services import http_throttle as throttle
from bot.services.click import errors, protocol, service

logger = logging.getLogger(__name__)

CLICK_PREPARE_PATH = "/api/click/prepare"
CLICK_COMPLETE_PATH = "/api/click/complete"
MAX_BODY_BYTES = 16 * 1024
# Click retries steadily rather than in bursts; this only sheds an obvious flood.
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW_SECONDS = 10.0

BOT_KEY = web.AppKey("click_bot", Bot)
RATE_LIMIT_KEY: web.AppKey[throttle.Buckets] = web.AppKey("click_rate_limit", dict)


async def _read_fields(request: web.Request) -> dict[str, str]:
    """Return the callback fields as raw strings, exactly as Click sent them."""
    body = await request.read()
    if len(body) > MAX_BODY_BYTES:
        raise errors.ClickError(errors.BAD_REQUEST, "body larger than the protocol allows")
    content_type = (request.headers.get("Content-Type") or "").partition(";")[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise errors.ClickError(errors.BAD_REQUEST, "malformed JSON body") from None
        if not isinstance(payload, dict):
            raise errors.ClickError(errors.BAD_REQUEST, "JSON body must be an object")
        return {str(key): "" if value is None else str(value) for key, value in payload.items()}
    try:
        fields = dict(parse_qsl(body.decode("utf-8"), keep_blank_values=True))
    except UnicodeDecodeError:
        raise errors.ClickError(errors.BAD_REQUEST, "body is not UTF-8") from None
    for key, value in request.query.items():
        fields.setdefault(key, value)
    return fields


def _echo(value: str) -> Any:
    """Click sends numeric ids; echo them as numbers when they parse as such."""
    trimmed = value.strip()
    return int(trimmed) if trimmed.lstrip("-").isdigit() else trimmed


def _response(fields: dict[str, str], action: int, code: int, note: str,
              merchant_id: int | None = None) -> web.Response:
    body: dict[str, Any] = {
        "click_trans_id": _echo(fields.get("click_trans_id", "")),
        "merchant_trans_id": _echo(fields.get("merchant_trans_id", "")),
        "error": code,
        "error_note": note,
    }
    if merchant_id is not None:
        key = "merchant_prepare_id" if action == protocol.ACTION_PREPARE else "merchant_confirm_id"
        body[key] = merchant_id
    return web.json_response(
        body,
        dumps=lambda data: json.dumps(data, ensure_ascii=False),
        headers={"X-Content-Type-Options": "nosniff"},
    )


async def _handle(request: web.Request, action: int) -> web.Response:
    """Single entry point for both callbacks; every outcome is HTTP 200."""
    fields: dict[str, str] = {}
    try:
        if not throttle.allow(request.app[RATE_LIMIT_KEY], throttle.client_ip(request),
                              limit=RATE_LIMIT_REQUESTS, window=RATE_LIMIT_WINDOW_SECONDS):
            raise errors.ClickError(errors.BAD_REQUEST, "rate limit exceeded")
        fields = await _read_fields(request)
        parsed = protocol.parse_request(
            fields, action,
            secret_key=config.click_secret_key, service_id=config.click_service_id,
        )
        async with AsyncSessionLocal() as session:
            if action == protocol.ACTION_PREPARE:
                merchant_id = await service.prepare(session, parsed)
            else:
                merchant_id = await service.complete(session, parsed, request.app[BOT_KEY])
        logger.info(
            "Click %s succeeded: click_trans_id=%s order=%s",
            "prepare" if action == protocol.ACTION_PREPARE else "complete",
            parsed.click_trans_id, parsed.order_id,
        )
        return _response(fields, action, errors.SUCCESS, errors.NOTES[errors.SUCCESS], merchant_id)
    except errors.ClickError as error:
        logger.warning("Click callback failed: code=%s detail=%s", error.code, error.detail)
        return _response(fields, action, error.code, error.note)
    except Exception:
        logger.exception("Unhandled Click error on %s", request.path)
        # Click retries a failed update, so an internal fault never drops money.
        return _response(fields, action, errors.UPDATE_FAILED, errors.NOTES[errors.UPDATE_FAILED])


async def handle_prepare(request: web.Request) -> web.Response:
    return await _handle(request, protocol.ACTION_PREPARE)


async def handle_complete(request: web.Request) -> web.Response:
    return await _handle(request, protocol.ACTION_COMPLETE)


def register_routes(app: web.Application, bot: Bot) -> None:
    app[BOT_KEY] = bot
    app[RATE_LIMIT_KEY] = {}
    app.router.add_post(CLICK_PREPARE_PATH, handle_prepare)
    app.router.add_post(CLICK_COMPLETE_PATH, handle_complete)
