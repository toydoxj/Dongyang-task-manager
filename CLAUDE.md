## 지침

1. 모든 절차를 진행할 때는 Codex mcp를 불러서 상의 후 결정. 코드 작성 후에도 확인 절차 진행
2. 에러 발생시 해당 에러는 /.claude/rule/error.md에 작성하여 반복되지 않도록 함.


**트레이드오프:** 이 지침은 속도보다 신중함에 가중치를 둠. 사소한 작업에는 판단에 따라 유연하게 적용할 것.

## 1. 코딩 전에 먼저 생각할 것

**가정하지 말 것. 혼란을 숨기지 말 것. 트레이드오프를 드러낼 것.**

구현하기 전에:

- 가정을 명시적으로 진술할 것. 불확실하면 질문할 것.
- 여러 해석이 가능하면 모두 제시할 것 — 임의로 선택하지 말 것.
- 더 단순한 접근법이 있다면 그 점을 말할 것. 필요하다면 반대 의견을 제시할 것.
- 불명확한 부분이 있으면 멈출 것. 무엇이 혼란스러운지 명시하고 질문할 것.

## 2. 단순함을 우선할 것

**문제를 해결하는 최소한의 코드만 작성할 것. 추측성 코드 금지.**

- 요청 범위를 벗어난 기능 추가 금지.
- 일회성 코드를 위한 추상화 금지.
- 요청되지 않은 "유연성"이나 "구성 가능성" 추가 금지.
- 발생할 수 없는 시나리오에 대한 예외 처리 금지.
- 200줄을 작성했는데 50줄로 가능했다면, 다시 작성할 것.

스스로에게 물을 것: "시니어 엔지니어가 이 코드를 보고 과도하게 복잡하다고 할까?" 그렇다면 단순화할 것.

## 3. 외과적 수정

**필요한 부분만 건드릴 것. 자신이 만든 흔적만 정리할 것.**

기존 코드를 수정할 때:

- 주변 코드, 주석, 포맷팅을 임의로 "개선"하지 말 것.
- 망가지지 않은 것을 리팩터링하지 말 것.
- 본인의 스타일이 다르더라도 기존 코드 스타일을 따를 것.
- 무관한 데드 코드를 발견하면 언급만 할 것 — 임의로 삭제하지 말 것.

수정으로 인해 고아 코드가 발생한 경우:

- **본인의 수정으로 인해** 사용되지 않게 된 import, 변수, 함수만 제거할 것.
- 별도 요청이 없는 한, 기존부터 존재하던 데드 코드는 제거하지 말 것.

판단 기준: 변경된 모든 줄은 사용자의 요청과 직접적으로 연결되어야 함.

## 4. 목표 기반 실행

**성공 기준을 정의할 것. 검증될 때까지 반복할 것.**

작업을 검증 가능한 목표로 변환할 것:

- "유효성 검증 추가" → "잘못된 입력에 대한 테스트를 작성하고 통과시킬 것"
- "버그 수정" → "버그를 재현하는 테스트를 작성한 뒤 통과시킬 것"
- "X 리팩터링" → "변경 전후 모두 테스트가 통과하도록 보장할 것"

다단계 작업의 경우, 간략한 계획을 먼저 진술할 것:

```
1. [단계] → 검증: [확인 방법]
2. [단계] → 검증: [확인 방법]
3. [단계] → 검증: [확인 방법]
```

---

## 5. 프로젝트 환경 (Task_DY 특화)

**Stack:** FastAPI + Postgres(SQLAlchemy 2 + alembic) + Notion API + NAVER WORKS Drive ↔ Next.js 16 + React 19 + Tailwind 4 + shadcn/ui + Zustand + SWR + WeasyPrint(PDF)

**명령어**
- `cd backend && uv add 'pkg>=v'` — pip은 PEP 668 차단, uv 필수
- `cd backend && source .venv/bin/activate && python -c "..."` — 로컬 검증
- `cd backend && source .venv/bin/activate && pytest tests/ -x` — 단위 테스트 (실패 즉시 중단)
- `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload` — dev 서버 (port 8000)
- `cd backend && alembic heads` / `alembic upgrade head` — DB schema
- `cd frontend && npx tsc --noEmit` — type check
- `cd frontend && npm run dev` / `npm run build` / `npm run lint`
- `pdftoppm -r 100 -png in.pdf out` — PDF→PNG 시각 디버깅 (poppler 설치됨)

**핵심 패턴**
- `quote_form_data` 신 schema: `{forms:[{id, doc_number, suffix, input, result, is_external?, attached_pdf_*?}]}`. POST/PATCH /sales 라우터에서 단일 schema → list-wrap 즉시 변환 필수 (안 하면 `normalize_quote_forms`가 매 호출 새 uuid → quote_id mismatch).
- alembic version naming: 직전 revision + 새 영문 prefix `{x}{prev}{date}_desc.py`.
- 노션 schema: `backend/app/services/notion_schema.py SALES_DB_REQUIRED` dict 부팅 시 자동 등록. drop은 노션 UI 수동.
- 단가: `backend/app/services/quote_calculator.py ENGINEERING_RATES_BY_GRADE` (매년 1월 갱신).
- 견적서 11종 + `_CODE_MAP` 분류 코드 (구조설계 01 ~ 기타 99). 영업당 다중 견적 모델 (PR-M) — `parent_lead_id` 폐기됨.
- 시특법 자동 산정 helper: `backend/app/services/inspection_legal_table.py` (별표 22~26 + 보간). PR-Q5b.
- 건축물관리법 자동 산정 helper: `backend/app/services/bma_table.py` (별표 1·3 + 제37조 군집). PR-Q4b.
- 영업코드 형식: `영{YY}-{NNN}` (옛 `{YY}-영업-{NNN}`도 sequence pool 포함 — `services/sales_code.py`).
- 견적별 영업정보 동기화: `QuoteInput.sync_with_sale: bool` (default True) — 한 영업에 대상 건축물이 다른 견적 케이스 대응. SalesEditModal echo useEffect는 false면 차단.
- 견적별 준공년도 자동 경과년수: `completion_year` 입력 시 KST 기준 `now.year - completion_year` 자동.
- 영업↔프로젝트 reverse lookup: `GET /api/sales/by-project/{project_id}` (converted_project_id indexed).
- 묶음 PDF 갑지 총액 토글: `?show_total=true|false` (기본 ON).
- xlsx 검증: `docs/quote_formulas/*.md` dump → backend strategy transcribe → ±0원 일치.
- mirror_seal_requests (PR-CL): pending-count는 노션 query_all이 아니라 mirror DB `SELECT COUNT(*)`. write 흐름(create/update/approve/reject)은 즉시 `_upsert_seal_request` (PR-CQ). 5분 cron이 회수 안전망.
- 건의사항 노션 schema (PR-CN/CO/CP): title=`내용` (dynamic lookup), 구분=multi_select(필드 추가됨), 방안=text, 진행상황=status, 조치내용=text, 작성자=multi_select. schema 불일치 시 502 NotionApiError — 운영 노션 UI에서 직접 정정.
- `/api/health/db` 응답에 `idle_in_transaction_session_timeout` SHOW 결과 포함 (PR-DB). PR-DA가 backend 연결에 적용됐는지 검증용.

**PR-W 주간업무일지 패턴**
- `build_weekly_report(week_start, *, week_end=None, last_week_start=None)` — 3개 날짜 input. default: `week_end = week_start + 4`, `last_week_start = -7`, `last_week_end = week_start - 1day` (자동, 토일 cover).
- bulk pre-fetch: `aggregate_team_work` / `aggregate_team_projects`는 mirror_tasks 한 번에 fetch → 메모리 dict로 N+1 회피 (32s → 0.8s).
- 완료 cutoff = `Project.end_date(완료일)` 기준 (last_edited_time 아님). 종결/타절 stage도 포함.
- 신규 cutoff = `Project.start_date(수주일)` 기준. stage 휴리스틱 폐기.
- 영업 cutoff = `mirror_sales.sales_start_date` (별도 노션 컬럼 — 운영자 수동 입력).
- 대기 정의: 팀별업무에 안 올라온 [진행중+대기] 프로젝트. `aggregate_stage_projects(stages, exclude_ids)`. 3개월 이상 대기는 `is_long_stalled=True`.
- task source 식별: `mirror_tasks.sales_ids` (영업) vs `project_ids` (프로젝트). EmployeeWorkRow.kind / PersonalScheduleEntry.kind에 노출.
- 작업단계(phase) — `Project.phase` 노션 "작업단계" select 자동 보강. 운영 stage(진행중/대기/보류)와 별개. UI는 phase 표시.
- 휴가 라벨 (`_vacation_label`): task.title 키워드(`반차`/`연차`) 우선 매칭 — '오전반차'/'오후반차'도 모두 '반차'로 단일화. 키워드 없으면 duration ≥4h 연차 / <4h 반차 fallback.
- 날인대장: status='승인' + admin_handled_at이 저번주 범위 안. 제출처 = real_source_id 우선 → 발주처 fallback. 응답은 approved_at 오름차순.
- 견적서 첫 추가 시 노션 task 자동 생성 (`_create_quote_task_for_sale`, idempotent).
- 주간일지 발행 (PR-W publish): `POST /api/weekly-report/publish` (admin only) → WORKS Drive `[주간업무일지]/{YYYYMMDD}_주간업무일지.pdf` 업로드 + 전직원 Bot 알림 + `weekly_report_publish_log` row. `GET /weekly-report/last-published(.pdf)` — 다음 일지 default lastWeekStart 셋팅 + 비admin용 다운로드.
- role enum: `admin / team_lead / manager / member`. manager(관리팀)는 운영 관리(프로젝트/영업/발주처/수금/지출/계약서) 위주 9개 메뉴만 노출 — backend API 권한은 추후 확장.

**운영자 1회 수동 단계 (노션)**
- 메인 프로젝트 DB: "작업단계" select 컬럼 (자동 보강 — 부팅 시 옵션 union)
- 영업 DB: "영업시작일" date 컬럼 (자동 보강), "전환된 프로젝트" relation (수동)
- task DB: "영업" relation 컬럼 (relation은 자동 생성 미지원 — 운영자가 직접 추가). 부재 시 부팅 로그 warn.
- notices 테이블 kind enum: 공지|교육|휴일
- WORKS Drive 루트의 `[주간업무일지]` 폴더는 첫 발행 시 자동 생성 (create_folder 409 fallback로 idempotent).

**Quirks**
- frontend: Next.js 16 / React 19 (학습 데이터와 차이) — `node_modules/next/dist/docs/` 참조
- backend: KST `_KST = timezone(timedelta(hours=9))`
- WeasyPrint paged media: flex `justify-content: center` 부분 동작. `running()` element는 page bottom margin 영역에 자동 배치.
- Render: backend Docker 빌드 5-8분 (WeasyPrint + cairo + fonts-nanum). 짧은 시간 6+ commits push → pipeline limit (dashboard에서 큐 cancel 또는 plan 업그레이드).
- 한글 파일명 표기 주의 ("프**레**젠테이션" vs "프**리**젠테이션").
- PDF 결과 검증 protocol: build_quote_pdf() → /tmp PDF → pdftoppm PNG → Read 시각 확인 → 사용자 OK → push.
- DB connection cleanup (PR-DA): backend connect 시 `SET idle_in_transaction_session_timeout='300s'` 자동 적용 (`db.py` event listener). Render worker OOM/restart로 SQLAlchemy 정리 누락돼도 5분 안에 PostgreSQL이 자동 rollback + close. cluster-wide ALTER DATABASE 대신 connection-level. ALTER TABLE lock wait 사고 회피.

**주요 디렉터리**
- `backend/app/routers/sales/` — 영업/견적 패키지 (PR-CC~CF). `__init__.py` (CRUD) + `quote_meta.py` (read-only meta+preview) + `link.py` (project↔sale) + `pdf.py` (PDF endpoints).
- `backend/app/routers/seal_requests/` — 날인 패키지 (PR-CG~CW, 8 sub-module). `__init__.py` 1826→699 (-62%). `meta.py` / `attachments.py` / `approval.py` / `update.py` / `delete.py` / `list_endpoint.py` / `create.py`. list endpoint는 함수만 export + `__init__.py`에서 `add_api_route("", _list.list_seal_requests, ...)` (sub-router prefix="" FastAPI 충돌 회피).
- `backend/app/services/quote_*.py` — 산출 strategy / PDF / forms helper
- `backend/app/templates/quote_template.html` — PDF Jinja2 템플릿
- `backend/app/services/weekly_report.py` — PR-W 집계 (10+ aggregate 함수)
- `backend/app/routers/weekly_report.py` — async 라우터 (날인/건의 노션 직접 조회)
- `backend/app/templates/weekly_report.html` + `_schedule_mini.html` — PR-W PDF
- `backend/app/services/weekly_snapshot.py` — 일요일 23:59 KST cron (Δ 인프라)
- `backend/app/models/{notice,snapshot}.py` — PR-W 신규 도메인
- `frontend/app/weekly-report/page.tsx` — 주간 일지 페이지 (PDF 동등 양식)
- `frontend/app/admin/notices/page.tsx` — 공지/교육/휴일 관리 (admin)
- `frontend/components/sales/SalesEditModal.tsx` — 영업 모달 (견적 list view + form view)
- `frontend/components/sales/QuoteForm.tsx` — 견적 입력 form
- `frontend/components/me/SaleTaskRow.tsx` — /me 영업 task row (ProjectTaskRow 동등 패턴)
- `backend/app/models/weekly_publish.py` — 발행 로그 모델 (alembic `d9b0c1d05011`)
- `backend/app/services/sso_drive.py` / `sso_works_bot.py` — Drive 업로드 / Bot send_text
- `docs/quote_formulas/*.md` — xlsx 산출식 dump (PR-Q0 산출물)
