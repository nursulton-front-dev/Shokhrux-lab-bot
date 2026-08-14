import json
import asyncio
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties

from bot.config import config
from bot.database.db import AsyncSessionLocal, init_db, engine
from bot.handlers.user import router as user_router
from api.cron import run_cron_jobs

# Initialize Aiogram Bot and Dispatcher
bot = Bot(
    token=config.bot_token,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()
dp.include_router(user_router)

# Middleware for injecting database session
class DBSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        await init_db()
        async with AsyncSessionLocal() as session:
            data['session'] = session
            return await handler(event, data)

dp.update.middleware(DBSessionMiddleware())

async def process_update(update: Update):
    try:
        await dp.feed_update(bot=bot, update=update)
    finally:
        await engine.dispose()

class handler(BaseHTTPRequestHandler):
    """
    Vercel Serverless HTTP Handler
    """
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/api/cron':
            try:
                asyncio.run(run_cron_jobs(bot))
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'success'}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Bot is running. Use POST to send webhooks or GET /api/cron to trigger tasks.")

    def do_POST(self):
        parsed_path = urlparse(self.path)
        
        # Webhook processing route
        if parsed_path.path == '/api/webhook':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                update_dict = json.loads(post_data.decode('utf-8'))
                update = Update(**update_dict)
                
                # Process the update synchronously within the serverless invocation
                asyncio.run(process_update(update))
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
            except Exception as e:
                print(f"Error handling update: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
