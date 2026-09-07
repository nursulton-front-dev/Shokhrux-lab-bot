"""Never load operator credentials or connect to the configured production DB."""
import os

from pydantic_settings import DotEnvSettingsSource

DotEnvSettingsSource.__call__ = lambda self: {}
os.environ.update(
    BOT_TOKEN="123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    DATABASE_URL="postgresql+asyncpg://audit:audit@127.0.0.1:1/audit",
    GEMINI_API_KEY="audit-offline-key",
    ADMIN_IDS="900",
    SUPPORT_ID="",
    LOG_FILE="-",
)
