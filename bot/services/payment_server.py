"""Lifecycle for the merchant HTTP endpoint, run alongside Telegram polling.

One aiohttp application serves both the Payme and the Click callbacks, so nginx
keeps a single upstream and the container exposes a single port.
"""
import asyncio
import logging

from aiogram import Bot
from aiohttp import web

from bot.config import config
from bot.services.click import api as click_api
from bot.services.payme import api as payme_api

logger = logging.getLogger(__name__)

SHUTDOWN_TIMEOUT_SECONDS = 10


def create_app(bot: Bot) -> web.Application:
    app = payme_api.create_app(bot)
    click_api.register_routes(app, bot)
    return app


async def run_payment_server(bot: Bot) -> None:
    """Serve until cancelled. Missing credentials disable one merchant loudly.

    A merchant whose credentials are absent still answers, and always rejects:
    Payme with -32504 and Click with a failed signature check.
    """
    if not config.payme_enabled:
        logger.error(
            "Payme callbacks will be rejected: PAYME_MERCHANT_ID and the key for "
            "%s mode must both be set", "sandbox" if config.payme_sandbox else "production",
        )
    if not config.click_enabled:
        logger.error(
            "Click callbacks will be rejected: CLICK_SERVICE_ID, CLICK_MERCHANT_ID "
            "and CLICK_SECRET_KEY must all be set",
        )
    if not (config.payme_enabled or config.click_enabled):
        logger.error("Payment endpoint not started: no merchant is configured")
        return
    runner = web.AppRunner(create_app(bot), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, config.payme_host, config.payme_port, shutdown_timeout=SHUTDOWN_TIMEOUT_SECONDS)
    try:
        await site.start()
        logger.info(
            "Payment endpoint listening on %s:%s (payme=%s in %s mode, click=%s)",
            config.payme_host, config.payme_port, config.payme_enabled,
            "sandbox" if config.payme_sandbox else "production", config.click_enabled,
        )
        await asyncio.Event().wait()
    finally:
        # Shielded so an in-flight PerformTransaction is not abandoned mid-commit.
        await asyncio.shield(asyncio.create_task(runner.cleanup()))
        logger.info("Payment endpoint stopped")
