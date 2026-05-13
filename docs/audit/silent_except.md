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

### 2. 외부 API 호출 silent — **위험. logger 추가 필요** (12 case)

**완료 (PR-BV):**
- ✅ `routers/projects.py:117` — 프로젝트 담당 변경 이력 page 생성 실패 → `logger.warning`
- ✅ `routers/master_projects.py:395` — `sync_master_blocks` write-through 실패 → `logger.warning`

**잔여 (별도 cycle):**
- `routers/seal_requests.py:643/645/876/1460/1489` — Drive 업로드 / Notion update 실패 시 `failed.append`만, logger 없음. 일부는 partial_errors 응답 schema와 함께 정리.
- `services/quote_code.py:60` — quote type fallback (default `STRUCT_DESIGN`) — 이건 의도일 수 있음, 검토 필요
- `services/weekly_report.py:691/888` — 주간 일지 집계 fallback (휴가 라벨 / duration_months) — 의도, OK 가능성 큼
- `routers/cashflow.py:31` — payer 이름 resolution fallback — 검토 필요
- `routers/projects.py:670` — review folder state count 실패 fallback — 검토 필요

### 3. 정상 fallback (Optional 함수) — 약 4 case

`routers/dashboard.py:285` (`_extract_date` invalid → `None`), `routers/projects.py:616`
(`_extract_resource_key`) 등. logger 없이 OK.

## 다음 작업 권장

1. **2차 — 잔여 외부 API silent (5 case)**: Drive/Notion 호출 silent를 모두
   `logger.warning` + 가능 시 `failed.append` 통합.
2. **3차 — partial_errors 응답 schema** (외부 리뷰 12.x #1 본격): API 응답에
   `partial_errors: [{code, target, retryable, message}]` 필드 추가. 호출처
   frontend에서 toast로 노출.
3. **4차 — Drive·Notion atomicity** (외부 리뷰 12.x #2): `try/except + 보상 트랜잭션`
   1차, `outbox + saga` 2차.

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
