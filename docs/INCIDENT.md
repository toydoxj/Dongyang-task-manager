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

- [ ] weekly_report `_report_cache`가 ORM 객체 보유 여부 검토
- [ ] background sync (5분 incremental) session close 보장
- [ ] PDF route (`build_weekly_report_pdf` 등)의 db 의존성 정리
- [ ] silent except path에서 db.close() 누락 점검
- [ ] `/api/health/db` 라우트 + Render health check path 교체

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

### 추적

- PR-BP revert: b51fd72
- PR-BQ revert: 5ae788e
- 상태 → PR-BO + PR-BN 시점(ce6f264) 안정 운영 중
- 체크리스트 #1/#3/#4 충족, #2는 결과적 안전(설계 차이) — PR-BP/BQ 2단계 재시도 가능 상태. 단 staging dual-run 검증(체크리스트 #5 PR-BL-5 / 별도 cycle 운영 telemetry #6)이 여전히 안전망 강화 필요

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
