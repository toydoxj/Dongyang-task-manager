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
- `app/routers/` — endpoint (sales.py, projects.py, seal_requests.py, tasks.py)
- `app/services/` — 비즈니스 로직 (quote_calculator·quote_pdf·sync·notion·sso_drive)
- `app/models/` — Pydantic + SQLAlchemy mirror models
- `app/templates/` — Jinja2 (PDF 렌더링)
- `alembic/versions/` — DB migrations

## 환경변수 (`.env`)
- `DATABASE_URL` — Postgres
- `NOTION_TOKEN` / `NOTION_DB_*` — 노션 통합
- `WORKS_DRIVE_*` — NAVER WORKS Drive
- 자세히는 `app/settings.py` Settings class 참조

## 핵심 패턴
- KST timezone: `_KST = timezone(timedelta(hours=9))`
- 노션 schema 자동 등록: `notion_schema.py SALES_DB_REQUIRED` dict (부팅 시)
- 미러 동기화: `sync.py` 5분 incremental + 매뉴얼 trigger
- PDF: `quote_pdf.py build_quote_pdf` → WeasyPrint paged media
