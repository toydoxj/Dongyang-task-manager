# 작업 Status

> 마지막 업데이트: 2026-05-09 (commit 9e36b3b 기준)

## 완료된 PR

| 영역 | 내용 | 핵심 commit |
|---|---|---|
| **PR-Q** 견적서 분류 | 8종 분류 + 산출 strategy 11개 dispatch + 통합 PDF (PR-Q1~Q9 + PR-G1) | (이전) |
| **PR-Q5b** 시특법 자동 산정 | 별표 22~26 보간·보정·추가과업 + PDF 2페이지 산정 상세 (`inspection_legal_table.py`) | a0c91c1 |
| 시특법 후속 fixup | 산식 표기 / default 단가 / sync 토글 / 완공년도 자동 / legacy 제거 / VAT 포함·별도 / 외부 견적 VAT | b7d39e5 ~ cf5d257 |
| **PR-Q4b** BMA 자동 산정 | 건축물관리점검지침 별표 1·3 + 제37·38조 + 산정표 ±1원 일치 (`bma_table.py`) | 78bdb0f / d224e62 |
| **영업코드 형식** | `{YY}-영업-{NNN}` → `영{YY}-{NNN}` (옛 형식도 sequence pool 포함) | cf5d257 |
| **PR-LK** 영업↔프로젝트 | reverse lookup endpoint + 동일 프로젝트 날인요청 N개 허용 | 9e36b3b |
| **CLAUDE.md 개선** | root + frontend/AGENTS.md + backend/CLAUDE.md (신규) | (커밋 외) |

## 미완료 / 보류

| PR | 상태 | 비고 |
|---|---|---|
| **PR-W** 주간업무일지 | 계획만, 코드 X | 13.5일 추정. PDF + Dashboard + 공지 게시판 + 매주 월 05:00 KST cron. 재개 시 `docs/PLAN_WEEKLY_REPORT.md` + `PLAN_REPORT_FORMAT.md` reference |

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
