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
        # CRLF 줄바꿈이 섞인 .env 파일에서 trailing \r이 값에 포함되는 문제 방지.
        # 모든 string 필드에 .strip()을 자동 적용 (pydantic v2 기능).
        str_strip_whitespace=True,
    )

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    # 30일. SSO 사용자가 매일 인증 안 해도 되도록 길게.
    # 다른 기기 로그인 시 session_id 메커니즘이 자동 무효화하므로 risk는 제한적.
    jwt_expire_minutes: int = 43200

    database_url: str = "sqlite:///./data/app.db"
    # 운영은 alembic이 schema 처리. dev/test에서만 init_db() 자동 실행.
    # AUTO_CREATE_TABLES=true env 또는 .env로 켤 수 있음.
    auto_create_tables: bool = False

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
    # 프로젝트 계약 항목 (공동수급/추가용역 — 1프로젝트 N발주처 N금액)
    notion_db_contract_items: str = ""
    # 영업 파이프라인 (수주영업 + 기술지원). 견적서 DB를 확장한 형태
    notion_db_sales: str = ""

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
    works_drive_sharedrive_id: str = ""  # 공유 드라이브 자체의 ID
    works_drive_root_folder_id: str = ""  # [업무관리] 루트 폴더의 fileId
    # PR5 견적서 작성 툴 — 견적서 xlsx 자동 저장 위치 ([견적서] 폴더 fileId).
    # 코드가 그 아래 "{YYYY}년" 폴더를 idempotent 생성하고 xlsx 업로드.
    works_drive_quote_root_folder_id: str = ""
    works_api_base: str = "https://www.worksapis.com/v1.0"
    # NAVER WORKS Drive 탐색기 가상 드라이브 마운트 경로 (옵션).
    # 설정하면 frontend가 "탐색기에서 열기" / "PC 경로 복사" 버튼을 표시.
    # 예: "W:\\공유 드라이브\\[업무관리]" 또는 "W:\\[업무관리]"
    works_drive_local_root: str = ""

    # ── NAVER WORKS Calendar (Phase 3 — task 동기화) ──
    # 회사 공유 캘린더 ID. /api/admin/calendar/create-shared-calendar로 1회 생성 후
    # 응답의 calendar_id를 Render env에 저장. Drive와 같은 토큰(scope: file calendar)
    # 사용하므로 별도 자격 증명 불필요.
    works_calendar_enabled: bool = False
    works_shared_calendar_id: str = ""

    # ── NAVER WORKS Bot (Phase 4 — 날인요청 알림) ──
    # Bot은 Drive와 별개의 인증 흐름 (Service Account JWT, RS256).
    # Developer Console → App에 Bot 등록 + Service Account 생성 + Private Key(PEM) 발급.
    # WORKS_BOT_PRIVATE_KEY는 PEM 전체를 그대로 (\\n 포함). Render는 multiline 환경변수
    # 지원하므로 그대로 붙여넣기.
    works_bot_enabled: bool = False
    works_bot_id: str = ""  # 콘솔에서 발급된 Bot ID
    works_bot_service_account_id: str = ""  # 예: xxxxx.serviceaccount@<domain>
    works_bot_private_key: str = ""  # PEM 전체

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


def validate_runtime_settings() -> None:
    """운영 시작 시 위험한 default 차단. lifespan 진입에 호출."""
    s = get_settings()
    if not s.jwt_secret or s.jwt_secret == "change-me-in-production":
        raise RuntimeError(
            "JWT_SECRET 환경변수가 설정되지 않았습니다 — "
            "Render Environment 또는 .env에 임의의 secret 입력 필요"
        )
    # Bot 알림이 켜져 있는데 자격이 없으면 startup 실패. 켜지 않았으면 무시.
    if s.works_bot_enabled:
        missing = [
            k
            for k, v in {
                "WORKS_BOT_ID": s.works_bot_id,
                "WORKS_BOT_SERVICE_ACCOUNT_ID": s.works_bot_service_account_id,
                "WORKS_BOT_PRIVATE_KEY": s.works_bot_private_key,
                "WORKS_CLIENT_ID": s.works_client_id,
                "WORKS_CLIENT_SECRET": s.works_client_secret,
            }.items()
            if not v
        ]
        if missing:
            raise RuntimeError(
                "WORKS_BOT_ENABLED=true인데 다음 환경변수가 누락됨: "
                + ", ".join(missing)
            )
