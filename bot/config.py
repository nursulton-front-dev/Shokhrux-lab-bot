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

    # ===== Payme Merchant API =====
    payme_merchant_id: Optional[str] = None
    payme_test_key: Optional[str] = None
    payme_prod_key: Optional[str] = None
    # Sandbox mode authenticates with the test key and enables sandbox orders.
    payme_sandbox: bool = True
    payme_host: str = "0.0.0.0"
    payme_port: int = Field(default=8000, ge=1, le=65535)

    @property
    def payme_key(self) -> Optional[str]:
        """Exactly one key is accepted, so a leaked test key cannot sign
        production callbacks and vice versa."""
        return self.payme_test_key if self.payme_sandbox else self.payme_prod_key

    @property
    def payme_enabled(self) -> bool:
        return bool(self.payme_merchant_id and self.payme_key)

    # Temporary launch gate: the Merchant API endpoint keeps serving Payme's
    # callbacks, but payers see a "coming soon" notice instead of a checkout
    # link. Set PAYME_CHECKOUT_PAUSED=false in .env to open Payme checkout.
    payme_checkout_paused: bool = True

    @property
    def payme_checkout_open(self) -> bool:
        return self.payme_enabled and not self.payme_checkout_paused

    # ===== Click SHOP API =====
    click_service_id: Optional[int] = None
    click_merchant_id: Optional[int] = None
    click_secret_key: Optional[str] = None
    click_tutorial_video_path: Optional[str] = "assets/click_instruction.mp4"
    click_tutorial_video_id: Optional[str] = None
    payment_delivery_concurrency: int = Field(default=4, ge=1, le=20)
    payment_delivery_batch_size: int = Field(default=50, ge=1, le=200)
    # Exact direct proxy addresses/CIDRs; never trust forwarding headers by default.
    trusted_proxy_ips: str = ""

    @field_validator("trusted_proxy_ips")
    @classmethod
    def _validate_trusted_proxies(cls, value: str) -> str:
        from ipaddress import ip_network
        for entry in value.split(","):
            if entry.strip():
                network = ip_network(entry.strip(), strict=False)
                if network.prefixlen == 0:
                    raise ValueError("Do not trust all internet addresses as proxies")
        return value

    @property
    def click_enabled(self) -> bool:
        return bool(self.click_service_id and self.click_merchant_id and self.click_secret_key)

    @field_validator(
        "admin_id", "support_id", "channel_id", "vip_chat_id",
        "payme_merchant_id", "payme_test_key", "payme_prod_key",
        "click_service_id", "click_merchant_id", "click_secret_key",
        "click_tutorial_video_path", "click_tutorial_video_id",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v):
        """Treat an empty/blank env value for optional fields as unset, so a
        `VIP_CHAT_ID=` or `PAYME_PROD_KEY=` line in .env doesn't crash startup."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = Settings()
