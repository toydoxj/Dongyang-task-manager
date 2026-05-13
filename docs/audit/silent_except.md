# Backend silent except audit (외부 리뷰 12.x #1)

> 마지막 업데이트: 2026-05-13 (PR-BV)

`backend/app/**/*.py`에서 `except: pass / return / continue` 패턴(logger 없이 묻힘)
audit 결과. silent except는 **부분 실패가 운영자/사용자에게 인지되지 않아** 사고 추적
지연 + 데이터 불일치 누적 위험.

## 분류 — 41 case

### 1. 의도적 (수정 불요) — 약 25 case

date 파싱 실패 시 `None` 반환, JWT 만료 시 logout idempotent 등 **타입 변환·정상
fallback** 케이스. logger 없이 OK.

대표 예:
- `security.py:30` — `bcrypt.checkpw` ValueError → `False` 반환 (잘못된 hash 형식)
- `services/sync.py:67/77/80` — `_parse_date` invalid ISO → `None`
- `models/task.py:131` — KST 변환 실패 시 원본 반환
- `routers/auth.py:365` — JWT decode 실패 시 logout idempotent (의도)
- `routers/seal_requests.py:212/318/452/534/596/629` — query string 파싱 fallback / bg task loop 부재 시 skip

### 2. 외부 API 호출 silent — **위험. logger 추가 완료**

**완료 (PR-BV):**
- ✅ `routers/projects.py:117` — 프로젝트 담당 변경 이력 page 생성 실패 → `logger.warning`
- ✅ `routers/master_projects.py:395` — `sync_master_blocks` write-through 실패 → `logger.warning`

**완료 (PR-BW):**
- ✅ `routers/projects.py:670` — review folder list_children 실패 → `logger.warning`

**점검 결과 — 추가 fix 불요 (audit script 오탐 정정):**
- `routers/seal_requests.py:643/645` — 이미 `logger.warning` 있음 (audit script가 같은 line 위 5줄 windows 안에 logger 못 잡음).
- `routers/seal_requests.py:876/1460/1489` — `failed.append` 응답 schema에 partial 실패 명시 중. 사용자가 응답에서 확인 가능 → silent 아님.
- `services/quote_code.py:60` — quote type fallback (default `STRUCT_DESIGN`). 코드 분류 휴리스틱이라 의도. OK.
- `services/weekly_report.py:691/888` — 주간 일지 집계 (휴가 라벨 / duration_months). 의도적 fallback. OK.
- `routers/cashflow.py:31` — date parse fallback (`None` 반환). 의도. OK.

### 3. 정상 fallback (Optional 함수) — 약 4 case

`routers/dashboard.py:285` (`_extract_date` invalid → `None`), `routers/projects.py:616`
(`_extract_resource_key`) 등. logger 없이 OK.

## 다음 작업 권장

silent except logger 1차 마감 — 외부 API silent 모두 `logger.warning` 또는
`failed.append` 처리됨. 다음 단계는:

1. **partial_errors 응답 schema** (외부 리뷰 12.x #1 본격): seal_requests의
   `failed[]`를 정형화 — `partial_errors: [{code, target, retryable, message}]` 필드.
   호출처 frontend에서 toast로 노출. seal_requests 외 다른 곳에도 적용.
2. **Drive·Notion atomicity** (외부 리뷰 12.x #2): `try/except + 보상 트랜잭션`
   1차, `outbox + saga` 2차.
3. **`_sync_sale_estimated_amount` race** (12.x #3): row-level lock 또는 transactional
   집계 update.
4. **`query_all` 페이징** (12.x #4): 우선순위 낮음 — mirror sync로 완화 중.

## audit 명령

```bash
cd backend/app && python3 -c "
import re, os
silent = []
for root, _, files in os.walk('.'):
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        with open(path) as fp:
            lines = fp.readlines()
        for i, line in enumerate(lines):
            if not re.match(r'\s+except[^:]*:\s*(?:#.*)?\$', line): continue
            block = ''.join(lines[i+1:i+5])
            if 'logger' in block or 'logging' in block or 'raise' in block: continue
            silent.append(f'{path}:{i+1}')
for s in silent: print(s)
print(f'total: {len(silent)}')
"
```
