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
    notion_db_assign_log: str = ""  # 프로젝트 담당 변경 이력
    notion_db_clients: str = ""  # 협력업체 (발주처 relation)
    notion_db_master: str = ""  # 마스터 프로젝트
    notion_db_suggestions: str = ""  # 건의사항
    notion_db_seal_requests: str = ""  # 날인요청

    # CORS 허용 origin (콤마 구분 raw string — pydantic_settings가 list를 JSON으로
    # 파싱하려 하므로 str로 받고 cors_origins_list로 변환)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # APScheduler 5분 sync 토글 + 인증 토큰 (외부에서 강제 트리거할 때)
    sync_enabled: bool = True
    sync_interval_minutes: int = 5
    cron_secret: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
