import asyncio
from bot.database.db import engine
from sqlalchemy import text

async def clear_db():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("DROP TABLE IF EXISTS payments CASCADE;"))
            await conn.execute(text("DROP TABLE IF EXISTS subscriptions CASCADE;"))
            await conn.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
            print("Database tables cleared successfully!")
        except Exception as e:
            print(f"Error clearing db: {e}")

if __name__ == "__main__":
    asyncio.run(clear_db())
