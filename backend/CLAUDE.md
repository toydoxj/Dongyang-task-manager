# backend (FastAPI + Postgres + Notion API)

## 명령어
- `source .venv/bin/activate` — venv 활성화 (uv 관리)
- `uv add 'pkg>=v'` — 의존성 추가 (pip은 PEP 668 차단)
- `uvicorn app.main:app --reload` — dev 서버 (port 8000)
- `pytest tests/ -x` — 단위 테스트 (실패 시 즉시 중단)
- `alembic heads` / `alembic upgrade head` — DB schema 적용
- `alembic revision -m "desc"` — 새 migration (file 이름 `{x}{prev}{date}_desc.py`)

## 구조
- `app/main.py` — FastAPI 앱 진입점
- `app/routers/` — endpoint (sales.py, projects.py, seal_requests.py, tasks.py, weekly_report.py, notices.py)
- `app/services/` — 비즈니스 로직 (quote_*, weekly_report, weekly_snapshot, sync, notion, sso_drive)
- `app/models/` — Pydantic + SQLAlchemy mirror models (mirror, employee, notice, snapshot, sale, project, task, weekly_publish)
- `app/templates/` — Jinja2 (quote_*.html, weekly_report.html, _schedule_mini.html)
- `alembic/versions/` — DB migrations (head 확인: `alembic heads`)

## 환경변수 (`.env`)
- `DATABASE_URL` — Postgres
- `NOTION_TOKEN` / `NOTION_DB_*` — 노션 통합
- `WORKS_DRIVE_*` — NAVER WORKS Drive (sharedrive_id / root_folder_id + OAuth)
- `WORKS_BOT_*` — NAVER WORKS Bot (service_account_id / private_key / bot_id) — 주간일지 발행 알림
- 자세히는 `app/settings.py` Settings class 참조

## 핵심 패턴
- KST timezone: `_KST = timezone(timedelta(hours=9))`
- 노션 schema 자동 등록: `notion_schema.py {SALES,TASK,PROJECT,...}_DB_REQUIRED` dict (부팅 시)
  - `relation` 타입은 자동 생성 미지원 (운영자 수동 추가 필요) — `_check_relation_present`로 부재 시 logger.warn
- 미러 동기화: `sync.py` 5분 incremental + 매뉴얼 trigger
- PDF: `quote_pdf.py build_quote_pdf` / `weekly_report_pdf.py build_weekly_report_pdf` → WeasyPrint paged media
- 주간 일지 bulk pre-fetch: `aggregate_team_work`는 mirror_tasks 한 번에 fetch + 메모리 bucket으로 N+1 회피
- 주간일지 발행: `POST /weekly-report/publish` (require_admin). PDF → Drive `[주간업무일지]` 폴더 업로드(없으면 자동 생성) → 전직원 `sso_works_bot.send_text` 순회 → `WeeklyReportPublishLog` 저장. 비admin은 `GET /weekly-report/last-published.pdf`로 마지막 발행본만 다운로드.
- role enum 검증: `auth.VALID_ROLES = {admin, team_lead, manager, member}` + `RoleUpdate.role` Literal. require_admin / require_admin_or_lead는 manager 미포함 (manager API 권한 추후 확장).
- 의존성: `holidays` lib (한국 법정공휴일·대체공휴일 자동) — `uv add 'holidays>=0.50'`
- alembic naming: `{x}{prev_short}{date}_desc.py` (예: `c8a9b0c05915_mirror_sales_start_date.py`)
