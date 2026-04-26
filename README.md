# 동양구조 업무관리 앱

(주)동양구조 구성원의 프로젝트 진행현황 관리를 위한 Electron 데스크톱 앱.

- **요구사항**: [PRD.md](./PRD.md)
- **상세 계획**: [PLAN.md](./PLAN.md)
- **참조 저장소**: https://github.com/toydoxj/DY_MIDAS_PROJECT

## 구성

| 디렉토리 | 역할 |
|---|---|
| `backend/` | FastAPI + SQLite + JWT 인증 + Notion 연동 |
| `frontend/` | Next.js + shadcn/ui 대시보드 |
| `electron/` | Electron 셸 + Python sidecar 기동 |
| `scripts/` | 개발/배포 보조 스크립트 |
| `docs/` | 사용 매뉴얼 등 |
| `_reference/` | 참조 저장소 (clone, 빌드 제외) |

## 빠른 시작 (개발 모드)

> 사전 요구사항: Node.js 20+, Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. 환경변수 준비
cp .env.example .env
# .env 편집 (JWT_SECRET, NOTION_API_KEY 등)

# 2. 백엔드
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 3. 프론트엔드 (별도 터미널)
cd frontend
npm install
npm run dev

# 4. Electron (별도 터미널)
cd electron
npm install
npm run dev
```

## 지침

- 본 프로젝트의 작업 절차/지침은 [`claude.md`](./claude.md)를 따른다.
- 모든 Python 작업은 `backend/.venv` 가상환경 내에서 수행한다.
- 발생 에러는 `.claude/rule/error.md`에 기록한다.
