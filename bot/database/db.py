from collections.abc import AsyncIterator
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import config

# Ensure compatible asyncpg connection string for Neon.tech
db_url = config.database_url
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Fix asyncpg incompatibility with sslmode and channel_binding URL query parameters
connect_args = {}
parsed = urlparse(db_url)
query_params = parse_qs(parsed.query)

# Remove channel_binding if present (unsupported by asyncpg)
keys_to_remove = [k for k in query_params if k.lower() in ("channel_binding", "gssencmode")]
for k in keys_to_remove:
    if "require" in [value.lower() for value in query_params[k]]:
        raise ValueError(f"Required {k} is not supported by this asyncpg configuration")
    query_params.pop(k)

sslmode_key = None
for k in query_params:
    if k.lower() == "sslmode":
        sslmode_key = k
        break

if sslmode_key:
    sslmode_val = query_params.pop(sslmode_key)[0]
    # asyncpg supports the libpq SSL modes. Preserve certificate/hostname
    # verification instead of silently reducing verify-full to encryption only.
    if sslmode_val.lower() not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ValueError("Unsupported database SSL mode")
    connect_args["ssl"] = sslmode_val.lower()

new_query = urlencode(query_params, doseq=True)
parsed = parsed._replace(query=new_query)
db_url = urlunparse(parsed)

# Engine configuration for PostgreSQL (Neon.tech compatible)
engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=config.db_pool_recycle,
    pool_size=config.db_pool_size,
    max_overflow=config.db_max_overflow,
    pool_timeout=config.db_pool_timeout,
    pool_use_lifo=True,
    connect_args={**connect_args, "timeout": 15, "command_timeout": 30},
)

from bot.database.models import Base

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

_db_initialized = False

async def init_db():
    """Create all database tables if they do not exist."""
    global _db_initialized
    if not _db_initialized:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_initialized = True

async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency for getting an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
