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

    # ── 외부 파일 storage (날인요청 첨부) ──
    storage_provider: str = "s3"  # 현재는 s3만
    storage_bucket: str = ""
    storage_region: str = "ap-northeast-2"
    storage_endpoint: str = ""  # S3 호환 (R2 등) 사용 시 채움. 빈 값이면 AWS S3 default
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_max_file_mb: int = 200

    # CORS 허용 origin (콤마 구분 raw string — pydantic_settings가 list를 JSON으로
    # 파싱하려 하므로 str로 받고 cors_origins_list로 변환)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # APScheduler 5분 sync 토글 + 인증 토큰 (외부에서 강제 트리거할 때)
    sync_enabled: bool = True
    sync_interval_minutes: int = 5
    cron_secret: str = ""

    # ── NAVER WORKS OAuth 2.0 SSO (Phase 1) ──
    # NAVER WORKS는 OIDC discovery 미지원이라 endpoint를 직접 사용.
    works_enabled: bool = False  # 롤백 스위치. true면 /auth/works/* 활성
    works_client_id: str = ""
    works_client_secret: str = ""
    works_domain_id: str = ""  # UserInfo API 응답의 domainId 비교 (다중 도메인 차단)
    works_redirect_uri: str = ""  # backend callback (env별 다름)
    works_authorize_endpoint: str = (
        "https://auth.worksmobile.com/oauth2/v2.0/authorize"
    )
    works_token_endpoint: str = "https://auth.worksmobile.com/oauth2/v2.0/token"
    works_userinfo_endpoint: str = "https://www.worksapis.com/v1.0/users/me"
    # 콤마 구분 차단 이메일 (마스터·시스템 계정 등). lower-case 비교.
    works_blocked_emails: str = "dyce@dyce.kr"

    # ── NAVER WORKS Drive (Phase 2) ──
    # 공유 드라이브 폴더 자동 생성. NAVER WORKS Drive는 user 토큰만 받으므로
    # admin이 1회 file scope 동의해 받은 토큰을 drive_credentials에 저장 후 재사용.
    works_drive_enabled: bool = False
    works_drive_redirect_uri: str = (
        "https://api.dyce.kr/api/admin/drive/callback"
    )
    works_drive_sharedrive_id: str = ""  # 공유 드라이브 자체의 ID
    works_drive_root_folder_id: str = ""  # [업무관리] 루트 폴더의 fileId
    works_api_base: str = "https://www.worksapis.com/v1.0"

    frontend_base_url: str = ""  # callback 후 frontend로 302할 때 사용

    @property
    def works_blocked_emails_set(self) -> set[str]:
        return {
            e.strip().lower()
            for e in self.works_blocked_emails.split(",")
            if e.strip()
        }

    @property
    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
