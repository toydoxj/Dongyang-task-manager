# 작업 Status

> 마지막 업데이트: 2026-05-13 (Phase 4-A 100% 완료 — lib/api.ts 1450→49줄 / 컴포넌트 분리 13 cycle)

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
| **회수 PR-N** 프로젝트 카드 quick action (PROJ-004 본격) | ProjectCard footer에 4 chip(TASK/날인/매출/노션). 카드 본문 click(상세)와 별개로 특정 영역으로 deep-link. ProjectClient의 SealHistoryList/TaskKanban/ProjectCashflowChart에 `id="seals/tasks/cashflow"` anchor + scroll-mt 추가. nested anchor 회피 위해 chip은 button + stopPropagation + router.push (external은 window.open) | d6bc320 |
| **회수 PR-O** 주간일지 섹션 → 관리 페이지 link (WEEK-005 본격) | Section 컴포넌트에 `sourceHref` prop 추가, 12 섹션 모두 admin용 「관리 ↗」 link. 인원현황→/admin/employees / 공지·교육→/admin/notices / 건의→/suggestions / 완료·신규·대기·보류→/projects / 영업→/sales / 날인대장→/seal-requests / 개인일정→/schedule / 팀별업무→/admin/employee-work. admin만 노출 (비admin은 link 없음) | 04b4ea7 |
| **회수 PR-P** StageBadge 추출 (COMMON-001 부분) | 7개 stage 색상 매핑(진행중/대기/보류/완료/타절/종결/이관)이 ProjectCard·ProjectTable·ProjectHeader 3개 파일에 동일 중복 → `components/ui/StageBadge.tsx`로 추출. className override prop으로 size·padding 변형 지원. ProjectTaskRow/SaleTaskRow의 작은 STAGE_BADGE("진행 중"·"대기" 띄어쓰기 다름)는 별도 enum이므로 유지 | 91c08c7 |
| **회수 PR-Q** /me TasksByTimeView 본격 (MY-002) | 「해야할 일」 헤더 옆에 [분류]/[시간] view toggle 추가. 시간 view = 5개 색상 그룹(지연·오늘·이번 주·이후·미정·최근 완료) + 각 그룹 task row(title·project·end_date·D-day chip·삭제). 기존 분류 view는 그대로 유지(default). 사용자가 시점 우선시 vs 도메인 우선시 자유 전환 | 9c8f8d2 |
| **회수 PR-R** TasksByTimeView quick action (MY-003) | TaskRow에 quick action 3개 추가: ✓ 완료 처리(updateTask로 status='완료' 즉시 PATCH) / 📁 프로젝트 열기(/projects/{id}) / 🔖 관련 날인(/seal-requests?project_id={id}). 페이지에 `handleCompleteTask` callback. 기존 분류 view(TodayTasks)는 회귀 위험으로 그대로 유지 — quick action은 시간 view 전용 | 943bc4c |
| **Phase 4-A PR-S1** lib/api.ts 도메인 분리 — 파일럿(clients) | `lib/api/_internal.ts` (jsonOrThrow + qs + authFetch re-export) + `lib/api/clients.ts` (listClients/createClient/updateClient/deleteClient). lib/api.ts에서 해당 함수 제거 + `export * from "./api/clients";` re-export. import "@/lib/api" 경로 모두 호환. 후속 PR-S2~S5에서 나머지 12 도메인 분리 예정 | cf6ee53 |
| **Phase 4-A PR-S2** lib/api.ts 분리 — tasks + suggestions + notices | 작은 도메인 3개 분리. tasks(40 줄), suggestions(60 줄), notices(100 줄). 각 도메인별 파일 + lib/api.ts re-export. unused type import(Task*) 정리 | fcd6872 |
| **PR-T** /me 4탭 구조 (사용자 요청) | 헤더+요약 카드+스냅샷 다음에 4탭 nav([해야할 일]/[담당 프로젝트]/[내 영업]/[기타 업무]). 각 탭 click 시 해당 섹션만 conditional render. 기존 hr 구분선 제거. URL `?tab=` 동기화. 「해야할 일」 안의 [분류/시간] toggle은 todo 탭 내부에서 그대로 유지. 후속 commit으로 5탭 재구조(할 일/일정/담당 프로젝트/내 영업/기타 업무) + 「일정」 탭에 파견 카드 추가 + 활동 옵션에 "파견" 동기화 | 1fce89a / 78e8d78 / eafdfcd |
| **PR-U** 주간업무일지 섹션 재배치 + 개인일정 파견 포함 (사용자 요청) | 새 순서: 1.공지 / 2.개인일정 / 3.신규 / 4.완료 / 5.인원 / 6.교육+7.건의(grid-2) / 8.날인 / 9.영업 / 10.팀별 / 11.대기 / 12.보류. frontend ReportPreview + backend weekly_report.html 동시 적용. backend `_SCHEDULE_CATEGORIES`와 activity 매칭 set에 "파견" 추가 — 파견 task가 개인일정 표에 표시되도록 | 신규 |
| **PR-V** SaleTaskRow에 영업별 task 추가 버튼 | /me 「내 영업」 탭의 각 영업 row에 + TASK 버튼 추가. TaskCreateModal에 `saleId` prop 신설 — saleId 전달 시 카테고리=영업(서비스) + 영업 link prefill. ProjectTaskRow와 동등 패턴 | 신규 |
| **PR-W** 주간업무일지 섹션 순서 v2 (사용자 요청) | 1.인원 / 2.공지·교육·건의(grid-3) / 3.개인일정 / 4.신규 / 5.완료 / 6.날인 / 7.영업 / 8.팀별 / 9.대기 / 10.보류. frontend + backend html 동시. | 98e52fc |
| **PR-X ~ AC 권한 정리** | 계약 분담 admin+manager → admin+team_lead+manager(PR-Y) + cashflow incomes admin+manager(PR-AB) + clients PATCH 전 직원(PR-AC) + 주간업무일지 admin 「최근 발행 PDF」 버튼(PR-Z) + 일반직원도 날인대장 노출(PR-AA). 자세한 매트릭스 [PERMISSIONS.md](PERMISSIONS.md) | a490430 / 948824b / 699be57 / e17ae61 / 913eed0 / 862b09c |
| **PR-AD** WeeklyReport in-memory cache + 새로고침 버튼 | backend module-level OrderedDict LRU cache (key=(ws,we,lws), TTL 300s, max 16). publish는 force_refresh=True. last-published.pdf는 cache hit 활용. frontend [새로고침] 버튼 추가 — refreshTick 증가 → SWR key 변경 + force_refresh=true | f293aa5 |
| **PR-AE ~ AN Phase 4-A 컴포넌트 분리 1차** | SalesEditModal 1670→1480(-190), weekly-report/page 1213→384(-829, **-68%**), me/page 1117→618(-499, -45%), QuoteForm 982→926(-56). 신규 컴포넌트 14개 파일 추출. lint·tsc 통과, 동작 영향 0 | 82853c4 ~ 1de0ae2 |
| **2026-05-12 연결 풀 사고 + 방어** | SQLAlchemy 풀 leak으로 Supavisor 50 도달 → 전사 접속 불가. 즉시 복구 (Supabase pg_terminate_backend + Render restart). 임시 보강: pool_size 10→5 / overflow 20→10 / recycle 300→120s(PR-AO). 근본 방어: pool_reset_on_return=rollback + get_db rollback + /api/health/db 라우트 + Render Health Check Path 교체(PR-AQ). 매뉴얼은 [INCIDENT.md](INCIDENT.md) | c4de851 / b57d525 / 4f95017 |
| **PR-AR Sync 관리** | render.yaml cron 5개 schedule 업무시간(KST 06~20) 회피 → UTC 11-21시(KST 20~06)만 실행. backend `/api/admin/sync/{status,run}` 신규 라우터 + frontend `/admin/sync` 페이지 (admin only, 10초 자동 refresh, kind별 강제 트리거) | 6bc3ede |
| **PR-AS / AT 권한 audit 마무리** | 「건의사항」 사이드바 manager 노출 + employees.GET "" 직원 명부 admin+팀장+manager(`require_editor`). master_projects는 현 정책(전 직원) 유지 결정 — audit 미결정 항목 모두 해소 | f70885a / 119dbf8 |
| **PR-AU ~ BC Phase 4-A 컴포넌트 분리 2차** | project/_shared.tsx 신설로 Field/inputCls 5+ 파일 통합. MasterProjectModal 608→514(-94), admin/employees/page 604→339(-265, -44%), seal-requests/page 543→154(**-389, -72%**), StageBoard 528→289(-239, -45%), TaskCreateModal 490→469(-21), IncomeFormModal 436→415(-21). 누적 9 파일 -2701줄 (-26%) / 신규 분리 파일 18개 | a73363f ~ c89c905 |
| **PR-AV Modal backdrop 차단** | components/ui/Modal — outer backdrop click → onClose 제거. 모달 입력 중 외곽 클릭 실수로 작업 손실 방지. ESC + X 버튼만 닫기 | 6cffb1d |
| **PR-AY /sales 가드 확장** | admin+manager → admin+team_lead+manager. 프로젝트 상세에서 「📋 영업 상세」 클릭 시 team_lead가 toast → /dashboard로 튕기던 dead-end 해소. backend는 이미 전 직원 허용 | c709d19 |
| **PR-BD/BE/BG lib/api.ts 100% 분리** | 1450 → 49줄 (-1401, -97%). 9 도메인 추가 추출 (cashflow/contractItems/master/users/employees/drive/projects/seals/sales/weekly). _internal에 downloadPdfBlob helper. 신규 분리 파일 12개 | 5367573 / d14befb / c0d6aff |
| **PR-BF 「새 영업」 form state remount fix** | SalesEditModal이 open=false에 return null만 호출 → React state 잔존. 부모에서 conditional mount + creatingKey로 force remount. 두 번째 「새 영업」 시 직전 입력 잔존 버그 해소 | 2b57196 |
| **PR-BH Phase 4-G 1단계 — JWT cookie 점진 마이그레이션** | backend `get_current_user`가 Authorization header 우선 + `dy_jwt` cookie fallback. `works_callback`이 fragment redirect와 함께 httpOnly+SameSite cookie 발급. `/api/auth/logout` 신설(idempotent + cli claim 기반 client별 UserSession 삭제). CORS `allow_credentials=True`. frontend `authFetch`에 `credentials: include`, Sidebar logout이 backend logout 선행. 운영 env `COOKIE_DOMAIN=.dyce.kr` 만 입력 필요(나머지는 default true/strict). 운영 검증 — Domain `.dyce.kr` / Secure / SameSite Strict / HttpOnly | 5db883a / 6b929a7 / db75dcf |
| **PR-BI 시도 → revert** | Phase 4-G 2단계(localStorage token 제거 + Authorization header 첨부 제거) 후 운영에서 일부 사용자(eul22)가 로그인 화면 반복 → 1단계로 즉시 롤백. 원인 가설: silent SSO iframe 안에서 cookie 발급/저장이 의도대로 안 되어 cookie 단독 인증으로 전환 시 fetch 401 loop. 다음 시도 시 silent SSO 흐름 + saveAuth signature 호환성 + 401 자동 silent 재시도 설계 보강 필요 | 0a427b0 / e340068 |
| **PR-BJ-1 Phase 4-F 집계 API 1차** | `/api/dashboard/summary` 신설 — KPI 6개(진행중/장기 정체/마감 임박/승인 대기 날인/이번주 수금·지출/최다 부하 팀) backend 집계. KST 경계 표준화(`_KST` + `_week_bounds`). 응답에 today/week_start/week_end 동봉(검증용). 승인 대기 날인은 일단 0(PR-BJ-3에서 추가). frontend는 별도 cycle에서 호출 전환 | 8239a00 |
| **PR-BJ-2 frontend KPICards 전환** | `lib/api/dashboard.ts` 신설 + `useDashboardSummary()` SWR hook + dashboard page에서 호출. KPICards props 시그니처 변경(`projects/tasks/incomes/expenses` 제거, `summary` 추가). 승인 대기 날인은 PR-BJ-1 backend가 0이라 frontend가 임시로 sealRequests prop으로 카운트 | 03bb96e |
| **PR-BJ-3a backend seal pending count** | dashboard router에 `_count_pending_seals` async helper — notion `상태` filter(1차/2차 검토중)로 페이지 수 카운트. summary 응답에 `pending_seal_count` 정상 채움. KPICards에서 임시 sealRequests prop 제거 | e6acbb4 / 245bc6e |
| **PR-BJ-3b/4 /actions endpoint + PriorityActionsPanel 전환** | `/api/dashboard/actions` 신설 — 5 액션 항목(장기 정체/승인 지연/마감 임박/편중 팀/멈춘 TASK) backend 집계. ActionItem `{count, preview}` schema. notion seal `제출예정일` 경과 + pending status filter for 승인 지연. mirror_tasks 기반 마감/멈춘 query. frontend PriorityActionsPanel을 list-based 제거 + actions prop으로 단순화. dashboard page에서 useSealRequests 제거 (seal 정보는 backend가 처리) | bd9468f |
| **PR-BJ-5 dashboard TTL cache** | summary / actions 두 endpoint에 30초 TTL in-memory cache (WeeklyReport pattern — `OrderedDict[(name, today), (ts, value)]` + LRU max 16). `force_refresh=true` query로 우회 (사용자 새로고침). notion query_all 부하 감소 + 응답속도 개선 | 572aecc |
| **PR-BK Phase 4-F 마감 — /insights endpoint** | RecentUpdatesPanel + WarningItemsPanel을 backend 집계로 통합. `/api/dashboard/insights` 신설 — recent_updates(7일 이내 last_edited Top 10) + warnings(미종결 + flag(stalled/noAssignee/incomeIssue/overdue) Top 12). frontend 두 panel을 props 시그니처(items/rows)로 단순화. ChartsTabs에서 useDashboardInsights 호출 + 30초 TTL cache 적용. Phase 4-F는 role 스코프만 남음 | (pending push) |

## 미완료 / 보류

### ✅ Phase 1·2·3 — 모두 완료
DASH-001~004 / PROJ-001~005 / MY-001~005 / WEEK-001~005 / COMMON-001~003 항목 모두 PR-A ~ PR-R로 완료.

### Phase 4 잔여 (장기 인프라 — 외부 1번 리뷰 12.3, 12.4)

| 항목 | 상태 | 비고 |
|---|---|---|
| **4-A** lib/api.ts 도메인 분리 | ✅ 완료 (PR-S/S2/AR/BD/BE/BG, 100%) | 15/15 도메인 lib/api/*.ts. lib/api.ts는 49줄 re-export hub만 남음 |
| **4-B** 대형 컴포넌트 외과적 분리 | ✅ 완료 (PR-AE~BC, 13 cycle) | -2701줄/-26%, 신규 분리 18개. 본격 design refactor는 별도 cycle |
| **4-C** 리스트 서버 필터링·페이지네이션 | 미진행 | backend list_projects/tasks/sales — offset/limit + push-down filter |
| **4-D** 메뉴 그룹 URL 재구성 | 미진행 | `/workspace`, `/operations`, `/admin` 통합 |
| **4-E** 권한 로직 layout 통합 | 미진행 | 페이지마다 분산된 가드를 layout 레벨로 |
| **4-F** 대시보드/주간보고 집계 API 별도 | 미진행 | client-side aggregation을 backend로 push |
| **4-G** JWT localStorage → httpOnly cookie | 1단계 완료(PR-BH) / 2단계(PR-BI) 시도 후 운영 회귀로 revert — silent SSO + saveAuth signature 보강 후 재시도 예정 | XSS 방어 강화 |
| **4-F** 대시보드/주간보고 집계 API | KPI/액션/RecentUpdates/Warnings 모두 backend 집계 + TTL cache 완료(PR-BJ-1~5 + PR-BK) / 잔여(role 스코프 차등) | dashboard N+1 → 1 fetch |
| **4-H** 문서 자동 동기화 체계 | 미진행 | USER_MANUAL/STATUS/PERMISSIONS auto-sync |
| **4-I** Frontend 테스트 framework | 미진행 | Vitest + Playwright |
| **4-J** Backend 라우터/서비스 분할 | 미진행 | seal_requests / sales / projects / quote_calculator / weekly_report 큰 파일들 |

### Backend atomicity·페이징·silent except (HIGH 위험 — 별도 cycle 권장)
| 항목 | 상태 | 비고 |
|---|---|---|
| Drive↔Notion 업기 atomicity | 보류 | `sales.py:1038~`, `seal_requests.py:862~` |
| `_sync_sale_estimated_amount` race | 보류 | |
| `query_all` 페이징 | 보류 | 노션 100건 limit 안전성 |
| silent except → partial-failure | 보류 | 응답 형식 통일 |

### 작은 잔여 (낮은 우선순위)
| 항목 | 비고 |
|---|---|
| **#113** /sales — onClose 시 ?sale= query 정리 | SaleLink referrer 보존(PR-114)으로 우회됨 |
| **#116** /weekly-report 페이지 PDF와 양식 통일 | 데이터·구조 동일. 시각 디테일(컬럼폭·색상)만 잔여 |
| **SQLAlchemy leak 근본 source 추적** | PR-AO/AQ 임시 방어 + auto restart 동작 중 |

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

## 환경 / 배포 노트

| 영역 | 호스팅 | 자동 트리거 |
|---|---|---|
| **frontend** | Vercel project `dongyang-task-manager` (team `fsjh35-8127s-projects`) | `main` push마다 자동 배포 |
| **backend** | Render Docker service `dy-task-backend` (region: `ap-northeast-2`, Singapore equivalent) | backend 디렉터리 변경 시 Docker 재빌드 5–8분 |
| **database** | Supabase Pro project `hxhdqjbzfuddinoejoyo` (DY-Task, region: `ap-northeast-2`) | — |

### DATABASE_URL 주의 — IPv4 호환 필수

Supabase는 두 종류 pooler를 제공:

| pooler | host | IP | Render 호환 |
|---|---|---|---|
| **SHARED** (권장) | `aws-0-ap-northeast-2.pooler.supabase.com` | IPv4 + IPv6 | ✅ |
| **DEDICATED** (기본 노출) | `aws-1-ap-northeast-2.pooler.supabase.com` | **IPv6 only** | ❌ Render outbound는 IPv4 only |

**Render `DATABASE_URL`은 반드시 SHARED pooler URL을 사용** (Session 모드 port `5432` 권장).
Dedicated pooler를 쓰면 startup 시 `(EDBHANDLEREXITED) connection to database closed` 에러로 instance restart 무한 루프 (2026-05-11 발생 사례).
Pro plan에서 IPv4 add-on(약 $4/월) 활성화 시 dedicated pooler도 사용 가능.

URL 형식:
```
postgresql://postgres.hxhdqjbzfuddinoejoyo:<PASSWORD>@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres
```

### Transaction (port 6543) vs Session (port 5432)

- Session pooler (5432) = SQLAlchemy + psycopg 표준 호환. **이 프로젝트는 Session 사용**.
- Transaction pooler (6543) = prepared statement / LISTEN-NOTIFY 미지원. SQLAlchemy 일부 기능 깨짐.
  - 추가로 Render IPv4-only outbound와 비호환(IPv6 endpoint만 노출, 2026-05-12 사고).

### SQLAlchemy connection pool

`backend/app/db.py` (PR-AO, 2026-05-12 사고 후 축소):
- `pool_size=5`
- `max_overflow=10` (워커당 최대 15)
- `pool_recycle=120s` (idle leak 빠른 회수)
- Supavisor 50까지 여유 35

근본 leak source 추적은 별도 cycle 진행 중. 자세한 내역은 [INCIDENT.md](INCIDENT.md#2026-05-12--sqlalchemy-connection-leak--supavisor-pool-고갈--전사-접속-불가) 참조.

### Supabase 진단 도구

`mcp__plugin_supabase_supabase__get_logs(project_id="hxhdqjbzfuddinoejoyo", service="postgres")` —
정상 backend connection은 `application_name=Supavisor`로 노출. `supabase/dashboard`만 보이고 `Supavisor`가 없으면 backend connect 실패 신호.

### 사고 대응 매뉴얼

운영 사고 발생 시 [INCIDENT.md](INCIDENT.md#사고-대응-체크리스트-재발-시) 의 체크리스트 참조.
주요 매핑: `QueuePool limit` → SQLAlchemy 풀 고갈 / `EMAXCONNSESSION` → Supavisor 풀 고갈 / `Network is unreachable` (`2406:...`) → IPv6 endpoint 시도.
