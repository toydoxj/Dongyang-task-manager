# 동양구조 업무관리

(주)동양구조 구성원의 프로젝트·업무·날인요청을 관리하는 사내 웹 애플리케이션.

- **운영 URL**: https://task.dyce.kr
- **요구사항**: [PRD.md](./PRD.md)
- **상세 계획**: [PLAN.md](./PLAN.md)
- **사용자 매뉴얼**: [docs/USER_MANUAL.md](./docs/USER_MANUAL.md)
- **배포 가이드**: [docs/DEPLOY.md](./docs/DEPLOY.md)

## 구성

| 디렉토리 | 역할 |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + JWT 인증 + Notion/NAVER WORKS 연동 |
| `frontend/` | Next.js 16 (App Router) + Tailwind 4 + SWR + 차트(Recharts/Nivo) |
| `scripts/` | 개발/유지보수 보조 스크립트 (스키마 점검, Drive POC 등) |
| `docs/` | 사용자 매뉴얼·배포 가이드·기능 명세 |
| `_reference/` | 참조 저장소 (clone, 배포 제외) |

## 아키텍처

```
Browser (task.dyce.kr)
   ▼
Vercel (Next.js 16)
   │  fetch → https://api.dyce.kr/api/*
   ▼
Render Web Service (FastAPI)            ◀── Render Cron (5분 incremental, 매일 03:00 full)
   ├─ JWT 인증 (HS256) + NAVER WORKS SSO
   ├─ /api/* 라우터 (Postgres mirror 우선 read, write-through)
   └─ 노션 호출 (transient 502/503 retry, batch streaming)
        │
        ▼
   Notion API (단일 진실 원천)
   Supabase Postgres (mirror_*, users, employees)
   NAVER WORKS Drive / Bot (첨부 폴더 / 알림)
```

| 영역 | 기술 |
|---|---|
| Frontend | Next.js 16.2 / React 19 / Tailwind 4 / SWR / @dnd-kit / Recharts / Nivo |
| Backend | FastAPI / SQLAlchemy 2 / psycopg3 / APScheduler / notion-client 3 / httpx |
| DB | Supabase Postgres (Pooled URI :6543) |
| Hosting | Vercel (FE) + Render Starter (BE/Cron) + Supabase Free (DB) |
| Domain | `task.dyce.kr` (FE) / `api.dyce.kr` (BE) |

## 개발 모드

> 사전 요구사항: Node.js 20+, Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. 환경변수 준비
cp backend/.env.example backend/.env
# .env 편집 (JWT_SECRET, NOTION_API_KEY, NOTION_DB_*, WORKS_*, DATABASE_URL 등)

# 2. 백엔드 (port 8000)
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 3. 프론트엔드 (port 3000, 별도 터미널)
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:3000` 접속.

## 운영/배포

배포 가이드는 [`docs/DEPLOY.md`](./docs/DEPLOY.md) 참고. 요약:

- main 브랜치 push → Vercel + Render 자동 빌드/배포
- DB 마이그레이션은 `backend/alembic` 으로 별도 트리거
- 환경 변수는 각 플랫폼 dashboard에서 관리

## 작업 지침

- 본 프로젝트의 작업 절차/지침은 [`claude.md`](./claude.md)를 따른다.
- Python 작업은 `backend/.venv` 가상환경 내에서 수행.
- 발생 에러는 `.claude/rule/error.md`에 기록해 반복 방지.
