import asyncio
from bot.database.db import engine
from bot.database.models import Base

async def reset():
    print("Dropping all tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("All tables dropped successfully!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset())
