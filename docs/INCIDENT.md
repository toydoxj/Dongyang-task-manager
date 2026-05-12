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
