import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import config

# Ensure compatible asyncpg connection string for Neon.tech
db_url = config.database_url
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Neon serverless environments recommend pool_pre_ping=True
# Some deployment models prefer no pooling at the driver level (poolclass=NullPool) 
# if using an external connection pooler like PgBouncer.
engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    """Dependency for getting an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
