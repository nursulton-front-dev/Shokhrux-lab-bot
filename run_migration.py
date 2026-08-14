import asyncio
from bot.database.db import engine
from sqlalchemy import text

async def main():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(5);"))
            print("Successfully added 'language' column to 'users' table.")
        except Exception as e:
            print(f"Error (maybe already exists): {e}")

if __name__ == "__main__":
    asyncio.run(main())
