from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr("postgresql+psycopg://gold_reader@db/gold")
    database_role: Literal["gold_reader", "gold_owner", "gold_ingestor"] | None = None
    database_password_file: Path | None = None
    xau_api_key: SecretStr = SecretStr("")
    metals_license_confirmed: bool = False
    source_allowlist: str = "api.metals.dev"
    request_timeout_seconds: int = Field(default=10, ge=1, le=30)
    daily_close_hour: int = Field(default=18, ge=0, le=23)
    daily_max_lag_minutes: int = Field(default=120, ge=1, le=1440)
    premium_tolerance_minutes: int = Field(default=30, ge=1, le=120)
    outlier_threshold_pct: str = "20"
    max_body_bytes: int = 16384
    rate_limit_per_minute: int = Field(default=120, ge=1, le=10000)

    @model_validator(mode="after")
    def production_database(self):
        # Also applies to `docker compose exec` / Dokploy jobs, which bypass image ENTRYPOINT.
        if self.database_password_file:
            if self.database_role is None:
                raise ValueError("DATABASE_ROLE required for secret file")
            password = self.database_password_file.read_text().strip()
            if len(password) < 24:
                raise ValueError("Database password must contain at least 24 characters")
            self.database_url = SecretStr(
                f"postgresql+psycopg://{self.database_role}:{quote(password, safe='')}@db:5432/gold"
            )
        if self.app_env == "production" and not self.database_url.get_secret_value().startswith("postgresql"):
            raise ValueError("Production yêu cầu PostgreSQL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
