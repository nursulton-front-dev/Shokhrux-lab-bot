from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import config

# Ensure compatible asyncpg connection string for Neon.tech
db_url = config.database_url
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Fix asyncpg incompatibility with sslmode URL query parameter
connect_args = {}
parsed = urlparse(db_url)
query_params = parse_qs(parsed.query)

sslmode_key = None
for k in query_params:
    if k.lower() == "sslmode":
        sslmode_key = k
        break

if sslmode_key:
    sslmode_val = query_params.pop(sslmode_key)[0]
    if sslmode_val.lower() in ("require", "verify-ca", "verify-full", "prefer"):
        connect_args["ssl"] = "require"
    elif sslmode_val.lower() == "disable":
        connect_args["ssl"] = False

    new_query = urlencode(query_params, doseq=True)
    parsed = parsed._replace(query=new_query)
    db_url = urlunparse(parsed)

from sqlalchemy.pool import NullPool

# Neon serverless environments recommend pool_pre_ping=True
# In serverless environments (Vercel), use NullPool to prevent connection pooling across closed event loops
engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool,
    connect_args=connect_args
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

async def get_session() -> AsyncSession:
    """Dependency for getting an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
