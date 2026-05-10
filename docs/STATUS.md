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
| **Phase 0 검증 fix** | playwright 4 역할 시나리오 검증 중 발견 — `AuthGuard` catch fallback에 `setUser(getUser())` 추가 (backend down 시 가드 무력화 fix) + `/help` page를 USER_MANUAL.md에 동기화 (대시보드 manager 라벨 / Bot 알림 표 주간업무일지 행 / FAQ 자동 TASK 항목) | 46d2bd3 |
| **Phase 1 PR-A** 대시보드 상단 (DASH-001 + DASH-002) | 6개 KPI 카드(진행중/장기 정체 90일/마감 임박 7일/승인 대기 날인/이번 주 순현금/최다 부하 팀) + "지금 처리할 것" 액션 패널 5항목(정체·승인 지연·마감 임박·편중 팀·오래 멈춘 TASK). 카드 클릭 → 관련 list로 이동. frontend 단독(useSealRequests 추가) | 374adb8 |
| **Phase 1 PR-B** 프로젝트 프리셋 필터 (PROJ-001) | `/projects` 상단 8개 프리셋 칩(진행중·이번주 시작·완료 임박 30일·장기 정체 90일·우리 팀·날인 진행중·수금 이슈 30%·최근 수정 7일) + 각 칩에 결과 수 badge + URL `?preset=` 동기화. 기존 검색·단계·팀 필터와 AND 조합 | b0e845f |
| **Phase 1 PR-C** 내 업무 개인 브리핑 (MY-001) | `/me` 헤더 다음에 5 카드(오늘 마감/이번 주 마감/지연/승인·피드백 대기/진행 프로젝트). 본인 검토자(lead/admin) 매칭으로 날인 대기 카운트. **MY-002 시간 기준 재구성은 보류** — 기존 TodayTasks가 분류(category) 기준 그룹이라 시간 축으로 재구성 시 회귀 위험. Phase 2/3에서 진행 | 148f1d3 |
| **Phase 1 PR-D** 주간업무일지 가이드 (WEEK-001 + WEEK-002 + WEEK-003) | `/weekly-report` 상단에 진행 상태 바(데이터 수집/검토 필요/수동 입력 필요/발행 가능) + sticky 섹션 점프 nav 5그룹(기본 정보/수동 보완/자동 집계/예외·누락/미리보기·발행) + 각 섹션 헤더에 자동 집계/수동 입력 배지. Section 컴포넌트에 id + badge prop 추가, 12개 호출에 매핑 | 658a5b0 |
| **Phase 2 PR-E** 대시보드 차트 탭화 (DASH-003) | 9개 차트 컴포넌트를 4개 탭(운영 리스크/인력 부하/매출·수금/단계 현황)으로 그룹화. KPI/액션 패널은 탭 위 유지. ChartsTabs.tsx 신규 (page.tsx 9 section → 1 호출) | 8f909f3 |
| **Phase 2 PR-F** 프로젝트 강화 (PROJ-002 + PROJ-003) | 카드에 상태 태그 6종(장기 정체/마감 임박/날인 진행중/수금 지연/담당 미정/최근 변경) 추가 + 카드/테이블 보기 토글 + ProjectTable.tsx 신규. tagsById Map은 useMemo로 캐시. **PROJ-004 본격 quick action 보류** — 카드/행 click이 이미 상세 navigation이라 추가 가치 작음, Phase 3에서 anchor (#tasks/#seals) + filter URL 형식과 묶어 진행 | faa1256 |
| **Phase 2 PR-G** 내 업무 프로젝트 스냅샷 (MY-004) | `/me` 브리핑 카드 다음에 담당 프로젝트별 진행 요약 카드(진행 중/임박/지연 + 최근 활동 일자) — 손볼 일이 많은 순(overdue × 10 + dueSoon)으로 정렬. **MY-003 본격 TASK quick action 보류** — TaskEditModal이 이미 모든 액션 제공 + TodayTasks 분류 기준 그룹과 결합 시 회귀 위험. Phase 3로 이전 | 622534a |
| **Phase 2 PR-H** 주간업무일지 발행 체크리스트 (WEEK-004) | confirm dialog → `PublishChecklist` 모달. 자동 평가 1(빈 자동 섹션 수) + 수동 체크 4(공지·교육·건의/완료/보류·대기/PDF 미리보기). 모두 통과해야 [발행] 활성. **WEEK-005 source link 확대 보류** — 일부 섹션은 이미 admin link 적용, 전체 확대는 권한·table column 변경이라 회귀 영향 큼. Phase 3로 이전 | 7a3209c |
| **Phase 2 PR-I** 프로젝트 list 필터/스크롤 sessionStorage 보존 (COMMON-002) | `/projects`에서 filter/sortKey/view/activePreset/visibleCount + scrollY를 sessionStorage(`projects-page-state-v1`)에 보존. 상세 ↔ list 왕복 또는 새로고침 시 자동 복원. URL `?preset` 우선 (외부 진입 deep-link 대응). **COMMON-001 배지 디자인 시스템 통합 보류** — 현재 6+ 곳에 분산된 배지가 모두 정상 동작 중이라 일괄 추출은 시각 회귀 위험. Phase 3·4 리팩터링 사이클에 묶어 진행 | c584e57 |
| **PDF 폰트 spec 정리** | 17+개 분기 폰트 사이즈를 `docs/pdf_font.md`에 카테고리별 정리(A 헤더/B 본문/C 표/D cell-shrink+매크로/E 섹션 예외/F 기타) + 6 영역 사이즈 변경(.title-line 16→15pt, .period 11→10pt, .summary-line 8→7pt, .empty 7→5pt, .stage-table 5→5.5pt) + cell-shrink em→절대 pt + .tw-table base 6.5pt override (해석 B). | be4aaa5 |
| **Phase 3 PR-J** 대시보드 — 최근 변경/경고 패널 분리 (DASH-004) | ChartsTabs.운영 리스크 탭에 `RecentUpdatesPanel` (last_edited_time 7일 이내 Top 10) + `WarningItemsPanel` (정체·기한 초과·담당 미정·수금 지연 4종 chip 표시, 경고 수 많은 순) 추가. 액션 패널과 차별 — "주의 깊게 모니터링" 영역 | a5f160f |
| **Phase 3 PR-K** /me 팀장 모드 분리 (MY-005) | `/me` 헤더에 admin/team_lead용 직원 select dropdown 추가. "내 업무" + 팀원 list (team_lead는 본인 팀, admin은 전체) → 선택 시 `?as=이름`으로 navigate. listEmployees + getEmployeeTeamsMap SWR로 fetch (canSwitchView일 때만). 기존 ?as= 메커니즘 + UI만 추가 | 13fe98e |
| **Phase 3 PR-L** 공통 CTA 문구 표준 (COMMON-003) | `lib/cta.ts` 신규 — 8 표준 CTA 상수(detail/openProject/viewTasks/viewSeals/viewIncomes/viewMyTasks/viewLoad/viewSource). PriorityActionsPanel 4개 라벨을 표준으로 교체. 신규 추가 list/액션 패널 작성 시 이 상수 import 권장 | 0be3bfc |
| **Phase 3 PR-M** 프로젝트 상세 URL 재구조화 (PROJ-005) | `/project?id={id}` → **`/projects/{id}`** dynamic route. 기존 path는 client redirect 페이지로 유지(외부 hardcoded URL — Bot 알림·북마크 호환). 17 사용처(15 파일)의 internal link sed 일괄 substring 교체 + ProjectClient의 sale referrer query도 갱신. build 25 routes 정상 (○ static + ƒ /projects/[id] dynamic) | da9007a |
| **회수 PR-N** 프로젝트 카드 quick action (PROJ-004 본격) | ProjectCard footer에 4 chip(TASK/날인/매출/노션). 카드 본문 click(상세)와 별개로 특정 영역으로 deep-link. ProjectClient의 SealHistoryList/TaskKanban/ProjectCashflowChart에 `id="seals/tasks/cashflow"` anchor + scroll-mt 추가. nested anchor 회피 위해 chip은 button + stopPropagation + router.push (external은 window.open) | 신규 |

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
