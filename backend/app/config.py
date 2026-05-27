"""
Centralized config loaded from environment variables.

Using pydantic-settings so misconfigured envs fail fast at startup with a
clear validation error, rather than crashing on first DB call.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (write path: storefront orders)
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "shop"
    postgres_user: str = "cdc_user"
    postgres_password: str = "cdc_pass"

    # ClickHouse (read path: admin metrics)
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 9000           # native protocol
    clickhouse_db: str = "analytics"
    clickhouse_user: str = "default"
    clickhouse_password: str = "clickpass"

    # CORS — the frontend served from port 3000 in dev
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",  # vite dev server default
    ]


settings = Settings()
