# 배포 가이드 (관리자용)

> Vercel(Frontend) + Render(Backend + Cron) + Supabase(DB) 운영 환경 기준.

## 운영 도메인

- Frontend: `https://task.dyce.kr` (Vercel)
- Backend API: `https://api.dyce.kr` (Render Web Service)
- DB: Supabase Postgres (Pooled URI :6543)
- Notion API: `api.notion.com`
- NAVER WORKS API: `worksapis.com`

## 배포 흐름 (자동)

```
GitHub main push
   ├─ Vercel 자동 빌드 → Frontend 배포 (~3-7분)
   └─ Render 자동 빌드 → Backend 재시작 (~3-5분)

Render Cron Job (별도 컨테이너)
   └─ 5분마다 sync_once incremental, 매일 03:00 KST full reconcile
```

`main` 브랜치에 push만 하면 Frontend·Backend 모두 자동 배포. 정상이라면 추가 작업 불필요.

## 배포 실패 대응

### Vercel 빌드 실패
- TypeScript 에러로 막히는 케이스가 가장 흔함
- 로컬에서 `cd frontend && npx tsc --noEmit` 으로 사전 점검 권장
- 대시보드 → Deployments → 최신 deployment 클릭 → 빌드 로그 확인

### Render 빌드 실패
- Python deps 충돌 / `uv sync` 실패
- 대시보드 → Logs / Events 탭에서 stdout 확인

### 자동 배포가 트리거 안 됨
- Vercel: Settings → Git → Production Branch가 `main`인지 확인
- Render: Settings → Build & Deploy의 connection 상태 확인
- 임시 우회: 대시보드에서 **「Redeploy」** 또는 빈 commit push (`git commit --allow-empty`)

### 캐시 문제
- 사용자가 새 코드를 못 보면 강력 새로고침 (`Ctrl+Shift+R`) 안내
- Vercel CDN이 stale HTML을 서빙 → Vercel deployment의 **「⋯ → Redeploy」**(Use existing Build Cache 해제)

## 환경 변수

### Backend (Render)
- 운영 backend의 모든 비밀값은 Render 대시보드 → Environment 에서 관리.
- `WORKS_BOT_ENABLED=true`인 경우 다음이 모두 채워져야 startup이 실패 안 함:
  - `WORKS_BOT_ID`, `WORKS_BOT_SERVICE_ACCOUNT_ID`, `WORKS_BOT_PRIVATE_KEY` (PEM 전체)
  - `WORKS_CLIENT_ID`, `WORKS_CLIENT_SECRET`
- 노션 DB ID 변경 시 `NOTION_DB_*` 갱신 후 Manual Deploy.
- `JWT_SECRET` 은 절대 `change-me-in-production` 으로 두지 말 것 (startup validate에서 차단됨).

### Frontend (Vercel)
- `NEXT_PUBLIC_API_BASE` 또는 그에 해당하는 변수가 `https://api.dyce.kr` 을 가리키게.
- 변경 후 **재배포 필요** (env 변경만으론 즉시 반영 안 됨).

### Cron (Render Cron Service)
- backend Web Service와 **동일한 Environment 변수** 사용.
- `cron service` 타입은 schedule cron 표현식으로 5분마다 + 매일 03:00 동작.

## DB 마이그레이션 (Alembic)

```bash
cd backend
uv sync
# 운영 DATABASE_URL을 환경에 export 후
PYTHONUTF8=1 uv run alembic upgrade head
```

운영에 그대로 적용하기 전에 `alembic upgrade --sql` 로 SQL 미리 검토 권장. Supabase는 자동 백업이 없으니 마이그레이션 전 수동 dump.

## 노션 schema 변경

노션 DB에 컬럼을 추가했는데 코드에서 참조하면 backend 부팅 시 자동 보강 (`notion_schema.py`). 그래도 새 multi_select 옵션을 프론트에서 추가 입력하려는 경우 노션이 거부할 수 있어 다음 sync에 자동 union 됨.

## NAVER WORKS Drive 자격증명

운영에서 admin이 한 번 OAuth 동의 후 `drive_credentials` 테이블에 access/refresh token이 저장. 만료 시 자동 refresh. refresh마저 실패하면 관리자가 다시 한 번 OAuth 화면을 통과해야 함.

확인:
- Backend → `/api/admin/drive/auth-url` → 받은 URL 방문 → 동의 → callback 처리
- Render 로그에 `drive_credentials updated` 메시지 확인

## 노션 sync transient 502

노션 API 502/503/504/429는 자동 retry (max 4회, deadline 60초). Render 로그에 다음 키워드:
- `notion retry op=... attempt=2/4 status=502 ...`
- `notion recovered op=... attempt=3/4 ...`
- `notion give up ...` ← 이게 자주 보이면 max_attempts 또는 deadline 상향 검토

## 모니터링

- **Render Metrics**: 메모리(512MB 한도) / CPU. OOM kill 시 backend가 재시작.
- **Vercel Analytics**: 페이지 로드, error rate.
- **Supabase**: 커넥션 풀 사용량 (Pooled URI 권장).

## 롤백

문제가 생긴 배포는 다음 방법으로 빠르게 되돌리기:

- **Vercel**: Deployments 목록 → 이전 정상 배포 → **「⋯ → Promote to Production」**
- **Render**: Deploys 목록 → 이전 deploy → **「Rollback」**
- **DB 마이그레이션**: `alembic downgrade -1` (다만 데이터 손실 위험 — 복구 어려움)

## 변경 이력 / 이슈 추적

- 코드 이력: GitHub `main` 브랜치 commit log
- 운영 이슈 / 에러 사례: `.claude/rule/error.md` (반복 방지용 학습 기록)
- 기능 명세: `docs/request.md` (날인요청), `docs/bot_trigger.md` (Bot 알림), `docs/NAVER_WORKS_*.md` (외부 연동)
