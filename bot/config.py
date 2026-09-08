from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional

class Settings(BaseSettings):
    bot_token: str = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    database_url: str = "postgresql+asyncpg://user:pass@localhost/db"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=0, ge=0, le=50)
    db_pool_timeout: int = Field(default=10, ge=1, le=60)
    db_pool_recycle: int = Field(default=600, ge=300, le=1800)
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    admin_id: Optional[int] = None # Legacy fallback
    admin_ids: Optional[str] = None
    support_id: Optional[int] = None
    support_username: Optional[str] = None
    gemini_api_key: Optional[str] = None

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
    channel_id: Optional[int] = -1001234567890  # Main closed channel (MAIN_CHANNEL_ID)
    vip_chat_id: Optional[int] = None  # Closed VIP group for 6-month clients

    # Tariff banner per interface language. Relative paths resolve against the
    # project root, so the same value works under Docker and systemd.
    tariffs_img_uz: str = "assets/Tarifs_uz.jpg"
    tariffs_img_ru: str = "assets/Tarifs_ru.jpg"

    def tariffs_img(self, lang: str) -> str:
        return self.tariffs_img_ru if lang == "ru" else self.tariffs_img_uz

    cashback_reward_amount: int = Field(default=30000, ge=0)

    @field_validator(
        "admin_id", "support_id", "channel_id", "vip_chat_id",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v):
        """Treat an empty/blank env value for optional int fields as unset,
        so a `VIP_CHAT_ID=` line in .env doesn't crash startup."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = Settings()
