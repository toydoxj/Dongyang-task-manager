# (주)동양구조 업무관리 앱 — 진행 정리

> 원천 요구사항: `PRD.md`
> 최종 갱신: 2026-05-02

## 최근 주요 변경 (2026-05-01 ~ 02)

- Electron 폐기 → 웹앱(Vercel + Render + Supabase) 단독 운영
- 노션 호출에 transient retry(429/502/503/504/timeout) 레이어 도입 + raw httpx 동일 정책
- 날인요청 전반 재정비:
  - 검토자료 폴더 명시 생성/열기/PC 경로 복사 (3개 버튼)
  - 임베디드 Drive 탐색기 (열기/새로고침/닫기/파일 삭제)
  - 자동 TASK 라이프사이클(요청자/1차/2차) + write-through로 칸반 즉시 반영
  - 팀장은 1차 단계에서만 승인·반려 가능
  - 권한별 정렬(팀장: 자기 팀 + 1차검토 우선 / admin: 전체 + 2차검토 우선)
  - 재날인요청 = 같은 row 덮어쓰기(새 row 미생성, 문서번호 유지)
- 프로젝트 상세:
  - 편집/날인요청 버튼을 제목 옆으로 이동
  - 칸반 위에 날인 현황 리스트 + 클릭 시 상세 모달 + 재날인요청
  - 라이프사이클 아래에 담당 이력 swim lane
  - TASK 칸반 기간 필터 제거(모든 완료 표시)
- 대시보드:
  - 월별 추이 = 수주/수금/지출 막대 + 12개월 선형회귀 추세선
  - 칸반 드래그는 admin 전용, 완료/타절/종결은 단계 변경 모달 자동 호출
- 내 업무:
  - 담당 프로젝트 섹션 펼치기/접기
  - 완료 TASK 표시는 '저저번 주 월요일' 이후만 (cutoff)
- Bot 알림: admin 본인 포함, 폴더 검증 알림 제거
- 휴가(연차) 분류 정상화 — 시간 지정 + 완료일 자동(=완료예정일)
- 사용자 매뉴얼 페이지(/help) 추가 (전 사용자 접근)

---

## 1. 시스템 아키텍처

```
Browser
   │  https://task.dyce.kr
   ▼
Vercel (Next.js 16, React 19)
   │  fetch → https://api.dyce.kr/api/*  (CORS)
   │
   ▼
Render Web Service (FastAPI + uvicorn, 상시)
   ├─ JWT 인증 (HS256)
   ├─ /api/* 라우터 (mirror 우선 read, write-through)
   ├─ APScheduler (5분 incremental + 매일 03:00 full reconcile)
   └─ 부팅 시 노션 schema 자동 보강
        │
        ▼
   Notion API (단일 진실 원천)
        │
        ▼
   Supabase Postgres (mirror_*, users, employees, sync_state)
```

| 영역 | 기술 |
|---|---|
| Frontend | Next.js 16.2 / React 19.2 / Tailwind 4 / SWR / @dnd-kit / Recharts / @nivo |
| Backend | FastAPI / SQLAlchemy 2 / psycopg3 / APScheduler / notion-client 3 |
| DB | Supabase Postgres (Pooled URI :6543, prepare_threshold=None) |
| Hosting | Vercel (FE) + Render Starter (BE) + Supabase Free (DB) |
| Domain | task.dyce.kr / api.dyce.kr (whois.co.kr CNAME) |

**비용**: 월 $7 (Render) + $0 (나머지 무료)

---

## 2. 도메인 모델

### Notion DB → Postgres mirror
- `mirror_projects` — 메인 프로젝트
- `mirror_tasks` — 업무 TASK (난이도 컬럼 포함)
- `mirror_clients` — 협력업체
- `mirror_master_projects` — 마스터 프로젝트
- `mirror_cashflow` — 수금 + 지출 통합 (kind 컬럼)
- `mirror_blocks` — 페이지 본문 (이미지 등)
- `notion_sync_state` — sync 진행 상태

### 자체 (노션과 무관)
- `users` — 인증/role/last_login_at
- `employees` — 직원 마스터 (엑셀 import, 이메일로 user 매칭)

---

## 3. 사용자 권한

| role | 권한 |
|---|---|
| `admin` | 전체 (직원/사용자 관리 포함) |
| `team_lead` | 일반 사용자 동일 (향후 본인 팀 권한 분리 예정) |
| `member` | 본인 데이터 |

- 관리자가 사용자 관리 페이지에서 role 변경 (드롭다운, 마지막 admin 강등 차단)
- 회원가입 시 이메일이 직원 명부에 있으면 자동 승인 + linked

---

## 4. 진행 완료 작업

### Phase 0~5 — 클라우드 전환 + 미러링
- Postgres 호환 (postgres:// 자동 정규화, PgBouncer prepare_threshold 처리)
- mirror 테이블 alembic 마이그레이션 (JSONB / ARRAY / GIN)
- NotionSyncService — incremental(last_edited_time 기준) + full reconcile
- APScheduler in-process (5분 incremental, 03:00 full)
- 라우터 read mirror 우선 + write-through (assign/update 시 mirror 즉시 upsert)
- frontend Vercel 적응 (NEXT_PUBLIC_API_BASE)
- Render/Vercel/Supabase 배포 + DNS (task / api dyce.kr)

### Master Project 모달
- 편집 form (모든 필드)
- 이미지 갤러리 + Ctrl+V 붙여넣기 업로드 (Notion file_upload API)
- Sub-Project 표시 (mirror 단일 IN 쿼리로 N+1 제거)
- 용도/구조형식/특수유형 → MultiSelectChips (자동완성 + 신규 입력 허용)

### 직원 관리 (`/admin/employees`)
- 엑셀 업로드 — 화이트리스트 컬럼만 in-memory 파싱 (연봉/실적 등 절대 저장 X)
- CRUD (이름/직급/소속/학위/자격/등급/이메일)
- 탭: 재직중 / 퇴사자 / 전체
- 퇴사 처리 (`resigned_at` 입력) / 복직 / 영구 삭제 분리
- 이메일 매칭 시 user.linked_user_id 자동 연결 (양방향)

### 사용자 관리 (`/admin/users`)
- 가입 신청 승인/거절/삭제
- role 인라인 드롭다운 (admin/팀장/일반직원, 색상 구분)
- 최근 로그인 일시 컬럼 (Asia/Seoul HH:mm)
- 탭: 승인 대기 / 활성 / 전체

### Task 관련
- 난이도 select (매우높음/높음/중간/낮음/매우낮음) — 노션 schema 자동 보강
- 등록 모달: 시작일 입력 시 완료예정일 자동 동기화 (사용자 변경값 보존)
- 다크 모드 date input picker icon 가시성 (CSS invert)

### 대시보드
- StageBoard 카드 DnD 이동 (PATCH /stage)
  - "진행중"은 자동 결정이라 drop 차단 + "자동" 배지
  - optimistic update + rollback

### 내 업무 (`/me`)
- "해야할 일" 카드 2열 grid + 프로젝트명 표시
- "마감 임박 프로젝트" 섹션 제거
- "해야할 일 ↔ 담당 프로젝트" 사이 구분선
- 프로젝트 가져오기 시 비-진행중 → 대기 자동 전환 (confirm 알림)

### 인프라/안전망
- 노션 schema 자동 보강 (부팅 시 누락 컬럼 자동 추가, idempotent)
- 노션 → Supabase write-through 라우터 패턴
- `update_data_source_schema` (raw httpx PATCH /v1/data_sources)
- `prepare_threshold=None` (Supabase PgBouncer 호환)

### 브랜드
- 회사 로고를 favicon (icon.svg) + Apple Touch Icon (apple-icon.tsx ImageResponse) + 사이드바 헤더에 적용

---

## 5. 운영 체크리스트

| 항목 | 위치 | 비고 |
|---|---|---|
| 백엔드 logs | Render Dashboard → Logs | `incremental ... 페이지 sync` 5분마다 |
| sync 상태 | Supabase Table → notion_sync_state | last_incremental_synced_at |
| 강제 sync | `POST /api/cron/sync` | Bearer CRON_SECRET |
| 노션 컬럼 추가 | `app/services/notion_schema.py` | 코드에 정의 → 배포 시 자동 보강 |
| 직원 엑셀 업로드 | /admin/employees | xlsx ≤5MB, 화이트리스트만 |
| DB 마이그레이션 | Render `uv run alembic upgrade head` | render.yaml buildCommand 자동 |

---

## 6. Electron 제거 (완료)

웹 단일화 결정에 따라 Electron 코드를 제거함:

- ✅ `electron/` 디렉토리 (main.js, preload.js, package.json) 삭제
- ✅ `backend/run.py` (PyInstaller 진입점) 삭제
- ✅ `backend/backend.spec` (PyInstaller spec) 삭제
- ✅ `frontend/next.config.ts` 단순화 (electron 분기 제거)
- ✅ `frontend/lib/types.ts` window.electronAPI / packaged 폴백 제거
- ✅ `frontend/package.json` build:electron 스크립트, cross-env devDep 제거

---

## 7. NAVER WORKS SSO (운영 중)

회사 NAVER WORKS 계정 단독 SSO. role/권한은 자체 DB. 도입 상세는 `~/.claude/plans/1-2-lovely-peach.md`.

### 정책 (2026-04-29 최신)

- **로그인은 NAVER WORKS OIDC SSO 단독.** `/auth/login`, `/auth/register`, `/auth/request`, `POST /auth/users` 라우터 제거. LoginForm은 NAVER WORKS 버튼 한 개.
- role/권한: 자체 DB에서만 관리. NAVER WORKS는 identity만.
- SSO 신규 사용자: `@dyce.kr` + `WORKS_DOMAIN_ID` 이중 검증 후 자동 `active` + `member`.
- **차단 계정**: `WORKS_BLOCKED_EMAILS` 환경변수(콤마 구분)에 등재된 이메일은 SSO 거부. 기본값 `dyce@dyce.kr` (마스터 계정). 기존 DB의 dyce 사용자는 Alembic `l1j2k3l40209`로 `status='rejected'` 강등.
- 자체 `employees` 테이블: 즉시 폐기 안 함. Directory API 도입은 Phase 2 이후.
- Bot / Calendar / Drive / Approval / Mail: Phase 1 안정화 결과 보고 별도 계획.

### 운영 토글 (Render dashboard)

| Key | 의미 |
|---|---|
| `WORKS_ENABLED` | true/false. SSO 비활성 시 `/auth/works/*`가 503, 프론트는 안내 문구 표시 |
| `WORKS_BLOCKED_EMAILS` | 차단 이메일 콤마 리스트 (소문자 비교) |
| `WORKS_CLIENT_ID` / `WORKS_CLIENT_SECRET` / `WORKS_DOMAIN_ID` | NAVER WORKS Developer Console 발급값 |

### Phase 0 (1주) — 사전 준비

- NAVER WORKS Developer Console 앱 등록(스테이징/프로덕션), scope `openid email profile`
- 환경변수 7개 추가: `WORKS_CLIENT_ID`, `WORKS_CLIENT_SECRET`, `WORKS_DOMAIN_ID`, `WORKS_REDIRECT_URI`, `WORKS_ISSUER`, `WORKS_ENABLED`, `FRONTEND_BASE_URL`
- Supabase `users` 데이터 점검 (이메일 누락 / `@dyce.kr` 외부 도메인 정리)
- Render staging 서비스 추가 (스테이징 검증 1주 후 production)

### 구현 요약 (현재 운영 중)

- `users` 컬럼: `works_user_id` UNIQUE INDEX, `auth_provider`, `sso_login_at` (Alembic `k0i1j2k30208`)
- 마스터 계정 강등: Alembic `l1j2k3l40209`로 `dyce@dyce.kr` `status='rejected'`
- `backend/app/services/sso_works.py`: code 교환 + UserInfo API(`/v1.0/users/me`) 호출 + signed state(HMAC) + `upsert_user(blocked_emails)`
- 라우터: `/api/auth/works/login`, `/api/auth/works/callback` (cookie 비사용 — signed state)
- 프론트: `LoginForm`은 NAVER WORKS 버튼 단독, `app/auth/works/callback/page.tsx` + server layout(`force-dynamic`)
- 보안: `@dyce.kr`, `WORKS_DOMAIN_ID`, signed state HMAC-SHA256 + 10분 TTL, 차단 이메일 리스트, fragment redirect + `history.replaceState`

### 본 phase에서 하지 않는 것

- Bot / Calendar / Approval / Mail API
- `employees` 폐기 / Directory API 동기
- Notion 도메인 변경

---

## 7.A. NAVER WORKS Drive — 프로젝트별 폴더 자동 생성 (Phase 2, 진행 중)

상세: `docs/NAVER_WORKS_DRIVE_PLAN.md` + 코드는 `backend/app/services/sso_drive.py`

### 정책 (2026-04-29 갱신 — Service Account → admin user-token 위임)

> NAVER WORKS Drive API가 Service Account JWT를 거부 (`Not allowed api`).
> Drive API는 user 토큰만 받음(공식 문서 명시) → admin 1명이 1회 동의 + 토큰 보관 방식.

- **인증**: admin이 1회 file scope 동의 → access_token + refresh_token 보관 → 자동 갱신
- **트리거**: 프로젝트 생성 시 BackgroundTasks로 자동 폴더 생성. 실패해도 응답에 영향 X
- **폴더 구조**: `[업무관리]/[CODE]프로젝트명/{1.건축도면, 2.구조도면, 3.구조계산서, 4.구조해석및설계, 5.문서(심의자료 등), 6.계약서, 7.기타}`
- **idempotent**: 같은 이름 폴더 있으면 재사용 (URL만 다시 저장)
- **저장 위치**: 노션 메인 프로젝트 DB의 `WORKS Drive URL` 컬럼 (자동 schema 보강)
- **재시도**: admin 전용 `POST /api/projects/{id}/works-drive` + `ProjectHeader`의 "📁 Drive 폴더 만들기" 버튼

### 구현 요약

| 영역 | 파일 |
|---|---|
| Service Account JWT + token 캐시 + Drive API helper | `backend/app/services/sso_drive.py` |
| 환경변수 6개 (ENABLED/SA_ID/PRIVATE_KEY/SHAREDRIVE_ID/ROOT_FOLDER_ID/API_BASE) | `backend/app/settings.py`, `backend/render.yaml` |
| 노션 schema 자동 보강 | `backend/app/services/notion_schema.py` PROJECT_DB_REQUIRED |
| 프로젝트 생성 hook + admin 재시도 라우터 | `backend/app/routers/projects.py` |
| URL property 추출 | `backend/app/services/notion_props.py` `url()` |
| Project DTO `drive_url` 필드 | `backend/app/models/project.py`, `frontend/lib/domain.ts` |
| "WORKS Drive 열기" / "Drive 폴더 만들기" 버튼 | `frontend/components/project/ProjectHeader.tsx` |
| PoC 스크립트 (사전 검증용) | `scripts/works_drive_poc.py` |

### 사용자 사전 작업 (필요)

1. NAVER WORKS Developer Console → 앱에 `file` scope 추가
2. **Service Account 발급** + Private Key (PEM) 다운로드
3. WORKS 공용 드라이브에 `[업무관리]` 폴더 생성 + 회사 권한 부여
4. Render 환경변수 6개 등록 (`WORKS_DRIVE_ENABLED=true`, `WORKS_SERVICE_ACCOUNT_ID`, `WORKS_PRIVATE_KEY`, `WORKS_DRIVE_SHAREDRIVE_ID`, `WORKS_DRIVE_ROOT_FOLDER_ID`)
5. 로컬에서 `scripts/works_drive_poc.py` 실행해 응답 schema 확인

### PoC에서 확정해야 할 항목

- Drive folder 생성 endpoint 정확한 path (`/sharedrives/{sd}/files` vs `/sharedrives/{sd}/files/{parent}/children` 등)
- 응답 JSON 키 이름 (`fileId`, `webUrl` 등)

PoC 결과로 `sso_drive.py`의 `_api(...)` path와 `_extract_id`/`_extract_url` 키를 단일 path로 정착.

---

## 8. 향후 가능한 작업 (참고)

- 팀장 권한 실제 적용 (본인 팀 task 보기/편집)
- 노션 webhook 도입 (5분 cron → 즉시 sync)
- 모바일 PWA (manifest.json + service worker)
- 회원가입 시 직원 이메일 도메인 화이트리스트 (보안)
- 차트 ResponsiveContainer minHeight 강제 (콘솔 noise 제거)
