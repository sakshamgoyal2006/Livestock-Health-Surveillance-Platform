from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "SIH 26128 Livestock Surveillance API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://sih:change-me-development-only@db:5432/sih"
    dev_auth_enabled: bool = True
    auth_secret: str = Field(default="development-only-secret-change-before-use", min_length=32)
    access_token_ttl_minutes: int = Field(default=480, ge=5, le=1440)
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith("postgresql+"):
            raise ValueError("DATABASE_URL must use a PostgreSQL async driver")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
