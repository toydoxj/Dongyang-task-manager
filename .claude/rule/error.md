# 에러 로그 (반복 방지용)

> claude.md 지침: 발생한 에러는 본 파일에 기록하여 반복되지 않도록 한다.

## 형식

```
### YYYY-MM-DD — 짧은 제목
- 컨텍스트: 어떤 작업 중에 발생했는가
- 증상: 에러 메시지/현상
- 원인: 근본 원인
- 해결: 어떻게 고쳤는가
- 재발 방지: 다음에 어떻게 피할 것인가
```

---

### 2026-04-26 — `.claude/rule`가 디렉토리가 아닌 빈 파일로 생성됨
- 컨텍스트: 프로젝트 초기화 중 `.claude/rule/error.md` 생성 시도
- 증상: `mkdir: cannot create directory '.claude/rule': File exists`
- 원인: 이전 세션에서 `rule`이 0바이트 파일로 생성되어 있었음
- 해결: 빈 파일 삭제 후 `mkdir -p`로 디렉토리 생성
- 재발 방지: 디렉토리 생성 전 `ls -la`로 동일 이름 파일 존재 여부 확인

### 2026-04-26 — packaged backend.exe가 Program Files data 디렉토리 생성 시 권한 거부
- 컨텍스트: NSIS 설치 후 첫 실행 — backend.exe가 `Program Files\dongyang-task-electron\resources\backend\data` 만들려다 실패
- 증상: `PermissionError: [WinError 5] 액세스가 거부되었습니다`, exit code 1
- 원인: run.py가 BACKEND_DATA_DIR 미설정 시 fallback을 `exe_dir/data`로 두어 read-only 위치 시도
- 해결:
  1) electron/main.js spawn env에 `BACKEND_DATA_DIR: app.getPath("userData")` 명시 전달
  2) run.py fallback도 `%LOCALAPPDATA%\동양구조 업무관리\data`로 강화
- 재발 방지: PyInstaller로 sidecar 만들 때 데이터 디렉토리는 절대 설치 위치(Program Files)에 의존하지 말 것. Electron이 항상 userData 경로를 명시 전달.

### 2026-04-26 — packaged frontend가 backend random port에 접근 못 함 (Failed to fetch)
- 컨텍스트: 설치 후 UI는 떴으나 모든 API 호출이 "Failed to fetch"
- 증상: 대시보드 빨간 에러 박스 "Failed to fetch"
- 원인: frontend의 `API_BASE`를 빌드 시점에 `process.env.NEXT_PUBLIC_API_BASE` (= `http://127.0.0.1:8000`)로 인라인. packaged 환경에서 backend는 `getFreePort()`로 랜덤 포트(예: 56727) 사용 → 8000으로 보낸 요청 모두 fail
- 해결: lib/types.ts의 `API_BASE`를 client-side에서 `window.location.origin` 사용하도록 동적 계산. backend가 frontend도 정적 서빙하므로 같은 origin으로 호출 가능
- 재발 방지: Electron sidecar + 정적 frontend 패턴에서 환경변수를 빌드 시점에 인라인 금지. client에서 런타임 `window.location.origin` 사용. dev에서는 별도 분기.

### 2026-04-26 — 노션 API 응답 지연 → Postgres 미러 캐싱 도입
- 컨텍스트: 모든 read endpoint가 노션 직접 호출 → 페이지당 1~3초. MasterProjectModal sub-project N+1, list_projects의 client/master title lookup 누적 호출
- 증상: UI 진입마다 1~3초 로딩, 클릭마다 추가 지연
- 원인: 노션 API 자체 200~800ms + RateLimiter 0.4초 + TTLCache 30초로 사실상 매번 cache miss
- 해결:
  1) `app/services/sync.py` NotionSyncService — 노션 → mirror_* 테이블 upsert
  2) `app/services/scheduler.py` APScheduler 5분 incremental + 1일 03:00 full reconcile
  3) read 라우터 모두 mirror 조회로 전환
  4) write 라우터는 노션 update 직후 sync.upsert_page (write-through)
  5) MasterProjectModal sub-project N+1 → mirror_projects 단일 IN 쿼리
- 재발 방지: 외부 API에 의존하는 read는 항상 mirror/cache 레이어 우선. 미러 부재 시만 fallback fetch + upsert.

### 2026-04-29 — NAVER WORKS Drive 폴더 생성: file과 folder는 별도 endpoint
- 컨텍스트: ensure_project_folder가 [업무관리] sharedrive에 [CODE]프로젝트명 폴더 자동 생성. 처음 `POST /sharedrives/{sd}/files` 사용
- 증상: NAVER WORKS Drive 웹에서 "유형: 파일", 0KB로 표시. list 응답의 `fileType: "ETC"`. 모든 sub 폴더가 sharedrive root에 평면 배치
- 원인: NAVER WORKS Drive는 file과 folder 생성 endpoint가 분리되어 있음. `/files`는 일반 파일 업로드용(fileSize·uploadUrl 흐름), 폴더는 별도 path
- 해결: 공식 spec endpoint 두 개로 분리
  - root에 폴더: `POST /sharedrives/{sd}/files/createfolder` body=`{"fileName":"..."}`
  - sub-folder: `POST /sharedrives/{sd}/files/{parentFileId}/createfolder`
  - 응답 201에 fileId/parentFileId/fileType="FOLDER" 즉시 포함 (PUT 추가 단계 불필요)
- 재발 방지: NAVER WORKS Drive API 패턴 — file과 folder는 항상 별도 path. 새 작업 시 공식 reference의 endpoint 이름 정확히 확인. `/files`는 file 전용

### 2026-04-29 — NAVER WORKS Drive API spec 페이지가 JS SPA라 raw fetch로 본문 안 보임
- 컨텍스트: developers.worksmobile.com의 endpoint·body schema 확인 시도
- 증상: WebFetch·curl 모두 `<title>Developers</title>` 비슷한 SPA 빈 shell만 반환. 본문은 JS 렌더링 후에야 채워짐
- 원인: 사이트가 React/Vue SPA. raw HTML에 spec 본문 없음
- 해결: Playwright MCP의 `browser_navigate` + `browser_evaluate`로 실제 브라우저 렌더링 후 `document.querySelector('main').innerText` 추출
- 재발 방지: NAVER WORKS·NAVER Cloud 등 한국형 SPA 개발자 사이트의 본문이 필요하면 처음부터 Playwright MCP 사용. WebFetch 시간 낭비 금지

### 2026-04-29 — NAVER WORKS Drive API는 user 토큰만 받음 (Service Account JWT 차단)
- 컨텍스트: `[업무관리]` 공유 드라이브에 폴더 자동 생성 자동화 — Service Account JWT 사용 시도
- 증상: token 발급은 정상(scope=file 부여), 그러나 모든 Drive API 호출이 `403 {"code":"FORBIDDEN","description":"Not allowed api"}`. JWT의 sub claim에 admin user를 넣어 impersonation 시도해도 `UserId or client_id is not valid` (400)
- 원인: NAVER WORKS Drive API는 사용자 OAuth 토큰만 인정. Service Account JWT는 Bot/일부 admin API에만 유효. 도메인 위임(domain-wide delegation)도 미지원
- 해결: admin이 1회 user OAuth 동의 → access_token + refresh_token을 `drive_credentials` (id=1 single row)에 저장 → 만료 60초 전부터 자동 refresh. 주체 admin 1명이 회사 전체 자동화 토큰 보유
- 재발 방지: NAVER WORKS API 사용 시 처음에 endpoint별 인증 모델 확인. `auth-jwt` 페이지에 사용 가능한 API 명시되어 있음. Drive·Calendar 등 user-facing API는 거의 모두 user 토큰. Bot/일부 admin API만 Service Account 가능

### 2026-04-29 — NAVER WORKS Drive 공유 드라이브 ID는 web URL의 resourceLocation이 아님
- 컨텍스트: 사용자가 NAVER WORKS Drive 웹의 공유 폴더 URL을 보내고 우리가 sharedrive ID 추출
- 증상: URL의 `resourceLocation=24101` 을 `WORKS_DRIVE_SHAREDRIVE_ID`로 사용 → Drive API가 `404 DRIVE_FOLDER_NOT_EXIST`
- 원인: `resourceLocation`은 NAVER WORKS internal storage location code(int32)일 뿐. 실제 sharedrive ID는 `@<숫자>` 형식 (예: `@2001000000536760`). web URL의 `resourceKey` 첫 segment를 base64 디코드하면 그 ID가 나옴
- 해결: `GET /sharedrives` (인증된 user 토큰)으로 ID 없는 list 호출 → 응답의 `sharedriveId` 필드가 진짜 ID. PoC가 자동 list로 발견하도록
- 재발 방지: NAVER WORKS Drive web URL의 query는 ID가 아닌 internal code. API용 ID는 항상 `/sharedrives` list로 확인. PoC 스크립트에 list-then-match 패턴 내장

### 2026-04-29 — NAVER WORKS는 OIDC discovery(/.well-known/openid-configuration) 미지원
- 컨텍스트: SSO 도입 시 `authlib`의 OIDC discovery로 endpoint 자동 검색 시도
- 증상: 첫 호출 `/.well-known/openid-configuration` → 404 → 예외가 catch되지 않은 채 500 Internal Server Error
- 원인: NAVER WORKS는 OIDC discovery URI를 표준 path로 노출하지 않음. id_token 검증 등 OIDC 기능을 부분 지원하지만 discovery는 안 함
- 해결:
  1. discovery 호출 폐기. authorize/token/userinfo endpoint를 `settings`에 직접 박음 (default값으로 `https://auth.worksmobile.com/oauth2/v2.0/{authorize,token}`, `https://www.worksapis.com/v1.0/users/me`)
  2. id_token RS256+JWKS 검증 대신 access_token으로 UserInfo API 호출 (단순화)
- 재발 방지: NAVER WORKS는 표준 OIDC와 부분 호환만. discovery·JWKS 같은 OIDC 부가 기능 의존 금지. endpoint 직접 사용

### 2026-04-29 — Render `value:`로 박은 환경변수가 dashboard 값을 매 빌드마다 덮어씀
- 컨텍스트: render.yaml에 `WORKS_ENABLED: value: "false"`로 등록. 사용자가 dashboard에서 `true`로 변경
- 증상: `/api/auth/status` 응답 `works_enabled: false`. dashboard 값이 적용 안 됨
- 원인: Render Blueprint는 `value:`로 명시한 환경변수가 권위(authoritative). 매 빌드마다 dashboard 값을 render.yaml의 value로 동기화함. 운영자 토글이 무력화됨
- 해결: 운영자가 토글하는 변수는 `sync: false`로 등록. dashboard 값이 권위가 됨. value:는 항상 일정한 값(예: 도메인 URL)에만 사용
- 재발 방지: render.yaml 환경변수 분류
  - `value:` — 변경 일이 없는 정적 설정 (URL, 일정한 라이브러리 버전 등)
  - `sync: false` — 운영자가 dashboard에서 토글하는 모든 것 (시크릿, ENABLED 플래그 등)

### 2026-04-29 — PEM private key 환경변수 inline은 줄바꿈 손상으로 MalformedFraming
- 컨텍스트: Service Account JWT 흐름에서 RSA private key를 `WORKS_PRIVATE_KEY` 환경변수에 직접 입력 시도 (Phase 2 초안에서 한 작업, Service Account 폐기로 결국 미사용)
- 증상: `jose.exceptions.JWKError: Unable to load PEM file ... MalformedFraming`. raw 길이 20자, BEGIN/END 마커 누락
- 원인: 사용자가 PEM을 .env에 inline 넣을 때 `\n` literal·따옴표·multi-line 처리 등이 dotenv·shell·Render UI 사이에서 깨짐. PEM의 strict 형식(64자 줄바꿈, BEGIN/END 헤더) 보존 어려움
- 해결: PEM은 파일로 보관 + `WORKS_PRIVATE_KEY_PATH=data/works_sa.key` 같은 path 환경변수만 사용 (.gitignore에 `*.key`/`backend/data/` 등재됨). 또는 코드에서 `_normalize_pem()` 같은 robust 복원 helper
- 재발 방지: PEM·private key는 환경변수에 inline 금지. 파일 path 또는 시크릿 매니저(AWS Secrets Manager·Vault 등) 권장. Render에서 multi-line value를 다루려면 base64 encode 후 디코드도 가능

### 2026-04-29 — SSO callback의 SameSite=Lax cookie가 cross-site redirect에서 누락
- 컨텍스트: SSO 흐름에서 state·nonce를 cookie로 보존, callback에서 검증
- 증상: 사용자가 NAVER WORKS 인증 마치고 우리 callback에 도착하면 `state 쿠키 누락` 에러. 브라우저·시크릿 모드·시간 경과 등 환경에 따라 간헐 재현
- 원인: NAVER WORKS authorize 페이지(cross-site)에서 우리 callback으로 redirect할 때 SameSite=Lax cookie가 일부 브라우저 정책에서 누락. SameSite=Strict는 100% 거부. None은 third-party cookie 차단 정책 충돌 가능
- 해결: cookie 자체를 폐기. **HMAC-SHA256 signed state token**으로 전환:
  - state payload: `{"n":nonce, "t":ts, "x":next, "d":drive?}` → JSON → base64url
  - signature: `HMAC-SHA256(jwt_secret, payload_b64)` → base64url
  - state token: `payload.sig`
  - callback이 sig 검증 + 10분 TTL 확인. cookie 0개로 stateless
- 재발 방지: OAuth state CSRF 방어에 cookie 의존 금지. signed token이 표준이고 모든 브라우저 환경에서 동작. `next` path도 state에 embed해 cookie 흐름 단순화

### 2026-04-29 — Vercel edge cache가 SSO callback 페이지 옛 SSR을 HIT으로 반환
- 컨텍스트: Next.js client 컴포넌트로 만든 `/auth/works/callback` 페이지. 빌드 후에도 옛 코드가 보임
- 증상: 새 빌드 Ready인데 callback 페이지에 옛 fallback 텍스트("로딩 중...") 표시. `curl -i`로 확인 시 `x-vercel-cache: HIT`
- 원인: callback 페이지의 SSR HTML이 edge cache. 새 빌드 chunk hash가 변경됐지만 cache는 옛 응답 유지. `useSearchParams` 등 dynamic API를 client에서만 호출하면 페이지 자체는 SSG/ISR로 인식돼 cache됨
- 해결: server layout으로 dynamic 강제
  ```tsx
  // app/auth/works/callback/layout.tsx
  export const dynamic = "force-dynamic";
  export const revalidate = 0;
  ```
  매 요청 fresh, edge cache HIT 차단
- 재발 방지: SSO callback·webhook receiver 등 fragment·query에 의존하는 페이지는 항상 server layout에서 `force-dynamic` 명시. client `"use client"`만으로는 cache 차단 불충분

### 2026-04-29 — AuthGuard가 SSO callback path를 가로채 LoginForm 재진입
- 컨텍스트: AuthGuard가 `AppShell`에서 모든 페이지를 감싸는 구조. `isLoggedIn()`이 false면 LoginForm 렌더
- 증상: SSO 콜백에서 fragment 파싱이 시작되기도 전에 AuthGuard가 phase=login으로 전환 → 사용자가 callback 페이지 못 보고 다시 LoginForm
- 원인: AuthGuard의 인증 검사가 path 무관하게 작동. callback 페이지의 `useEffect`가 fragment 처리 전에 AuthGuard render가 먼저
- 해결:
  1. AuthGuard에 `pathname.startsWith("/auth/works/callback")` 분기 — children passthrough (인증 검사 우회)
  2. callback 페이지에서 `router.replace("/")`(SPA navigation) 대신 `window.location.replace("/")`(hard reload) 사용 → AuthGuard 새로 mount 보장
- 재발 방지: 인증 wrapper에는 항상 OAuth callback path whitelist. SPA router는 wrapper 재mount 안 시키므로 인증 phase 전환에는 hard reload 필요

### 2026-04-29 — NAVER WORKS Console redirect URI 슬롯 제한 → SSO callback 1개로 흐름 통합
- 컨텍스트: SSO callback과 Drive callback을 별도 path로 두려 했으나 Console에 redirect URI 슬롯이 production+staging 정도로 빠듯
- 해결 패턴: signed state에 mode flag(`d=1`)를 인코딩. login URL `?drive=1`이면 scope에 `file` 추가 + state에 d=1. callback이 state.d를 보고 분기 — 일반 SSO인지 Drive 위임인지
  ```python
  state, _ = sso_works.issue_state(secret, next_path, drive=True)
  scope = "user.read file" if drive else "user.read"
  ```
- 재발 방지: 다중 OAuth 흐름이 필요하면 redirect URI 추가 등록 대신 state 안에 mode flag로 분기. 한 callback이 모든 흐름 처리. CSRF 방어는 그대로 (signed state)

### 2026-04-28 — Codex MCP가 본문 무시하고 일반 응답만 반환
- 컨텍스트: NAVER WORKS 전환 계획 검토를 Codex MCP(`mcp__codex-cli__codex`, gpt-5.3-codex)에 의뢰
- 증상: 4000자 분량의 구조화된 계획·질문을 prompt에 담았지만, Codex가 본문을 인식하지 못한 듯 "초안을 붙여달라" 같은 일반 안내만 반복 반환. 두 번 시도, `resetSession=true`도 무효
- 원인(추정): Codex MCP 세션의 길이 제한 또는 prompt parsing 이슈로 본문이 누락되어 전달되는 것으로 보임
- 해결: 본 건은 Codex 검토 없이 진행. 사용자에게 상황을 알리고 자체 계획 초안을 먼저 제시한 뒤, 다음 단계에서 재시도 또는 사용자가 외부 GPT에 직접 검토 의뢰하는 방식으로 우회
- 재발 방지: Codex MCP에 4000자 이상의 prompt를 한 번에 보내지 말 것. 핵심 질문 1~2개로 분할하거나 mcp__codex-cli__review 별도 도구 사용을 우선 검토. Codex가 빈 응답·맥락 무시 응답을 줄 때는 두 번 이상 재시도하지 말고 즉시 차선책으로 전환

### 2026-04-30 — NAVER WORKS Drive `share/root-folder` URL이 sharedrive root로 redirect (resourceKey 무시)
- 컨텍스트: 프로젝트 폴더 자동 생성 후 노션에 share URL 저장. 사용자가 "WORKS Drive" 버튼 클릭 → 그 프로젝트 폴더가 아닌 [업무관리] 루트 폴더로 이동
- 증상: URL은 `https://drive.worksmobile.com/drive/web/share/root-folder?resourceKey=...&resourceLocation=24101` 인데 NAVER가 resourceKey 무시하고 sharedrive 자체 root만 보여줌
- 원인: `share/root-folder` path는 sharedrive 자체의 root를 의미하는 endpoint. 하위 폴더의 web URL은 `share/folder`를 사용해야 resourceKey가 적용됨. 우리 `_extract_url`/`build_file_web_url`이 둘 다 `root-folder`로 만들고 있었음
- 해결:
  1) `sso_drive._extract_url` / `build_file_web_url` 모두 `share/folder`로 변경 (새로 만들 폴더는 정상)
  2) `Project.from_notion_page`의 `drive_url` 추출 시 `/share/root-folder?` → `/share/folder?` 자동 정규화 — 노션에 이미 저장된 잘못된 URL도 응답 시점에 회복 (마이그레이션 스크립트 불필요)
- 재발 방지: NAVER WORKS Drive web URL 패턴 — `share/folder`는 폴더, `share/root-folder`는 sharedrive 루트. 응답에 webUrl 키 없을 때 직접 조립할 때는 항상 folder. PoC로 실제 폴더 URL 1개 확인하면 5초

### 2026-04-30 — sync 구조 후속 보강 (외부 리뷰 권장사항)
- 컨텍스트: web worker 격리 + cron 분리 1차 적용 후 외부 코드 리뷰에서 6개 잔존 문제 지적
- 문제·해결 묶음:
  1) **render.yaml SYNC_ENABLED `value: "true"` 박혀있어 dashboard toggle 무력화** — `value: "false"`로 변경. 이전 error.md(2026-04-29 Render value vs sync: false) 패턴의 반대 적용 — 운영자 토글 불필요한 변수는 value로 박는 게 맞음
  2) **full reconcile cron 누락** — incremental cron만으론 archive(`_mark_missing_archived`) 정리 안 됨. 새 cron `dy-task-sync-full` (KST 03:00) 추가
  3) **sync_once.py env 사일런트 실패** — sync_kind는 db_id 없으면 0건 성공 처리. `assert_required_env(kind)` 추가해 cron exit 1 + 명확 메시지
  4) **JWT_SECRET 기본값** — `change-me-in-production`이 운영 누락 시 사용. `validate_runtime_settings()` 추가, lifespan에서 즉시 RuntimeError
  5) **lifespan init_db 무조건** — 운영은 alembic 처리. `auto_create_tables: bool = False` 추가, 운영에선 호출 skip
  6) **query_all 전체 누적** — 큰 DB(1000+ 페이지) 시 메모리 + 첫 반영 시간 길음. `iter_query_pages` async generator 추가, sync_kind를 batch streaming(100개씩 받자마자 thread pool upsert)으로 리팩터
- 재발 방지:
  - render.yaml의 운영자 토글 안 하는 env는 항상 `value:`로 명시 (dashboard 덮어쓰기 회피)
  - full reconcile은 incremental과 별개 cron으로 운영 (single point of truth 원칙)
  - cron entrypoint(`sync_once.py`)에 필수 env 검증 — 사일런트 실패가 운영 침묵 사고로 이어짐
  - 모든 secret default는 위험 값(`change-me-in-production` 등)으로 두고 startup 시 차단 — 운영 환경변수 누락 즉시 fail
  - `init_db()`/Base.metadata.create_all 같은 자동 schema 생성은 dev/test 전용 토글 뒤로
  - 대용량 외부 API → DB sync는 streaming(generator) 패턴 — 메모리 누적 + 첫 반영 시간 동시 개선

### 2026-04-30 — sync가 web worker 안에서 돌아 사용자 API가 5~22초 지연
- 컨텍스트: 외부 cron이 `/api/cron/sync` 호출 → fire-and-forget 202 즉시 응답 + DB upsert는 thread pool 분리. 이 상태에서도 `/api/auth/status`(5초+), `/api/projects?assignee=...`(15~88초) 같은 단순 요청이 timeout/502
- 증상: cron 5분 사이클마다 task.dyce.kr 화면이 잠깐 죽고 SWR retry 폭주
- 원인: DB upsert를 thread로 분리했지만 노션 API 호출(0.4초 rate limit, 6 DB × 100 페이지+) 자체는 web worker의 event loop이 점유. HTTP connection pool, CPU도 같은 process가 공유. 또한 sync_all이 6개 DB를 한 번에 처리해 부하 집중
- 해결:
  1) **sync를 web worker 밖으로 — 별도 cron container에서 `python -m app.scripts.sync_once`** 직접 실행. web service는 사용자 API만 처리
  2) kind별 빈도 차등 — projects/tasks 5분, master/clients/cashflow/expense 30분, 시간 엇갈리게(`*/5`, `2-59/5`, `*/30`, `15,45`)
  3) web service의 `SYNC_ENABLED=false`로 내부 APScheduler 비활성 — 외부 cron이 유일한 트리거
  4) `/api/cron/sync?full=true`는 KST 7~22시 차단 (안전망)
- 재발 방지: 무거운 백그라운드 작업은 web worker와 분리된 container/worker에서. fire-and-forget도 결국 같은 process라 자원 공유 — 진짜 격리는 별도 container. backend/app/scripts/* 패턴 사용해 module로 호출(`python -m app.scripts.X`). render cron의 envVars는 web service와 동일하게 share

### 2026-04-30 — `asyncio.create_task` 결과를 참조 안 잡으면 mid-execution에서 GC됨
- 컨텍스트: cron 엔드포인트를 fire-and-forget으로 분리하면서 `asyncio.create_task(_run_sync_in_bg(...))` 사용. 반환값 무시
- 증상: 첫 호출 `{"status":"started"}` 정상 응답인데 Render Logs에 `manual cron ... done: N` 메시지가 영영 안 나옴. 두 번째 호출 시 `already_running` 아닌 또 `started` 응답 (즉 `_running_sync` set이 비어있음). 실제 mirror upsert는 안 됨
- 원인: Python asyncio docs 공식 경고 — "The event loop only keeps weak references to tasks. A task that isn't referenced elsewhere may be garbage collected at any time, even before it's done." 우리 코드가 task 객체를 어디에도 보관 안 함 → mid-await GC. coroutine.close() → GeneratorExit가 finally는 돌리지만(그래서 `_running_sync`는 정리됨) 실제 sync 작업은 끊김
- 해결:
  ```python
  _bg_tasks: set[asyncio.Task] = set()

  def _spawn_bg_sync(*, kind, full):
      task = asyncio.create_task(_run_sync_in_bg(kind=kind, full=full))
      _bg_tasks.add(task)
      task.add_done_callback(_bg_tasks.discard)
  ```
  완료 시 콜백으로 자동 제거되어 메모리 누수도 없음
- 재발 방지: `asyncio.create_task(...)` 결과는 항상 어딘가에 보관. fire-and-forget 패턴은 `set + add_done_callback(set.discard)` 표준 idiom 사용. lint rule(`RUF006`)이 ruff에 있어 활성화 권장: `asyncio-dangling-task`

### 2026-04-30 — `/api/cron/sync` 동기 응답이 worker를 1~3분 막아 다른 요청이 502
- 컨텍스트: Render starter (512MB/0.5 CPU, 단일 worker process)에서 `?full=true` 호출 시 노션 6개 DB reconcile이 1~3분 걸림. 그 동안 frontend의 SWR polling(`/api/seal-requests/pending-count` 등)이 모두 `502 Bad Gateway` + 표면상 CORS 에러
- 증상: `Access to fetch at ... blocked by CORS policy: No 'Access-Control-Allow-Origin' header` + 502. CORS 자체는 정상이지만 502 응답에 헤더가 안 붙어서 브라우저가 CORS 에러로 표시
- 원인: cron 엔드포인트가 `await sync.sync_all(...)`를 동기 await 해 worker가 sync 종료까지 점유. uvicorn 단일 worker라 같은 process에서 다른 요청이 줄 서다 timeout
- 해결:
  1) cron 엔드포인트를 fire-and-forget으로 — `asyncio.create_task(_run_sync_in_bg(...))` + 즉시 `202 {"status":"started"}` 반환. sync는 background 코루틴으로 진행
  2) `NotionSyncService`에 per-kind `asyncio.Lock` — 5분 scheduler와 수동 cron이 같은 kind를 동시에 돌려 cursor 충돌하는 문제 차단
  3) main.py에 `_running_sync: set[str]` — 사용자가 응답 빠르다고 여러 번 호출해도 중복 background task spawn 금지. `_all` 또는 kind별 키. 이미 실행 중이면 `{"status":"already_running"}` 반환
  4) 결과는 동기 응답에서 빠지므로 Render Logs(`logger=dy.cron`)에서 `manual cron ... done: N` 메시지로 확인
- 재발 방지: I/O bound라도 1분+ 동기 await가 있는 endpoint는 단일-worker 환경에서 항상 background task로 분리. 또한 멱등하지 않은 트리거는 dedupe set/lock으로 중복 spawn 방어. asyncio.Lock 인스턴스 변수는 `__new__`로 만든 테스트 인스턴스에서도 동작하도록 lazy init (`getattr(self, "_kind_locks", None)` 패턴)

### 2026-04-30 — incremental sync since 갱신 race로 노션 신규 페이지가 mirror에 영구 누락
- 컨텍스트: 노션 마스터 DB에 새 마스터 추가했는데 5분 incremental sync가 여러 번 돌아도 mirror_master_projects에 안 들어옴. 다른 마스터들은 정상
- 증상: 프로젝트 상세 ProjectHeader의 ▣ 마스터 라벨 비표시. `master_project_name`이 빈 값 (project mirror에는 master_project_id 정상). 이전에 만들어진 마스터들은 모두 정상 표시
- 원인: `_record_success`가 since(`last_incremental_synced_at`)를 sync **종료** 시각(`_utcnow()`)으로 박음 + 노션 query는 strict `>` filter (`last_edited_time after since`). sync가 T_start ~ T_end 동안 실행되는 사이 노션에서 페이지가 추가되면 last_edited_time이 T_end보다 작을 수 있음 → 다음 incremental의 `> T_end` filter에서 누락. 이후 그 페이지가 수정되지 않으면 영구 누락
- 해결:
  1) `sync_kind` 시작에 `start_time = _utcnow()` capture
  2) `_record_success`에 `next_since` 매개변수 추가, since 갱신을 시작 시각으로 (종료 시각 아님)
  3) query filter에 60초 lookback overlap (`since - 60s`) 적용. upsert idempotent라 중복 안전. 노션 인덱싱 지연·clock skew도 함께 방어
  4) 즉시 복구는 단건 GET API (`/api/master-projects/{id}` 등 mirror miss시 노션 fallback + upsert) 또는 `POST /api/cron/sync/{kind}?full=true`
- 재발 방지: incremental 동기화 패턴에서 cursor는 항상 sync **시작** 시각 (또는 max(seen.last_edited_time))으로 갱신. 종료 시각 사용 금지. boundary 페이지를 위한 lookback overlap window는 표준 방어책. 외부 source에 strict timestamp filter가 있으면 더더욱 필요

### 2026-04-26 — Packaged 환경에서 노션 토큰 배포 방식
- 컨텍스트: 사용자 PC마다 .env 직접 두기 불편. NOTION_API_KEY 등 어떻게 배포?
- 결정: 옵션 A — `backend/.env.production` 파일을 PyInstaller datas에 번들 (사내 도구라 보안 trade-off 수용)
- 우선순위: `BACKEND_DATA_DIR/.env` (사용자 override) > `exe_dir/.env` > 번들 `.env.production` (기본값)
- JWT_SECRET은 첫 실행 시 user_dir에 자동 생성/저장 (`secrets.token_urlsafe(64)`)
- 재발 방지: `.env.production`은 .gitignore 처리, 빌드자만 보유. 토큰 유출 시 노션 통합 토큰 재발급으로 대응 가능

### 2026-05-01 — 날인요청 시나리오 정착 (검토구분 6종 + Works Drive + Bot 알림)
- 컨텍스트: docs/request.md 명세를 코드에 반영. 기존 4종(구조계산서/도면/검토서/기타) → 6종(구조계산서/구조안전확인서/구조검토서/구조도면/보고서/기타). 상태값 doc 명세(1차검토 중/2차검토 중/승인/반려)로 통일. S3 → NAVER WORKS Drive (`0. 검토자료/YYYYMMDD/`). 단계별 Bot 알림. 자동 TASK row 연동
- 패턴: 노션 select 옵션은 schema에서 자동 제거 불가 → 신 옵션을 schema에 추가 + read 시점에 `seal_logic.normalize_status`/`normalize_type`로 옛 옵션을 신 옵션으로 양방향 매핑. 마이그레이션 없이 호환
- 패턴: `python-jose[cryptography]`로 RS256 JWT 서명 (PyJWT 추가 설치 불필요). `from jose import jwt as jose_jwt; jose_jwt.encode(claim, pem_private_key, algorithm="RS256")`. PEM 환경변수에 single-line `\n` 이스케이프가 들어와도 동작하도록 `key.replace("\n","\n")` 호환 처리
- 패턴: 외부 서비스 호출(Bot send_text, 자동 task 생성, task 동기화)은 fire-and-forget — 호출자 트랜잭션을 절대 막지 않음. `asyncio.create_task` + `_bg_tasks: set` 강 참조 + `add_done_callback(_bg_tasks.discard)` 으로 GC 누수 방지
- 패턴: 구조검토서 문서번호 발급(`{YY}-의견-{NNN}`)은 노션 default `archived=False` filter가 자동 적용 → 마지막 번호 archive 시 다음 발급에서 재사용 (별도 회수 로직 불필요). 중간 번호 취소는 archive하지 않고 `[날인취소]` prefix + 첨부 비움으로 흔적 남김 (sequence 깨짐 방지)
- 재발 방지: 노션 select enum 변경 시 schema 자동 추가 + read 정규화 함수 쌍을 항상 같이 도입. 외부 알림은 어떤 경우에도 사용자 트랜잭션 차단 금지. JWT 서명 라이브러리는 이미 있는 것을 우선 활용 (python-jose / PyJWT 중복 의존 회피)

### 2026-04-30 — Render env에 PEM 붙여넣으면 줄바꿈이 공백으로 평탄화 (MalformedFraming)
- 컨텍스트: NAVER WORKS Bot Service Account JWT(RS256) 서명을 위해 WORKS_BOT_PRIVATE_KEY를 Render Environment에 붙여넣은 후 첫 호출
- 증상: backend Logs `Bot 토큰 발급 실패: Bot JWT 서명 실패 — Private Key 형식 확인 필요: Unable to load PEM file. ... MalformedFraming`. test endpoint는 `ok=false, error="send_text False"`만 응답
- 원인: Render env 입력 UI가 multi-line 지원하긴 하지만, paste 과정에서 PEM의 줄바꿈이 공백/탭으로 squash되는 케이스 발생. cryptography는 base64 본문 사이의 공백을 줄바꿈으로 인식 못 해 framing 에러
- 해결: `sso_works_bot._normalize_private_key`를 강화 — (1) 정상 multi-line / (2) `\n` 이스케이프 single-line / (3) 공백 평탄화 single-line 3종 모두 정규화. BEGIN/END 마커를 regex로 잡고 본문의 모든 공백을 제거 후 64자 단위 wrap으로 표준 PEM 재구성. 테스트 6종 추가
- 재발 방지: secret 환경변수에 multi-line 값이 들어가야 하는 모든 곳(JWT private key, certificate, multi-line config)은 입력 형태에 무관한 정규화 함수 + 명시적 unit test 동반. paste 사고를 코드 레이어에서 흡수하면 운영자 트러블슈팅 시간이 절약됨

### 2026-04-30 — Render env에 PEM의 BEGIN/END 마커 라인이 누락됨
- 컨텍스트: 위 PEM 줄바꿈 평탄화 fix(`fcc3d41`) 후에도 `MalformedFraming` 지속. test endpoint에 PEM 진단 metadata 추가(`77f08bf`)해 확인
- 증상: 진단 응답에 `has_begin_marker:false, has_end_marker:false`. raw가 `MIIEvgIBADAN...`(=base64 본문 첫 글자)로 시작 → BEGIN/END 마커 라인 자체가 입력에 없음
- 원인: 운영자가 `.key` 파일을 열어 본문만 복사했거나, Render env 입력 시 마커 라인이 잘림. base64만으로는 cryptography가 PEM으로 인식 못 함
- 해결: `_normalize_private_key`에 case (4) 추가 — 마커가 없고 본문이 base64 alphabet만으로 구성되어 있으면 PKCS#8 `PRIVATE KEY`로 가정하고 헤더/푸터 자동 wrap. NAVER WORKS Service Account 키는 PKCS#8 표준이라 안전한 가정
- 재발 방지: secret 입력 robustness는 짐작 가능한 모든 paste 패턴(이스케이프/공백 평탄화/마커 누락/본문만)을 흡수하는 정규화 + 단위 테스트로 잠금. 또한 진단 응답(secret 본문 노출 X, 구조 metadata만)을 admin endpoint에 두어 다음 사고도 즉시 진단 가능

### 2026-04-30 — 노션 select 옵션 누락 자동 보강 미동작 (NOTION_API_ERROR 502)
- 컨텍스트: 날인요청 schema에 신 옵션(`1차검토 중`/`2차검토 중`/`승인`/`취소`)을 추가했는데 운영에서 backend가 그 옵션으로 query/write 시도 → 노션 "select option not found" → NotionApiError → frontend 502
- 증상: Render Logs에 `NOTION_API_ERROR on GET /api/seal-requests/pending-count — select option "2차검토 중" not found for property "상태". Available options: "요청", "팀장승인", "관리자승인", "완료", "반려"`
- 원인: `notion_schema._ensure_db`가 **컬럼 자체 누락 시에만** 추가. 기존 select 컬럼의 누락 옵션은 비교/patch 안 함. 노션은 select option `update_data_source_schema`에서 부분 patch가 아닌 전체 list 교체 방식이라 기존 옵션 보존이 까다로움
- 해결: `_missing_select_options` 헬퍼 추가. 기존 옵션(id 포함) + 누락 옵션을 union해 전체 list로 patch. `_ensure_db`가 컬럼 추가 + 옵션 보강 둘 다 처리. logger도 `노션 schema 옵션 보강 [...]` / `노션 schema 컬럼 추가 [...]`로 분리해 운영 가시성 향상
- 응급 처치: 사용자가 노션 DB에서 누락 옵션을 수동 추가 (5분). 코드 fix는 다음 backend 재배포 시 동일 사고 자동 방어
- 재발 방지: select enum 추가 시 schema 보강 함수가 옵션 union까지 처리하는지 항상 확인. `_ensure_db` 처럼 schema 자동 적용 코드는 단위 테스트로 (a) 컬럼 누락 (b) 옵션 누락 (c) 옵션 일부 동일 (d) 변경 없음 4가지 경로 cover
