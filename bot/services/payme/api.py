"""HTTP transport for the Payme Merchant API.

Payme expects HTTP 200 with a JSON-RPC error object for every business failure,
including authentication, so the status code carries no protocol meaning here.
"""
import base64
import binascii
import hmac
import json
import logging
from typing import Any, Awaitable, Callable

from aiogram import Bot
from aiohttp import web

from bot.config import config
from bot.database.db import AsyncSessionLocal
from bot.services import http_throttle as throttle
from bot.services.http_payload import read_body, load_json
from bot.services.payme import errors, service

logger = logging.getLogger(__name__)

PAYME_PATH = "/api/payme"
PAYME_LOGIN = "Paycom"
MAX_BODY_BYTES = 64 * 1024
# Payme's sandbox fires bursts of calls; this only sheds an obvious flood.
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW_SECONDS = 10.0

BOT_KEY = web.AppKey("bot", Bot)
RATE_LIMIT_KEY: web.AppKey[throttle.Buckets] = web.AppKey("payme_rate_limit", dict)

Handler = Callable[..., Awaitable[dict[str, Any]]]


def _authorize(request: web.Request) -> None:
    """Payme authenticates with Basic auth: login `Paycom`, password = key."""
    expected_key = config.payme_key
    if not expected_key:
        logger.error("Payme request rejected: no key configured for the current mode")
        raise errors.insufficient_privilege()
    header = request.headers.get("Authorization", "")
    scheme, _, encoded = header.partition(" ")
    if len(header) > 1024 or scheme.lower() != "basic" or not encoded:
        raise errors.insufficient_privilege()
    try:
        login, _, key = base64.b64decode(encoded, validate=True).decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError):
        raise errors.insufficient_privilege() from None
    allowed_logins = {PAYME_LOGIN.lower(), (config.payme_merchant_id or "").lower()}
    login_ok = login.lower() in allowed_logins
    key_ok = hmac.compare_digest(key.encode("utf-8"), expected_key.encode("utf-8"))
    # Compare both before deciding, so timing cannot separate the two failures.
    if not (login_ok and key_ok):
        raise errors.insufficient_privilege()


def _check_rate_limit(request: web.Request) -> None:
    if not throttle.allow(
        request.app[RATE_LIMIT_KEY], throttle.client_ip(request),
        limit=RATE_LIMIT_REQUESTS, window=RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise errors.unable_to_perform("rate limit exceeded")


METHODS: dict[str, str] = {
    "CheckPerformTransaction": "check_perform_transaction",
    "CreateTransaction": "create_transaction",
    "PerformTransaction": "perform_transaction",
    "CancelTransaction": "cancel_transaction",
    "CheckTransaction": "check_transaction",
    "GetStatement": "get_statement",
}
# Only these methods commit money, so only they need the bot for delivery.
BOT_AWARE_METHODS = frozenset({"perform_transaction"})


def _json_response(payload: dict[str, Any]) -> web.Response:
    return web.json_response(
        payload,
        dumps=lambda data: json.dumps(data, ensure_ascii=False),
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _success(request_id: Any, result: dict[str, Any]) -> web.Response:
    return _json_response({"jsonrpc": "2.0", "id": request_id, "result": result})


def _failure(request_id: Any, error: errors.PaymeError) -> web.Response:
    return _json_response({"jsonrpc": "2.0", "id": request_id, "error": error.as_error_object()})


async def _read_rpc_request(request: web.Request) -> tuple[Any, str, dict[str, Any]]:
    try:
        body = await read_body(request, MAX_BODY_BYTES)
        payload = load_json(body)
    except (ValueError, UnicodeError, TimeoutError):
        raise errors.parse_error() from None
    if not isinstance(payload, dict):
        raise errors.invalid_request()
    method = payload.get("method")
    params = payload.get("params")
    request_id = payload.get("id")
    if (not isinstance(method, str) or len(method) > 64
            or isinstance(request_id, bool) or not isinstance(request_id, (str, int, type(None)))):
        raise errors.invalid_request()
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise errors.invalid_params()
    return request_id, method, params


async def handle_payme(request: web.Request) -> web.Response:
    """Single JSON-RPC entry point; every outcome is reported as HTTP 200."""
    request_id: Any = None
    try:
        _check_rate_limit(request)
        _authorize(request)
        request_id, method, params = await _read_rpc_request(request)
        handler_name = METHODS.get(method)
        if handler_name is None:
            raise errors.method_not_found(method)
        handler: Handler = getattr(service, handler_name)
        async with AsyncSessionLocal() as session:
            if handler_name in BOT_AWARE_METHODS:
                result = await handler(session, params, request.app[BOT_KEY])
            else:
                result = await handler(session, params)
        logger.info("Payme %s succeeded (id=%s)", method, request_id)
        return _success(request_id, result)
    except errors.PaymeError as error:
        logger.warning("Payme request failed: code=%s data=%s", error.code, error.data)
        return _failure(request_id, error)
    except Exception:
        logger.exception("Unhandled Payme error (id=%s)", request_id)
        # Payme retries -31008, so an internal fault never silently drops money.
        return _failure(request_id, errors.unable_to_perform("internal error"))


async def handle_health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app(bot: Bot) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY_BYTES, handler_args={"auto_decompress": False})
    app[BOT_KEY] = bot
    app[RATE_LIMIT_KEY] = {}
    app.router.add_post(PAYME_PATH, handle_payme)
    app.router.add_get("/healthz", handle_health)
    return app
