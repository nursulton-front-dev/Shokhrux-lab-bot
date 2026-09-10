"""Wipe all application data while keeping the migrated schema.

TRUNCATE keeps tables, indexes and constraints that `run_migration.py` built,
so a test reset never has to re-run CREATE INDEX CONCURRENTLY. Development and
staging only — this destroys every row.
"""
import asyncio

from sqlalchemy import text

from bot.database.db import engine
from bot.database.models import Base


async def clear_db() -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
            for table in Base.metadata.sorted_tables:
                count = await conn.scalar(text(f'SELECT count(*) FROM "{table.name}"'))
                print(f"  {table.name}: {count}")
        print("Database cleared successfully.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(clear_db())
