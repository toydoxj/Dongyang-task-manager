"""환경변수 통합 설정 (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    database_url: str = "sqlite:///./data/app.db"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    notion_api_key: str = ""
    notion_db_projects: str = ""
    notion_db_tasks: str = ""
    notion_db_cashflow: str = ""
    notion_db_expense: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
