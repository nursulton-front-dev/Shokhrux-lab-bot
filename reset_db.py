import asyncio
from bot.database.db import engine
from bot.database.models import Base

async def reset_database():
    print("Dropping all tables from database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("Re-creating all tables...")
        await conn.run_sync(Base.metadata.create_all)
    print("Database has been completely cleared and reset successfully!")

if __name__ == "__main__":
    asyncio.run(reset_database())
