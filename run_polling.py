import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties

from bot.config import config
from bot.database.db import AsyncSessionLocal, init_db
from bot.handlers.user import router as user_router
from bot.handlers.admin import router as admin_router
from bot.services.scheduler import start_scheduler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Middleware for injecting database session into handlers
class DBSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        async with AsyncSessionLocal() as session:
            data['session'] = session
            return await handler(event, data)

async def main():
    logger.info("Initializing Telegram Bot in Long Polling mode...")
    
    # 1. Initialize Bot & Dispatcher
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher()
    
    # 2. Register Middlewares and Routers
    dp.update.middleware(DBSessionMiddleware())
    dp.include_router(admin_router)
    dp.include_router(user_router)
    
    # 3. Initialize Database Schema
    logger.info("Ensuring database tables exist in Neon PostgreSQL...")
    await init_db()
    logger.info("Database schema initialized successfully.")
    
    # 4. Start Bot with retry loop
    try:
        while True:
            try:
                logger.info("Deleting old webhooks and clearing pending updates...")
                await bot.delete_webhook(drop_pending_updates=True)
                
                # Start background tasks
                logger.info("Starting background scheduler...")
                asyncio.create_task(start_scheduler(bot))
                
                logger.info("Starting Long Polling...")
                await dp.start_polling(bot)
                break # Exit loop if polling ends gracefully
            except Exception as e:
                logger.error(f"Network error during bot startup/polling: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot process stopped gracefully.")
