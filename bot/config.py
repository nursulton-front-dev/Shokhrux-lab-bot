from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    bot_token: str = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    database_url: str = "postgresql+asyncpg://user:pass@localhost/db"
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    admin_id: Optional[int] = None # Legacy fallback
    admin_ids: Optional[str] = None
    support_id: Optional[int] = None
    support_username: Optional[str] = None

    @property
    def get_admin_ids(self) -> list[int]:
        ids = set()
        if self.admin_ids:
            for x in self.admin_ids.split(','):
                x = x.strip()
                if x.isdigit():
                    ids.add(int(x))
        if self.admin_id:
            ids.add(self.admin_id)
        if self.support_id:
            ids.add(self.support_id)
        return list(ids)
    channel_id: Optional[int] = -1001234567890
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = Settings()
