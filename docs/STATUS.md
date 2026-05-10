# 작업 Status

> 마지막 업데이트: 2026-05-10 (Phase 0 검증 fix 포함)

## 완료된 PR

| 영역 | 내용 | 핵심 commit |
|---|---|---|
| **PR-Q** 견적서 분류 | 8종 분류 + 산출 strategy 11개 dispatch + 통합 PDF (PR-Q1~Q9 + PR-G1) | (이전) |
| **PR-Q5b** 시특법 자동 산정 | 별표 22~26 보간·보정·추가과업 + PDF 2페이지 산정 상세 (`inspection_legal_table.py`) | a0c91c1 |
| 시특법 후속 fixup | 산식 표기 / default 단가 / sync 토글 / 완공년도 자동 / legacy 제거 / VAT 포함·별도 / 외부 견적 VAT | b7d39e5 ~ cf5d257 |
| **PR-Q4b** BMA 자동 산정 | 건축물관리점검지침 별표 1·3 + 제37·38조 + 산정표 ±1원 일치 (`bma_table.py`) | 78bdb0f / d224e62 |
| **영업코드 형식** | `{YY}-영업-{NNN}` → `영{YY}-{NNN}` (옛 형식도 sequence pool 포함) | cf5d257 |
| **PR-LK** 영업↔프로젝트 | reverse lookup endpoint + 동일 프로젝트 날인요청 N개 허용 | 9e36b3b |
| **PR-W** 주간업무일지 | 9개 섹션(인원현황/공지/완료/날인대장/영업/신규/개인일정/팀별업무/대기·보류) + WeasyPrint PDF + admin 발행(Drive 업로드 + 전직원 Bot 알림 + `WeeklyReportPublishLog`) + 비admin `last-published.pdf` 다운로드 + 일요일 23:59 KST `weekly_snapshot` cron + manager role 사이드바 | 9e36b3b ~ 56e306d |
| **CLAUDE.md 개선** | root + frontend/AGENTS.md + backend/CLAUDE.md (신규) | (커밋 외) |
| **Phase 0 품질·권한·문서** | lint 56→0 (set-state-in-effect / exhaustive-deps / purity / static-components 본격 fix) + `/admin/incomes`·`/sales` admin\|\|manager 가드 정합 + `/admin/{expenses,contracts}` placeholder + `UnauthorizedRedirect` (1.5초 toast → 자동 redirect) + USER_MANUAL.md 동기화 | 27ad9e6 ~ c33299c |
| **Phase 0 검증 fix** | playwright 4 역할 시나리오 검증 중 발견 — `AuthGuard` catch fallback에 `setUser(getUser())` 추가 (backend down 시 가드 무력화 fix) + `/help` page를 USER_MANUAL.md에 동기화 (대시보드 manager 라벨 / Bot 알림 표 주간업무일지 행 / FAQ 자동 TASK 항목) | 신규 commit |

## 미완료 / 보류

| 항목 | 상태 | 비고 |
|---|---|---|
| **Phase 1 UX 1차** | 계획만 | DASH/PROJ/MY/WEEK 상단 KPI·액션 패널·프리셋·요약 — `.claude/plans/federated-stirring-hedgehog.md` |
| **Phase 4-B SalesEditModal 본격 분해** | 보류 | 1500+ 줄 단일 컴포넌트 — set-state-in-effect 8건 file-level disable + TODO 표시 (`SalesEditModal.tsx`) |
| **Backend atomicity·페이징·silent except** | 보류 | `sales.py:1038~`, `seal_requests.py:862~` Drive↔Notion atomicity / `query_all` 페이징 / silent except 정리 |

## 핵심 helper / 모듈 위치

- `backend/app/services/inspection_legal_table.py` — 시특법 별표 22~26 (PR-Q5b)
- `backend/app/services/bma_table.py` — 건축물관리법 별표 1·3 (PR-Q4b)
- `backend/app/services/quote_calculator.py` — strategy dispatch (11종)
- `backend/app/services/quote_pdf.py` + `templates/quote_template.html` — PDF 빌드
- `backend/app/services/sales_code.py` — 영업코드 발급 (신·구 형식 sequence pool)
- `backend/app/routers/sales.py` — 영업/견적 CRUD + by-project lookup + 묶음 PDF
- `frontend/components/sales/InspectionLegalForm.tsx` — 시특법 입력 UI
- `frontend/components/sales/BmaInspectionForm.tsx` — BMA 입력 UI
- `frontend/components/sales/QuoteForm.tsx` — 견적 form (종류별 분기)
- `frontend/components/sales/SalesEditModal.tsx` — 영업 모달
- `frontend/app/sales/page.tsx` — `?sale={id}` query 진입 지원

## 노임 단가 갱신 (매년 1월)

`backend/app/services/quote_calculator.py` `ENGINEERING_RATES_BY_GRADE` dict.
BMA 운영 단가는 `backend/app/services/bma_table.py` 상단 (책임자 456,237 / 점검자 235,459).

## 검증 자료 위치

- `docs/quote_formulas/*.md` — 견적 종류별 산출식 dump (xlsx 검증 reference)
- `docs/시설물의+안전+및+유지관리+...PDF` — 시특법 본문
- `docs/건축물관리점검지침...doc` — 건축물관리법 본문
- `docs/건축물 정기점검 대가 산정표.xlsx` — 사장 운영 산정표
- 견적서 xls/xlsx 8개 — 종류별 실 사례
