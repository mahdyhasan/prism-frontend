from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    prism_env: Literal["dev", "staging", "prod"] = "dev"

    # Database
    prism_database_url: str = Field(
        default="mysql+aiomysql://prism:prism@localhost:3306/prism"
    )

    # Redis
    prism_redis_url: str = Field(default="redis://localhost:6379/0")

    # Security
    prism_token_encryption_key: str = Field(default="")
    prism_jwt_secret: str = Field(default="")

    # Google OAuth
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")
    google_service_account_json: str = Field(default="")

    # Anthropic
    anthropic_api_key: str = Field(default="")

    # Service URLs
    prism_api_base_url: str = Field(default="http://localhost:8000")
    prism_web_base_url: str = Field(default="http://localhost:3000")

    # Google PageSpeed Insights / CrUX
    psi_api_key: str = Field(default="", description="Google PageSpeed Insights v5 API key")
    crux_api_key: str = Field(default="", description="Chrome UX Report v1 API key (same as PSI)")

    # Actions HMAC
    actions_hmac_secret: str = Field(
        default="",
        description="HMAC-SHA256 secret for action confirmation tokens",
    )

    # Observability
    sentry_dsn: str = Field(default="")

    @property
    def is_prod(self) -> bool:
        return self.prism_env == "prod"

    @property
    def debug(self) -> bool:
        return self.prism_env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
