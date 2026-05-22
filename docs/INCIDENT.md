# 운영 사고 기록 (Incident Log)

본 문서는 production 사고의 원인/조치/교훈을 시간 순으로 기록.
다음 사고 발생 시 빠른 진단 및 대응을 위한 매뉴얼.

---

## 2026-05-12 — SQLAlchemy connection leak → Supavisor pool 고갈 → 전사 접속 불가

### 증상

- frontend(task.dyce.kr)에서 backend API 호출 모두 500 + CORS 차단
  ```
  Access to fetch at 'https://dy-task-backend.onrender.com/api/auth/status' from
  origin 'https://task.dyce.kr' has been blocked by CORS policy:
  No 'Access-Control-Allow-Origin' header is present
  ```
- backend `/health`는 200 (DB 안 거쳐서) → Render는 healthy로 인식, 자동 restart 안 함

### 진행 단계 (각 단계 별 backend 로그 신호)

| 단계 | 신호 | 원인 |
|---|---|---|
| **1차** | `QueuePool limit of size 10 overflow 20 reached, connection timed out, timeout 20.00` | SQLAlchemy 자체 풀(워커당 30) 고갈 |
| **2차** | `FATAL: (EMAXCONNSESSION) max clients reached in session mode - max clients are limited to pool_size: 50` | Supavisor Session pool(50) 도달. backend workers의 누적 leak이 SQLAlchemy 풀을 넘어 Supavisor 단까지 채움 |
| **3차** | `connection to server at "2406:da12:..." port 6543 failed: Network is unreachable` | Transaction mode(6543) 시도 시 IPv6 endpoint만 반환되어 Render(IPv4-only) 차단 |

### 원인

1. **SQLAlchemy connection leak** — get_db() Depends 외 경로의 `SessionLocal()` 또는 background task에서 `session.close()` 누락. 시간 누적으로 풀 고갈.
2. **`/health` 라우트가 DB 안 거침** — Render auto-restart trigger 못 됨.
3. **Transaction mode pooler는 IPv6 endpoint만 노출** — Render의 IPv4-only outbound와 비호환.

### 조치

**즉시 복구 (운영 정상화):**
1. Render → Manual Restart (워커 fresh 시작)
2. Supabase SQL Editor에서 활성 supavisor session 강제 종료:
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE application_name LIKE 'Supavisor%';
   ```
3. `DATABASE_URL`은 Session mode(5432) + Shared pooler(`aws-0-...`) 유지.

**임시 보강 (commit `c4de851`):**
- `backend/app/db.py`
  - `pool_size`: 10 → **5**
  - `max_overflow`: 20 → **10**
  - `pool_recycle`: 300s → **120s**
- 효과: 워커당 최대 15 connection. Supavisor 50까지 여유 35.
  - idle leak도 2분 주기로 강제 reset → 누적 속도 감소.
  - 근본 leak 해결은 아님 (시간 늦춤만).

### 교훈

1. **`/health`는 DB 거쳐야** — 별도 cycle에서 `/api/health/db` 추가 + Render health check path 교체.
2. **connection leak source audit 필요** — backend 전체 `SessionLocal()` 호출 위치 점검.
3. **Transaction mode는 Render에서 불가** — Supabase IPv4 add-on 또는 Render Pro plan 필요. 현재는 Session mode 유지.
4. **사고 대응 SQL은 본 문서에 보관** — Supabase Dashboard 접근 권한자가 즉시 실행 가능.

### 추적 항목 (별도 cycle 진행)

- [x] **weekly_report `_report_cache`가 ORM 객체 보유 여부 검토** — PR-DX audit (2026-05-16). `_report_cache`는 Pydantic `WeeklyReport` DTO만 보관 (BaseModel, ORM 객체 X). cache TTL 5분 후 자동 invalidate. 안전.
- [x] **background sync (5분 incremental) session close 보장** — PR-DX audit. `sync.py NotionSyncService`는 `with self.session_factory() as db:` 패턴 일관 사용 (180~755 11 callsites 모두). `weekly_snapshot.py` / `task_auto_progress.py` / `project_stage_sync.py`는 `with SessionLocal() as db:` 자동 close. `sso_drive.py` 3 callsites / `task_calendar_sync.py` 2 callsites는 `try: ... finally: db.close()` 패턴 — 모두 보장.
- [x] **PDF route (`build_weekly_report_pdf` 등)의 db 의존성 정리** — PR-DX audit. `weekly_report_pdf.py` / `quote_pdf.py`는 pure DTO → bytes 변환 (Session 의존 0건). 라우터(`routers/weekly_report.py`, `sales/pdf.py`)는 FastAPI `Depends(get_db)`로 자동 close.
- [x] **silent except path에서 db.close() 누락 점검** — PR-DX audit + PR-BV/BW silent except 분류 결과 cross-check. `except` 블록 내부에서 `SessionLocal()` 호출 케이스 0건 — silent except의 db.close 누락 위험 없음.

근본 연결 누수 위험은 PR-AQ(get_db rollback + reset_on_return + /api/health/db) + PR-DA(idle_in_transaction_session_timeout 300s) 2중 안전망으로 cover.
- [x] **`/api/health/db` 라우트 + Render health check path 교체** — PR-DB(/api/health/db endpoint, idle_in_transaction_session_timeout SHOW 함께 노출) + PR-DY(render.yaml healthCheckPath `/health` → `/api/health/db`). DB 끊김 시 503 반환 → Render auto-restart trigger. INCIDENT #1 교훈 #1 충족.

---

## 2026-05-11 — Supabase compute 등급업 (pool_size 15 → 50)

### 증상

- backend 시작 직후 `EMAXCONNSESSION pool_size: 15` 에러
- 사용자 요청 폭주 시 즉시 풀 고갈

### 원인

Supabase free/micro tier의 Supavisor Session pool은 **15** 한도. SQLAlchemy 풀(pool_size=10 + max_overflow=20 = 30)이 한 워커당 최대 30 요청 시도 → Supavisor 15에서 막힘.

### 조치

Supabase Dashboard → Compute and Disk → **Small 등급 이상**으로 업그레이드 (pool_size 25+). 본 프로젝트는 Small(pool 50) 사용 중.

| Compute | Session pool | Transaction pool |
|---|---|---|
| Nano (Free) / Micro | 15 | 200 |
| Small | 25 (또는 50) | 400 |
| Medium | 50 | 800 |
| Large | 100 | 1600 |

---

## 2026-05-11 — Dedicated pooler(IPv6-only) 사용 시 startup 무한 restart

### 증상

backend startup 시 즉시:
```
(EDBHANDLEREXITED) connection to database closed
```
Render instance restart 무한 루프.

### 원인

`DATABASE_URL`이 dedicated pooler(`aws-1-ap-northeast-2.pooler.supabase.com`) 사용. 해당 host는 **IPv6 endpoint만** 노출. Render outbound는 IPv4-only이므로 connect 자체 실패.

### 조치

Supabase Dashboard → Database → Connection Pooler → **Shared 탭**(`aws-0-ap-northeast-2.pooler.supabase.com`)의 connection string으로 교체.

자세한 매뉴얼은 [STATUS.md - 환경/배포 노트](STATUS.md#환경--배포-노트) 참조.

---

## 사고 대응 체크리스트 (재발 시)

### 1. 진단 (1분 내)

```bash
# backend health
curl -s -o /dev/null -w "HTTP %{http_code}  time=%{time_total}s\n" -m 15 \
  https://dy-task-backend.onrender.com/api/auth/status

# Render Logs 확인 — Dashboard → 해당 서비스 → Logs
```

### 2. 로그 패턴 매칭

| 에러 메시지 | 원인 | 1차 조치 |
|---|---|---|
| `QueuePool limit ... timed out` | SQLAlchemy 풀 고갈 | Render Restart |
| `(EMAXCONNSESSION) ... pool_size: NN` | Supavisor pool 고갈 | Supabase SQL Editor에서 `pg_terminate_backend` |
| `Network is unreachable` (`2406:...`) | IPv6 endpoint 시도, Render 차단 | `DATABASE_URL`을 Shared pooler(`aws-0-...`)로 |
| `EDBHANDLEREXITED` startup loop | Dedicated pooler 사용 중 | Shared pooler로 교체 |
| `WORKS_BOT_ENABLED=true ... 누락` | 환경변수 누락 | Render env vars 확인 |

### 3. 운영 정상화 SQL (Supabase SQL Editor)

```sql
-- 활성 connection 확인
SELECT pid, application_name, usename, state, query_start, state_change
FROM pg_stat_activity
WHERE datname IS NOT NULL
ORDER BY state_change DESC;

-- Supavisor session 강제 종료
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE application_name LIKE 'Supavisor%';
```

### 4. 정상화 확인

```bash
curl -s https://dy-task-backend.onrender.com/api/auth/status | head -3
# {"initialized":true,"user_count":NN,"works_enabled":true,...} 출력 확인
```

### 5. 사고 기록

본 문서에 신규 사고 entry 추가 (날짜 / 증상 / 원인 / 조치 / 교훈 / 추적 항목).

---

## 2026-05-13 — PR-BI 인증 채널 폐기 시도 후 일부 사용자 로그인 loop

### 증상

- 운영 사용자 `eul22` 브라우저에서 강제 새로고침 후 로그인 화면이 계속 반복.
- DevTools Application → Cookies에 `dy_jwt`가 저장됐다가 곧 사라지거나, 페이지가 `/login` 으로 끊임없이 redirect되는 경우 발생.
- 같은 시점에 다른 사용자(eul22 외)는 정상.

### 원인 (가설)

PR-BI(2단계 cookie 단독 인증)에서 `authFetch`의 Authorization header 첨부 + `localStorage` token 저장을 모두 제거. 인증을 cookie에만 의존하게 됐는데, 다음 흐름 중 하나에서 cookie가 의도대로 발급/저장되지 않은 것으로 추정:

1. **silent SSO iframe context** — `trySilentSSO`가 iframe으로 NAVER WORKS authorize 호출 → backend callback redirect에 `Set-Cookie`가 포함되지만, 일부 브라우저(Chrome 3rd-party cookie 차단 강화)에서 iframe 안 응답의 cookie 저장이 차단되거나 partition됨.
2. **saveAuth signature 변경 (`(token, user) → (user)`)이 캐시된 옛 build chunk와 어긋남** — Vercel deploy 직후 사용자 브라우저가 옛 callback chunk + 새 lib/auth.ts chunk를 동시에 load하면 token 위치에 user JSON이 저장되어 `getUser()=null` → `isLoggedIn=false` → /login redirect 반복.
3. **AuthGuard fetch 401 자동 redirect** — silent SSO 후 첫 fetch가 401이면 즉시 `clearAuth + /login` → 사용자가 다시 로그인 → 다시 401 → loop.

1단계(PR-BH)는 token도 살아있어 cookie 발급 실패해도 header로 우회됐지만, 2단계는 fallback이 없어 즉시 loop으로 발현.

### 조치

1. **즉시 revert** — `git revert` PR-BI 두 commit (47e6d06 + 0badaa6) → 1단계(`db75dcf`) 상태로 복구. push 후 5-8분 deploy → eul22 정상 진입 확인.
2. INCIDENT 기록 (본 entry).
3. 다음 시도 전 설계 보강 (재발 방지) — 아래 "다음 시도 전 체크리스트".

### 교훈

- **운영에서 cookie 단독 인증 전환은 silent SSO + cookie partition 동작 검증 후에만 안전하다.** Chrome의 third-party cookie 정책 변화로 iframe 안 응답의 Set-Cookie가 차단되거나 partition될 수 있다.
- **saveAuth 같은 핵심 helper signature 변경은 backward-compatible 한동안 유지.** Vercel chunk 부분 stale로 인한 mismatch 회피.
- **fetch 401 → 즉시 redirect /login** 정책은 cookie 채널이 살아있을 때 OK이지만, cookie 문제가 있으면 즉시 loop. 401 한 번에는 silent SSO 한 번 재시도 후 redirect로 보강 필요.
- **dual-run 검증 부재.** 2단계 deploy 직전 staging에서 4 role 시나리오 + cookie 발급 흐름 verify 안 함 → 운영 즉시 회귀.

### 다음 시도 (PR-BI 재시도) 전 체크리스트

1. **silent SSO cookie 검증** — 운영 로그인된 상태에서 incognito 모드로 silent SSO 흐름 trace, callback 응답 Set-Cookie + Cookies storage에 저장 여부 확인.
2. **saveAuth backward-compat** — `function saveAuth(arg1: string | UserInfo, user?: UserInfo)` 형태로 옛 호출 (token, user) + 새 호출 (user) 둘 다 처리. 옛 chunk가 깨지지 않도록.
3. **401 자동 silent SSO 재시도** — `authFetch` 첫 401에 silent SSO 한 번 시도 후 재시도, 그래도 401이면 `clearAuth + /login`.
4. **/api/auth/me 호출 hydration** — fragment user_b64 직접 신뢰 대신 cookie 기반 `/me` fetch 결과로 user 저장 (signature 안전성 + cookie validity 동시 검증).
5. **CI playwright e2e에 4 role 인증 흐름 추가** (PR-BL-5) — backend mock 또는 staging 환경에서 `silent SSO 실패 → /login → 정상 SSO → cookie 발급 → 대시보드 진입` 시나리오 자동 검증.
6. **운영 telemetry** — 1단계 PR-BI에서 추가한 `auth_via_header` log를 PR-BI 재시도 후 0으로 수렴하는지 확인 (이미 보유한 인프라).

### 추적

- PR-BI revert: 0a427b0 / e340068
- 상태 → 1단계(PR-BH 5db883a / 6b929a7 / db75dcf) 안정 운영 중
- 재시도 일정: 위 체크리스트 모두 충족 후 별도 cycle

---

## 2026-05-13 — PR-BP/BQ 재시도 시 callback page hydration 무한 재귀

### 증상

- PR-BP(`/me hydration`) + PR-BQ(`Authorization header 제거`) 운영 deploy 후 사용자 SSO callback page에서 "로그인 처리 중..." 화면이 계속 반복.
- 페이지가 멈춰있는 게 아니라 callback URL을 계속 재방문하는 패턴.

### 원인

PR-BP에서 `hydrateUserFromMe()`가 `authFetch("/api/auth/me")`를 사용. SSO callback page useEffect에서 redirect 직전 호출했는데:

1. callback page mount → `hydrateUserFromMe()` → `authFetch("/api/auth/me")`
2. cookie가 callback redirect에서 set은 됐지만 첫 fetch에 적용 타이밍 이슈 → 401
3. PR-BO `authFetch` 401 자동 처리: silent SSO 1회 시도
4. **silent SSO는 iframe으로 callback page를 다시 load** (NAVER WORKS authorize → backend callback → frontend callback)
5. iframe 안 callback page → `hydrateUserFromMe()` 호출 안 함(silentMessage 분기) — 이건 OK
6. 하지만 main page의 `hydrateUserFromMe`가 여전히 await 중. silent SSO postMessage로 부모에 결과 전달 → trySilentSSO resolve → authFetch 재시도 → 또 401 → silent skipped → clearAuth + `/login` redirect
7. 동시에 callback page의 `.finally`가 redirect target으로 navigate 시도 → **navigation 충돌**

또 PR-BO + PR-BQ 조합 효과로 callback 외 페이지에서도 401 → silent SSO trigger 가능. silent SSO 자체가 callback page를 사용하므로 callback page의 hydration 호출이 silent SSO 결과 받기 흐름과 결합되어 "callback URL이 계속 트리거되는" 현상.

### 조치

1. `git revert` PR-BQ(8a7f45f) + PR-BP(bd86c9f) — 5ae788e + b51fd72 push.
2. 안정 상태(PR-BO 시점) 복귀. PR-BN(saveAuth backward-compat) + PR-BO(401 silent retry) + PR-BL-5(e2e) 인프라는 그대로 유지.

### 교훈

- **인증 hydration helper(`hydrateUserFromMe` 등)는 raw `fetch`를 사용해야 한다.** `authFetch`는 401 자동 처리(silent SSO)를 포함하므로, hydration이 401을 받으면 silent SSO로 발산 → callback 재방문 → 무한 재귀.
- **callback page에서 추가 인증 요청을 trigger하면 안 된다.** callback은 silent SSO의 receiver 역할만. `hydrateUserFromMe` 같은 검증은 callback 후 다른 페이지(AuthGuard ready phase 진입 시)에서 호출.
- **PR-BO 401 silent retry는 강력하지만 부작용 영역이 넓다.** 인증 endpoint(`/me`, `/auth/status`)에는 silent retry를 적용하면 안 됨 — 인증 검증 자체가 401 받으면 silent로 풀리는 게 아니라 정상 redirect 흐름.

### 다음 PR-BP 재설계 시 체크리스트

1. **`hydrateUserFromMe`는 raw `fetch` 사용** ✅ — PR-CY `verifyAndHydrateFromMe` (line 243 frontend/lib/auth.ts): raw `fetch` + `credentials: "include"` + 401/network graceful fallback. silent SSO trigger 안 함.
2. **callback page에서 호출 X** ⚠️ — 현재 callback page(`frontend/app/auth/works/callback/page.tsx:105`)에서 호출 중이지만, PR-CY 설계가 raw fetch + 401 graceful fallback이라 INCIDENT #5 무한 재귀는 회피됨(silent SSO trigger 없음). 체크리스트 의도와 다르지만 결과적 안전.
3. **PR-BO `authFetch` silent retry에 제외 list 추가** ✅ — PR-DV: `_authFetchInternal`에 `isAuthVerifyEndpoint` 분기 추가, `/api/auth/me` / `/api/auth/status` 시작 path는 silent SSO 시도 안 함. vitest 2 시나리오로 회귀 방지.
4. **PR-BQ 재시도 전 PR-BP 재설계 완료** ✅ — PR-CY 완료(2026-05-14 commit a1e8d08) + PR-DT vitest 회귀 보강(3119ba9) + PR-DV silent retry 제외(2026-05-16).
5. **🚨 PR-EM/EN 4차 시도(2026-05-16)에서 사고 발생** — 위 체크리스트 1~4 모두 충족됐음에도 cookie 발급 안 된 사용자에서 회귀. 누락된 안전망: **운영 telemetry 1주 관찰(PR-EL → 차단된 채 PR-EN 진행)** + **playwright e2e 4 role 인증 흐름 cookie 발급/차단 시나리오** (체크리스트 #5/#6). 5차 시도 전 반드시 두 가지 충족. **#5 충족: PR-EP(cba951c, 2026-05-17) — callback page 3 시나리오(200/401/network) playwright e2e 추가. 누적 e2e 8 통과.**
6. **graceful fallback 설계 개선 필요** — verifyAndHydrateFromMe가 401 vs network을 구별 시그니처로 호출처에 전달(`{user, reason: 'ok'|'unauthorized'|'network'}`). AuthGuard는 401이면 silent SSO trigger, network이면 stale user 유지. 현 PR-CY의 graceful은 cookie 만료 시점에 401 폭주를 표면화 못 함. **1차 충족: PR-EO(feb2a4c, 2026-05-17) — VerifyResult discriminated union + vitest 4 시나리오. AuthGuard 활용은 5차 본격 PR로 분리.**

### 추적

- PR-BP revert: b51fd72
- PR-BQ revert: 5ae788e
- PR-EN revert: b752a40 (2026-05-16, 4차 시도)
- PR-EM revert: 7ea0824 (2026-05-16, 4차 시도)
- 상태 → PR-EL telemetry만 살아있음(93f4d5b), 인증 흐름은 PR-BH 1단계와 동일(header+cookie 둘 다 허용)
- 체크리스트 #1/#3/#4 충족, #2는 결과적 안전(설계 차이) — PR-BP/BQ 2단계 재시도 가능 상태. 단 staging dual-run 검증(체크리스트 #5 PR-BL-5 / 별도 cycle 운영 telemetry #6)이 여전히 안전망 강화 필요
- 2026-05-16 PR-EL(93f4d5b): backend `dy.auth` logger.info("auth_via=header|cookie") 복구 — 체크리스트 #6 telemetry 충족. PR-EM(localStorage token 저장 중단) deploy 후 cookie 비율 모니터링으로 PR-EN(header 코드 완전 제거) go/no-go 판단 가능.
- 2026-05-16 PR-EM(9f5576e): frontend cookie-only 전환 (PR-BP+PR-BQ 재설계 통합본). `saveAuth(token, user)` token 인자 무시(signature backward-compat 유지) + `isLoggedIn` user-기반 + AuthGuard 부팅 시 `verifyAndHydrateFromMe` cookie validity 검증. 기존 PR-BP(/me hydration)는 PR-CY로 callback page에서 raw fetch 패턴 완성됐으며, AuthGuard에서도 동일 패턴 활용으로 무한 재귀 회피.
- 2026-05-16 PR-EN(b60d720): authFetch Authorization header 첨부 코드 완전 제거 + `getToken` 함수 제거. 사용자 명시 결정으로 운영 1주 관찰 없이 즉시 진행. 회귀 시 단독 revert로 header fallback 복귀 가능. vitest 33 통과.
- **2026-05-16 PR-EM/EN 운영 회귀 (4차 시도 실패)** — PR-EN deploy 직후 사용자 console에 `GET /api/auth/me 401` + 그 후 모든 API call 401 무한 반복. 원인: cookie 발급 안 된 운영 사용자가 PR-EM 이전엔 localStorage token으로 backend header fallback 인증 받고 있었음. PR-EM/EN으로 frontend가 header 첨부 안 함 → backend header fallback 무용지물. 즉시 revert: PR-EN(b752a40) + PR-EM(7ea0824). PR-EL telemetry 복구는 유지.

---

## 2026-05-15 — idle in transaction connection 4시간+ 잔존 → ALTER TABLE lock wait

### 증상

- Supabase advisor RLS enable 작업 중 `apply_migration` / SQL editor에서 ALTER TABLE 실행 시 `57014: canceling statement due to statement timeout` 반복.
- `pg_stat_activity` 조회 시 `state='idle in transaction'` connection이 4시간+ 잔존. `application_name=Supavisor`이고 `query`는 mirror_tasks/mirror_projects SELECT.
- 원인 connection이 ACCESS EXCLUSIVE lock 대기 중인 ALTER TABLE을 영구 차단.

### 원인

PR-AQ(get_db rollback + `pool_reset_on_return="rollback"`)가 적용됐어도 다음 시나리오에서 SQLAlchemy 정리 호출이 누락되는 것으로 추정:

1. **Render uvicorn worker OOM/SIGKILL** — 메모리 압박이나 platform restart로 worker가 정상 cleanup 없이 죽음. SQLAlchemy `__del__`/`close()`가 호출 안 됨.
2. **Supabase pooler(PgBouncer) TCP fin 인지 지연** — backend 측 socket이 닫혀도 pooler는 한동안 active 간주.
3. 결과: pooler에서 transaction이 idle 상태로 잔존 → 5분 cron + 사용자 요청이 누적될 때마다 leak 추가.

이 leak은 PR-AO(Supavisor pool 50 도달 사고)의 root cause이기도 함.

### 조치 (PR-DA)

`backend/app/db.py`에 connection 시점 event listener 추가:

```python
@event.listens_for(engine, "connect")
def _set_session_params(dbapi_conn, _conn_rec):
    if _is_sqlite:
        return
    with dbapi_conn.cursor() as cur:
        cur.execute("SET idle_in_transaction_session_timeout = '300s'")
```

5분 안에 PostgreSQL이 자동으로 transaction rollback + connection 종료.
backend 측 정리가 누락돼도 DB 측에서 강제 회수.

connection-level 적용 — `ALTER DATABASE`로 cluster default 변경 X (다른 사용자/프로젝트 무관).

### 즉시 복구 (사고 시점)

```sql
-- 잔존 idle in transaction 강제 종료 (ALTER 진행 가능하게)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND application_name LIKE 'Supavisor%';
```

### 검증

PR-DB로 `/api/health/db` 응답에 `idle_in_transaction_session_timeout` 노출:

```bash
curl https://dy-task-backend.onrender.com/api/health/db
# {"status":"ok","idle_in_transaction_session_timeout":"5min"}
```

배포 직후 Supabase pg_stat_activity 재조회 시 idle in transaction 0건 확인.

### 교훈

- **backend cleanup만으로는 leak 차단 불충분** — worker가 비정상 종료할 수 있는 환경(Render 등 PaaS)에서는 DB-side timeout이 마지막 방어선.
- **`/api/health/db` 같은 endpoint에 진단용 SHOW 노출은 운영 검증을 단순화한다** — Supabase MCP는 다른 세션 설정을 못 보므로 backend 자기 connection의 SET 적용 여부는 self-report 외 검증 어려움.
- **connection-level `SET`는 cluster default 변경(`ALTER DATABASE`)보다 안전** — 다른 사용자/프로젝트에 영향 없음.

### 추적

- PR-DA (5분 timeout): 2687eb4
- PR-DB (health endpoint 확장): 0a6f663
- PR-DB (alembic file alembic_version 포함, 운영 일치): 3e388c9
- 검증 시점: 2026-05-15. 운영 `/api/health/db` 응답 `"5min"` 확인.
- **🚨 2026-05-22 재검증 결과: 운영 `/api/health/db` 응답이 `"0"`으로 회귀** — 5회 연속 호출 모두 `"0"`. PR-DA event listener(`connect` 시점 `SET idle_in_transaction_session_timeout='300s'`)가 실제 운영 connection에 적용되지 않은 상태. 가설: Supavisor Session mode pooler가 SET을 backend에 propagate 안 하거나 pool checkin 시 reset함. 영향: 2026-05-22 backend hang 사고에서 DB-side 안전망이 작동 안 했을 가능성. **추적 항목**: (a) BEGIN/COMMIT 명시 transaction으로 SET 감싸기 / (b) 매 query 전 `SET LOCAL` 전환 / (c) cluster-wide `ALTER DATABASE` (INCIDENT.md 본 entry에서 의도적으로 회피했던 옵션 — Codex 상의 후 결정). PR-DB의 SHOW 노출 덕분에 회귀가 표면화된 점은 안전망 설계 검증 사례.

---

## 2026-05-17 — alembic_version은 head인데 일부 테이블 schema 누락 → weekly-report 500

### 증상

- 사용자가 `/weekly-report` 진입 시 브라우저 console에 CORS 차단 메시지 + `500 Internal Server Error`.
- backend log: `sqlalchemy.exc.ProgrammingError: (psycopg.errors.UndefinedTable) relation "weekly_report_publish_log" does not exist`.
- 다른 endpoint (예: `/api/projects`, `/api/sales`)는 정상 응답.
- CORS는 OK이지만 500 응답에 CORS header가 안 붙어 브라우저는 CORS 차단으로 표시 (혼동 유발).

### 원인

production DB의 alembic_version = `75b02f886038` (head)이지만 실제 schema에는 `weekly_report_publish_log` 테이블이 없음. 두 가지 가설:

1. 어느 시점에 DB가 reset/migrate되면서 alembic_version은 `stamp head`로 동기화됐지만 누락된 migration 실제 DDL은 안 적용.
2. 옛 deploy에서 alembic upgrade가 silent fail 후 다음 deploy가 이미 head라고 판단해 skip.

추가 회귀 (동시 발생):
- `_build_suggestions`가 옛 시그니처(`list_suggestions(notion=...)`) 호출 — PR-EX/3에서 mirror DB 전환됐는데 호출 흐름 미갱신. `TypeError: list_suggestions() got an unexpected keyword argument 'notion'` (PR-FI/11 fix).

### 즉시 조치

Render shell에서 모든 model 명시 import + `Base.metadata.create_all(bind=engine)` 실행:

```bash
uv run python -c "from app.db import Base, engine; from app.models import auth, calendar_event, contract, drive_creds, employee, mirror, notice, snapshot, weekly_publish; Base.metadata.create_all(bind=engine); print('done')"
```

`create_all`은 `checkfirst=True` default → 기존 테이블엔 영향 없이 누락분만 생성. `weekly_report_publish_log` + `contracts` (PR-FH/1) 모두 채워짐.

### 추적 항목 (별도 cycle 진행)

- [x] **`db.py init_db()`에 `contract` + `notice` import 추가** — PR-FI/12. 신규 model 추가 시 dev/test 환경에서 SQLAlchemy 자동 생성에 포함되도록 보강. 본 사고의 재발 방지(누락된 model 발견 즉시 dev에서 ImportError로 잡힘).
- [ ] **production DB alembic_version 무결성 모니터링 endpoint** — `/api/health/db`에 `alembic head` vs 실제 `inspect(engine).get_table_names()` 차이 노출 권장.
- [ ] **`list_*` 같은 cross-module 호출 회귀 테스트** — `_build_suggestions` 같이 router 간 dependency가 변경됐을 때 pytest로 잡히지 않음. weekly-report endpoint e2e (인증된 시나리오)로 회귀 보강.

### 교훈

- **alembic_version은 head라도 schema 실제 일치는 보장 안 됨** — `alembic upgrade head`가 "이미 head"라고 판단하면 skip. 실제 DDL 적용 여부 별도 검증 필요.
- **500 응답 + CORS 헤더 누락 = 브라우저 CORS 차단 메시지** — CORS 메시지 보이면 actual response (status + body)부터 확인. backend log 1줄이 진단의 90%를 결정.
- **`Base.metadata.create_all(checkfirst=True)`는 운영 복구용 안전한 수단** — alembic 외 우회 경로로도 누락된 테이블 채울 수 있음.

---

## 2026-05-22 — backend hang(분 단위) → /api/health/db 503 → Render auto-restart (PR-DY 안전망 첫 발동)

### 증상

- 사용자가 `/weekly-report` 진입 시 브라우저 console에 CORS 차단 메시지:
  ```
  Access to fetch at 'https://dy-task-backend.onrender.com/api/seal-requests/pending-count'
  from origin 'https://task.dyce.kr' has been blocked by CORS policy:
  No 'Access-Control-Allow-Origin' header is present on the requested resource.
  ```
- 직접 curl로는 preflight 200 + GET 401 모두 CORS 헤더 정상 — 사고 후 시점엔 정상화돼 재현 안 됨.
- **사용자 보고**: "중간중간 계속 딜레이가 되는 현상이 많아" — 본 사고가 단발성이 아니라 만성 hang의 한 표면화임을 시사.

### Render 로그 — 사고 윈도우

```
slow GET /api/health/db — 20001ms (status=503)
[GET] /api/projects?assignee=... responseTimeMS=3287073   ← 약 55분
[GET] /api/projects?mine=true   responseTimeMS=3022196   ← 약 50분
[GET] /api/tasks?mine=true      responseTimeMS=4029162   ← 약 67분
[GET] /api/tasks?mine=true      responseTimeMS=4197076   ← 약 70분
==> Instance srv-d7mu51vavr4c73f9q960-b2g2h restarted
... (재부팅)
노션 schema 보강 중 예외 (무시)
httpx.HTTPStatusError: Server error '502 Bad Gateway' for url
  'https://api.notion.com/v1/data_sources/31de8498-6c86-8029-b4e2-000bf5992d7d'
slow GET /api/health/db — 1426ms (status=200)   ← 회복 진행
```

### 원인 (가설 — Codex MCP 검증 반영 2026-05-22)

1. **노션 API 측 일시 장애** — 재부팅 직후 `api.notion.com` `502 Bad Gateway` 직접 관찰. 노션 SDK 1회 호출은 자체 60s timeout. `_RETRY_DEADLINE_S=60s`이므로 timeout류는 보통 1회에서 deadline 소진 (4 attempts × 60s = 240s 가 아님 — 초기 작성 시 부정확했던 부분 정정).
2. **진짜 hang 진원지** — 사용자 facing 라우터 중 노션을 await하면서 `Depends(get_db)` DB session도 같이 잡고 있는 곳: `weekly_report.py:228 _build_full_report` / `weekly_report.py:128 _build_seal_log` / `seal_requests/list_endpoint.py:70 list_seal_requests`. `/weekly-report` 진입이 이 endpoint들을 동시 호출 → 워커당 connection 동시 점유.
3. **`/api/projects?mine` / `/api/tasks?mine`의 분 단위 hang은 endpoint 자체 문제가 아니라 2차 피해** — `projects.py:198` / `tasks.py:55`는 **mirror-only**(노션 호출 없음). 노션 hang으로 DB pool/워커가 고갈된 동안 줄서서 fail하면서 응답 시간이 분 단위로 표시된 것. 초기 작성 시 진원지로 잘못 분류했던 부분 정정.
4. **추가 위험: async 라우터에서 sync SQLAlchemy 직접 호출** — pool 대기 시 워커 이벤트 루프 자체가 막힘. cascade 가속 메커니즘. (Codex MCP 신규 식별)
5. **DB connection pool 고갈 cascade** — 위 진원지 endpoint들이 노션 hang 동안 connection 점유 → 워커당 15개 pool 빠르게 소진 → health check가 pool에서 connection 못 얻어 20초 timeout → 503.
6. **사용자의 CORS 에러는 hang의 외부 증상** — backend가 응답 못 하는 동안 Render LB가 timeout 503/connection drop을 자동 반환. CORSMiddleware를 거치지 않은 응답이라 헤더 부재 → 브라우저는 CORS 차단으로 표시 (INCIDENT.md 2026-05-12 / 2026-05-17 동일 메커니즘).

### 조치

- **자동 복구** — `render.yaml healthCheckPath: /api/health/db`(PR-DY)가 의도대로 동작. health check 503 → Render auto-restart trigger → 정상화. **PR-DY 안전망의 첫 실전 발동.**
- 재부팅 후 정상 응답 복귀 확인 (`slow GET /api/health/db — 1426ms (status=200)` → 평시 latency).
- 즉시 사용자 영향 종료. 추가 수동 조치 불필요.

### 교훈

- **PR-DY 안전망은 작동했지만 사용자 경험은 여전히 나쁨** — auto-restart까지 사용자는 몇 분 hang을 직접 겪음. health check timeout(20초) + Render restart sequence(수십 초) 누적. 만성 hang 자체를 줄이지 않으면 안전망만으론 부족.
- **노션 API 응답성에 backend가 노출돼 있음** — 노션 retry deadline 60초 × 4회 = 240초 hang. 단일 endpoint hang이 노션을 쓰지 않는 endpoint(`pending-count`는 mirror DB SELECT만)까지 영향 줄 만큼 DB pool 압박 발생.
- **사용자가 "계속 딜레이"라고 말하면 단발 사고가 아닌 capacity/resilience 문제로 재분류해야 함** — 본 사고는 documented 사례 1건이지만 사용자 체감은 빈번. 만성 hang root cause 추적 필요.

### 추적 항목 (Codex MCP 상의 반영 — 별도 cycle 진행)

**즉시 (다음 배포)**
- [ ] **옵션 C: user-facing 노션 호출 deadline 단축** — 현재 60s deadline + 4 attempts를 사용자 응답 path에선 **3~5초 deadline + 0~1회 retry**로 축소. context별 deadline 주입 인터페이스 도입. 효과: 전역 hang 차단. 위험: 노션 잠깐 느릴 때 502가 사용자에게 더 자주 노출.
- [ ] **옵션 B: DB session lifecycle 분리** — `_build_full_report` / `_build_seal_log` / `list_seal_requests` 등 노션 await 전에 `db.close()` (또는 짧은 세션 스코프). connection 점유 차단. 위험: object detached / 세션 재사용 패턴 가이드 필요.

**다음 스프린트**
- [ ] **옵션 A: weekly-report/dashboard user-facing GET에서 노션 fallback 제거** — mirror DB만 SELECT. stale(최대 5분) 사용자 노출 허용. seal/suggestion mirror 이미 존재해 전환 여지 큼.
- [ ] **Circuit Breaker / Bulkhead 도입** — 노션 502 연속 시 일정 시간 fallback fast-fail. 동시 노션 호출 수 제한. (Codex 신규 제안)

**조건부 / 모니터링**
- [ ] **옵션 D: background sync 풀 분리** — `render.yaml:47` cron이 separate process인지 운영 확인 필요. same-process면 우선도↑, 이미 분리면 우선도↓.
- [ ] **async/sync 정합성 정리** — async 라우터에서 sync SQLAlchemy I/O 직접 호출 패턴 축소. 큰 안건, 별도 cycle.
- [ ] **`/api/health/db` `idle_in_transaction_session_timeout: "0"` 별건 진단** — PR-DA event listener가 health check connection에 적용 안 됨 의심. 본 사고에서 DB-side 안전망이 정상이었다면 backend hang이 더 일찍 정리됐을 가능성.
- [ ] **만성 딜레이 telemetry** — slow request middleware(`main.py:97`) 임계값 이상 요청 daily 집계. 사용자 "중간중간 계속 딜레이" 보고와 cross-check 가능하게.
- [ ] **노션 API 가용성 모니터링** — `api.notion.com` 502/timeout 발생률 로깅. 노션 측 장애 vs backend 측 문제 구분.
- [ ] **운영 환경 확정** — Render plan(starter/standard) + cron 분리 여부 한 번 확인. 우선순위 정확도 상승.

### 참고

- 본 사고는 INCIDENT.md 2026-05-12(connection leak), 2026-05-17(500 + CORS 헤더 누락)의 안전망(PR-DA / PR-DB / PR-DY)이 모두 작동한 첫 케이스.
- 코드 변경 없이 자동 복구됐으므로 즉시 PR 불필요.
- 진단/우선순위는 Codex MCP 상의 결과 반영 (2026-05-22). 권장 조합: **C + B 즉시 배포, 다음 스프린트 A + circuit breaker**.
