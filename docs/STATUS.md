# 작업 Status

> 마지막 업데이트: 2026-05-16 (Phase 4-D 2단계 — employee-work 운영 이동 + PR-EJ redirects 보강)

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
| **PR-BK Phase 4-F 마감 — /insights endpoint** | RecentUpdatesPanel + WarningItemsPanel을 backend 집계로 통합. `/api/dashboard/insights` 신설 — recent_updates(7일 이내 last_edited Top 10) + warnings(미종결 + flag(stalled/noAssignee/incomeIssue/overdue) Top 12). frontend 두 panel을 props 시그니처(items/rows)로 단순화. ChartsTabs에서 useDashboardInsights 호출 + 30초 TTL cache 적용. Phase 4-F는 role 스코프만 남음 | 9481f6c |
| **PR-BL-1 Phase 4-I 1차 — Vitest 도입** | frontend 테스트 framework. vitest + jsdom + @vitejs/plugin-react 설치. vitest.config.ts(jsdom 환경 + @/* alias). lib/format / lib/cta 단위 테스트 (8개) — `npm run test` / `npm run test:watch`. PR-BI 같은 회귀 사전 검출 인프라 1차. Playwright는 별도 cycle, CI 통합도 별도 | eb18426 |
| **PR-BL-2 lib/* 테스트 확장** | lib/api/_internal qs (5 케이스: empty/skip/falsy/encoding/coercion) + lib/types ROLE_LABEL (4 role 한글 표기 회귀 방지) + lib/format formatDateTime (KST 변환) — 누적 18 테스트 | b6efd5c |
| **PR-BL-3 Phase 4-I 2차 — Playwright e2e 도입** | @playwright/test + chromium 설치(92MB binary). playwright.config.ts(webServer로 next dev 자동 실행 + chromium-only 1차) + e2e/login.spec.ts (`/login?error=test` 진입 시 h1 + 분기 텍스트 노출 검증). `npm run test:e2e` / `test:e2e:ui` script. .gitignore에 test-results/playwright-report 추가. PR-BI 같은 redirect loop 회귀 1차 검출 | ca1d3ec |
| **PR-BL-4 Phase 4-I 3차 — GitHub Actions CI** | `.github/workflows/ci.yml` 신설 — push to main + pull_request 트리거. concurrency cancel-in-progress(연속 push 비용 절약). 2 job: frontend(npm ci → lint → tsc → vitest → playwright install --with-deps chromium → e2e + 실패 시 report artifact 업로드) / backend(uv sync --frozen → pytest, WORKS_*=false env). PR마다 자동 회귀 검증 — PR-BI 같은 사고 사전 차단. **첫 run 1m30s success** | 14f433a |
| **PR-BM INCIDENT.md PR-BI 사고 정리** | 2026-05-13 사고 entry 추가 — 증상(eul22 로그인 loop)/원인 가설 3가지(silent SSO + 3rd-party cookie / saveAuth chunk stale / 401 즉시 redirect)/조치(revert)/교훈/다음 시도 전 체크리스트 6개(silent SSO cookie 검증, saveAuth backward-compat, 401 silent 재시도, /me hydration, e2e 4 role, telemetry). PR-BI 재시도용 설계 보강 메모 | 94ed032 |
| **PR-BL-5 4 role e2e (INCIDENT 체크리스트 #5)** | e2e/_helpers.ts(setupRoleAuth — addInitScript로 localStorage 인증 주입) + e2e/role-access.spec.ts(4 시나리오: admin/team_lead/manager → 루트 진입 시 대시보드 h1 노출 / member → /me redirect). AuthGuard catch fallback(Phase 0-B) 활용으로 backend mock 없이 self-contained. 누적 e2e 5 통과(5초). PR-BI 같은 redirect loop + role guard 회귀 자동 검출 | 725d459 |
| **PR-BN saveAuth backward-compat (INCIDENT 체크리스트 #2)** | `saveAuth(token, user)` + `saveAuth(user)` 두 호출 시그니처 모두 지원하도록 overload + runtime branch. PR-BI 사고 원인 가설 #2(Vercel chunk 부분 stale로 옛/새 chunk 혼재 시 user 자리에 token 저장 → loop) 회피. 누적 vitest 21(saveAuth 3 시나리오 + clearAuth) | 3156584 |
| **PR-BO authFetch 401 silent SSO 재시도 (INCIDENT 체크리스트 #3)** | authFetch에 retry flag → 401 발생 시 silent SSO 1회 재시도(만료 cookie/token 갱신) 후 성공이면 fetch 재시도, 실패면 clearAuth + redirect. dy_logged_out / dy_silent_failed flag 시 재시도 skip. PR-BI 사고 원인 가설 #3(401 즉시 redirect → loop) 회피 + 현 운영에서도 silent SSO 후 cookie 회복 시나리오 자동 처리. 누적 vitest 24 | ce6f264 |
| **PR-BP/BQ 시도 → revert** | PR-BP `/me hydration` + PR-BQ Authorization header 제거 deploy 후 callback page에서 "로그인 처리 중..." 무한 반복 사고. 원인: `hydrateUserFromMe`가 `authFetch`를 사용 → 401 → PR-BO silent SSO → callback page iframe 재load → 재귀. 즉시 revert(b51fd72 + 5ae788e) 후 안정 복귀. INCIDENT.md에 재설계 체크리스트 4항목 추가(raw fetch 사용 / callback에서 호출 X / PR-BO silent retry에 인증 endpoint 제외 / PR-BP 재설계 후 PR-BQ 재시도) | b51fd72 / 5ae788e |
| **PR-BR INCIDENT.md PR-BP/BQ 사고 entry 추가** | callback hydration 무한 재귀 사고 메모(증상/원인/조치/교훈/체크리스트 4항목). STATUS 4-G 행 갱신 — 3회 시도 회귀 명시 | 58014eb |
| **PR-BS Phase 4-E 권한 가드 hook 추출 1차** | `lib/useRoleGuard.ts` 신설 — `useAuth + allowed 평가` 패턴을 `useRoleGuard(allowedRoles)`로 통합. /sales + /admin/expenses 2 page 시범 적용(useAuth import 제거). 권한 매트릭스가 다양해 layout 통합은 회피, hook 패턴이 page별 권한 차이 유연하게 처리. 나머지 page 점진 마이그레이션은 별도 cycle | 3d3594d |
| **PR-BT Phase 4-E 2차 — 5 page 마이그레이션** | `useRoleGuard` 추가 적용: `/`(dashboard, admin/team_lead/manager) + `/projects` + `/admin/contracts` + `/admin/incomes` + `/admin/incomes/clients`(모두 admin/manager). 누적 7 page. seal-requests/employee-work/notices/sync/users 등 isAdmin/isAdminOrLead 변수 derive 패턴은 별도 cycle | c704a51 |
| **PR-BU Phase 4-E 3차 — admin only / employee-work 3 page** | `/admin/sync` + `/admin/users` (admin only — `useRoleGuard(["admin"])`) + `/admin/employee-work`(admin/team_lead, isAdmin/myTeam derive는 user 객체 그대로 사용). 누적 10 page. 잔여(weekly-report/seal-requests/notices — 모두 전 직원 진입 + isAdmin derive로 UI 분기, redirect 가드 없음 → useRoleGuard 적용 부적절, useAuth 유지) | 8e75998 |
| **PR-BV silent except audit + 2 case 시범 fix (외부 리뷰 12.x #1)** | `docs/audit/silent_except.md` 신설 — backend 41 case 분류(의도적 25 / 외부 API silent 12 / 정상 fallback 4). 위험한 외부 API silent 2개 시범 fix(`routers/projects.py:117` 변경 이력 page 생성 / `routers/master_projects.py:395` master blocks write-through). 본격 partial_errors schema + Drive/Notion atomicity는 별도 cycle | 7d33cb4 |
| **PR-BW silent except 마감 (외부 리뷰 12.x #1 1차 완료)** | 잔여 case 점검 — audit script 오탐(seal_requests:643/645는 이미 logger 있음) 정정 + 정상 의도 fallback(quote_code/weekly_report/cashflow) 분류. 진짜 silent 1건 추가 fix(`routers/projects.py:670` review folder list 실패 → `logger.warning`). 외부 API silent 모두 logger 또는 failed.append 처리. 다음 단계는 partial_errors schema(별도 cycle) | 9e13a38 |
| **PR-BX partial_errors schema (외부 리뷰 12.x #1 본격)** | seal_requests 응답에 `partial_errors: [{code, target, message, retryable}]` 정형 필드 추가. create_seal_request + attachments endpoint에서 `failed[]` → `partial_errors[]` 변환(드라이브 업로드 실패 정형화). frontend `PartialError` 타입 + `SealRequestItem.partial_errors?` 추가 | ff2b7ef |
| **PR-BY partial_errors 사용자 안내 (PR-BX 후속)** | `SealRequestCreateModal`에서 createSealRequest/redoSealRequest 응답 받은 후 `partial_errors`가 있으면 `window.alert("등록은 성공했으나 일부 작업이 실패했습니다:\n- ...")` 노출 후 `onCreated()`. toast 시스템 미도입이라 native alert. 추후 toast 도입 시 한 곳만 교체 | f45d8e9 |
| **PR-BZ _sync_sale_estimated_amount race 해소 (외부 리뷰 12.x #3)** | `db.get()` → `SELECT ... FOR UPDATE`로 row-level lock. 동일 page_id의 동시 호출은 직렬화되어 last-write-wins overwrite 차단. 노션 update는 락 release 후(commit 후) 외부 API latency가 락에 영향 X. SQLite(test)는 noop, Postgres(운영)에만 효과. 5 호출처 영향 없음 | 212f80e |
| **PR-CA Drive·Notion atomicity 1단계 (외부 리뷰 12.x #2)** | `notion._call`은 이미 4 attempts retry — codex 권장 #2(재시도) 자동 충족. 시나리오 C(retry 후에도 노션 update 실패 → Drive orphan + 사용자 500) 보호 위해 `seal_requests.py:906/1532` 마지막 update_page를 try/except로 wrap → `failed.append`로 partial_errors 노출. helper `_failed_to_partial`로 prefix 분기 (drive_upload / notion_update). sales.py는 이미 try/except + logger.exception 적용됨(점검 결과). 2차 보상 트랜잭션(page archive 등)은 사용자 워크플로 검토 후 별도 cycle | b15135c |
| **PR-CB query_all 안전장치 (외부 리뷰 12.x #4)** | `notion.query_all`에 fail-fast 가드 3종 추가 — `max_pages=200`(20000 row 한도) / `has_more=True && next_cursor=None` 검증 / `seen_cursors` cycle 검증. 이상 시 `logger.warning` + `RuntimeError` raise. 부분 결과 truncate는 silent 데이터 불일치 위험이라 cap 대신 fail-fast 선택(codex 자문). 호출처(8곳) 영향 없음 — 정상 응답에선 동작 동일. 진짜 큰 DB는 호출처에서 `iter_query_pages` 전환(별도 cycle) | df778e3 |
| **PR-CC Phase 4-J 1단계 — sales 라우터 패키지 변환 (codex 권장 sub-router 패턴)** | `routers/sales.py` (1563 lines) → `routers/sales/__init__.py` 패키지 변환 (`git mv` rename 추적). 상위 router는 그대로(`prefix="/sales"`). 가장 작은 read-only endpoint(`GET /quote/types`)를 `routers/sales/quote_meta.py` sub-router로 분리 + `include_router`. main.py import 변경 없음(`from app.routers import sales`가 패키지 자동 resolve). 회귀 위험 거의 0 — endpoint 경로 동일(`/api/sales/quote/types`), pytest 63 passed | 58f63a0 |
| **PR-CD Phase 4-J 2단계 — sales link sub-router 분리** | 영업↔프로젝트 link 3 endpoint(`POST /:id/convert` + `GET /by-project/:id` + `POST /:id/link-project`) + `LinkProjectRequest` model을 `routers/sales/link.py`로 이동(~210 lines). 고아가 된 import(`Project`/`ProjectCreateRequest`/`project_create_to_props`/`CONVERTIBLE_STAGES`) 정리. 경로 동일, pytest 63 passed | 394d509 |
| **PR-CE Phase 4-J 3단계 — sales pdf sub-router 분리** | PDF 4 endpoint(`GET /:id/quote.pdf` + `GET /:id/quote-bundle.pdf` + `POST /:id/quote/save-pdf-to-drive` + `POST /:id/quote-bundle/save-pdf-to-drive`) + 3 helper(`_resolve_target_form`, `_form_to_pdf_data`, `_collect_bundle_sections`)를 `routers/sales/pdf.py`로 이동(~503 lines). `_KST` 정의는 외부 견적 attach endpoint(line 772)도 사용해 `__init__.py` 상단으로 옮김 + pdf.py 자체에서도 정의. 고아 import(`Employee`/`url_quote`/`build_quote_*`/`quote_*_filename`) 정리. `__init__.py` 1381 → 930 lines(~33% 감소). 4 PDF 경로 동일, pytest 63 passed | 61f3da7 |
| **PR-CF Phase 4-J 4단계 — quote/preview를 quote_meta에 통합** | `POST /quote/preview`(견적 산출 read-only)를 `routers/sales/quote_meta.py`로 이동. `QuoteResult` 고아 import 정리. 단일 endpoint라 helper 의존 없음. `__init__.py` 930 → ~920 lines | 88ae27a |
| **PR-CG Phase 4-J 5단계 — seal_requests 패키지 변환 + meta sub-router** | `routers/seal_requests.py` (1826 lines) → `routers/seal_requests/__init__.py` 패키지 변환 (`git mv` rename 추적). 가장 작은 read-only endpoint 2개(`GET /next-doc-number` + `GET /pending-count`) + 2 model(`NextDocNumberResponse`, `PendingCount`)을 `routers/seal_requests/meta.py`로 분리. `_db_id` helper는 다른 endpoint에서도 사용 → meta.py에 중복 정의(2줄, 외과적). `weekly_report.py`의 `from app.routers.seal_requests import list_seal_requests` 영향 없음(list는 그대로 `__init__.py`). main.py import 변경 없음. 경로 동일, pytest 63 passed | 4e61ed3 |
| **PR-CH Phase 4-J 6단계 — seal_requests attachments sub-router** | 첨부 read-only 2 endpoint(`GET /:id/download/:idx` + `GET /:id/preview/:idx`) + `_get_attachment_or_404` helper를 `routers/seal_requests/attachments.py`로 이동(~157 lines). `_can_access` helper는 다른 곳에서도 사용 → attachments.py에서 lazy import (`from app.routers.seal_requests import _can_access` 함수 안). sub-router include 위치를 파일 끝으로 이동 — `__init__.py` fully loaded 후 mount해 lazy import가 fail-safe. 경로 동일, pytest 63 passed | 912aaa1 |
| **PR-CI Phase 4-J 7단계 — seal_requests approval sub-router** | status 전이 3 endpoint(`PATCH /:id/approve-lead` + `PATCH /:id/approve-admin` + `PATCH /:id/reject`) + `_set_status_with_handler` helper + `RejectBody` model을 `routers/seal_requests/approval.py`로 이동(~240 lines). `_set_status_with_handler`는 approve-lead/admin에서만 사용 → 함께 이동. 다른 helper(`_from_notion_page`/`_sync_linked_task` 등)는 함수 안 lazy import. `SealRequestItem`은 decorator(`response_model`)에 필요해 module-level lazy import. `__init__.py` 1667 → 1495 lines. 경로 동일, pytest 63 passed | 028ab12 |
| **PR-CJ Phase 4-J 8단계 — seal_requests update/redo sub-router** | `PATCH /:id` (update_seal_request) + `POST /:id/redo` (redo_seal_request) 2 endpoint + `SealUpdateBody` + `SealRedoBody` 2 model을 `routers/seal_requests/update.py`로 이동(~410 lines). 두 endpoint 모두 본문이 큼 — update(~125 lines)는 반려→재요청 복구 흐름, redo(~167 lines)는 row 덮어쓰기 + 새 사이클 task 생성. helper(`_can_access`/`_get_title_prop_name`/`_project_summary_from_db`/`_create_seal_task_bg` 등 10+개)는 함수 안 lazy import. `__init__.py` 1495 → 1173 lines (~21% 감소). 경로 동일, pytest 63 passed | cfbc0c9 |
| **PR-CK dashboard slow 1단계 — pending-count 분리 + TTL cache (운영 6.4초 병목 fix)** | 운영 로그에서 `/api/dashboard/summary` 6420ms 식별. 원인: `_count_pending_seals(notion)` → `notion.query_all` 페이지당 0.4s rate limit. codex 권장 Step 1 적용 — (1) backend `dashboard.py`에서 `_count_pending_seals` 호출 제거 + 함수 자체 deprecated(요청 경로에서 노션 호출 완전 제거, mirror DB만 사용 → ~수백 ms). (2) `seal_requests/meta.py`의 `pending-count` endpoint에 5분 TTL in-memory cache 추가 — Sidebar 60초 polling이 cache hit. (3) `KPICards.tsx`에서 `summary.pending_seal_count` → `useSWR(['seal-pending'], getSealPendingCount)`로 분리, Sidebar SWR cache 공유. 추가 backend 호출 0. Step 2(mirror_seal_requests 신설)는 별도 cycle | a5930e6 |
| **PR-CL dashboard slow 2단계 (근본 fix) — mirror_seal_requests 신설** | codex 권장 Step 2. `MirrorSealRequest` model 신설 (page_id/title/seal_type/status/requester/project_ids 최소 schema). alembic `e0c1d2e05015_mirror_seal_requests` migration. `sync.py`에 `seal_requests` SyncKind 추가 + `_upsert_seal_request` (SL.normalize_status 호환). `seal_requests/meta.py`의 `pending-count`를 노션 query_all에서 mirror DB count(`SELECT COUNT(*)`)로 전환 — TTL cache 제거(이제 마이크로초 응답). 5분 sync lag 허용 (write 흐름 즉시 sync는 별도 PR). pytest 63 passed | 88aea10 |
| **PR-CM 사이드바/page 권한 — 팀장도 프로젝트 진입** | 「운영 관리 > 프로젝트」 사이드바 + `/projects` page guard에 team_lead 추가. backend는 이미 전 직원 허용. team_lead 로그인 시 사이드바에서 누락되던 dead-end 해소 | ec35c33 |
| **PR-CN/CO/CP 건의사항 502 fix (운영 노션 schema 일치화)** | 「+새건의 → 저장」 시 502 NotionApiError. 운영 노션 schema가 backend 기대와 불일치(`내용`이 title / `구분`이 multi_select 신설 / `방안`은 text / `진행상황`은 status / `작성자`는 multi_select). PR-CN(title 컬럼명 dynamic lookup) → PR-CO(매핑 정정 + 구분 필드 추가) → PR-CP(작성자 multi_select). 사용자 schema 정보 직접 제공 후 단계적 fix. 「이제 된다」 확인 | 05183ec / 1a9cfd6 / e1244c5 |
| **PR-CQ seal_requests write 즉시 mirror sync (PR-CL 후속)** | 5분 sync lag로 새 seal request가 pending count에 즉시 반영 안 됨. create/update/approve/reject 4 endpoint에 `_upsert_seal_request` 즉시 호출 (best-effort, 실패 시 5분 cron이 회수). pytest 63 passed | df11314 |
| **PR-CR SQL/pool checkout 분리 계측 (Step 3 진단 1단계)** | `db.py`에 `before/after_cursor_execute` + `checkout/checkin` event listener. SQL ≥0.5s → "slow SQL" warn. checkout~checkin ≥0.3s → "long DB connection held" warn. 운영 mirror endpoint 2~3초 병목이 (a) SQL 자체 (b) connection wait 중 어느 것인지 분리 진단용 | 1fbad0a |
| **PR-CS 계약기간 입력 → 계약 자동 체크** | 프로젝트 PATCH에서 `contract_start`/`contract_end` 둘 다 채워지면 backend에서 `is_contracted=True` 자동 set. 운영 흐름(계약기간 입력했는데 계약 체크 누락) 사전 차단 | eafb5f9 |
| **PR-CT~CW Phase 4-J 9~12단계 — seal_requests 본격 분할** | attachments add를 attachments.py로 통합(PR-CT) / delete sub-router(PR-CU) / list endpoint sub-module(PR-CV, FastAPI prefix=="" 충돌 회피로 함수만 export + add_api_route 패턴) / create_seal_request 분리(PR-CW). `__init__.py` 1826 → 699 lines (-62%). 누적 12단계 (sales 4 + seal_requests 8) 완료. 경로 동일, pytest 63 passed | bf75dab / be0dd9a / 0f52bea / 10c2b46 |
| **PR-CX silent SSO 실패 flag 5분 TTL (INCIDENT #1 #3)** | `_isSilentFailedRecently` — `dy_silent_failed`를 timestamp로 저장해 5분 후 자동 재시도 허용. 기존 영구 차단으로 cookie 만료 후 사용자 회복 불가(loop)였던 상태 해소. legacy "1" 값은 fresh fail로 marker 갱신 | 97ccd73 |
| **PR-CY SSO callback /me hydration + cookie 검증 (INCIDENT #1 #4)** | `verifyAndHydrateFromMe()` — callback page redirect 직전 raw `fetch("/api/auth/me")` (authFetch 미사용 → 401 silent SSO 무한 재귀 회피, INCIDENT #4). 200이면 `saveAuth(user)` 갱신 / 401·network는 fragment user fallback + console.warn. fragment user_b64 schema 변경 / Vercel chunk stale 자동 정정 | a1e8d08 |
| **PR-CZ Supabase RLS enable (advisor 보안 경고 조치)** | 모든 public 테이블에 RLS enable. policy 부여 없음 → anon/authenticated 차단. backend는 service_role connection이라 RLS bypass — 영향 없음. frontend는 Supabase JS client 미사용 확인. alembic `f1d2e3f05015` migration. 22 ERROR → 19 INFO(rls_enabled_no_policy, 의도된 상태) | f502cf6 / 3e388c9 |
| **PR-DA / PR-DB idle in transaction leak 근본 fix** | 4시간+ 살아있는 idle in transaction connection이 ALTER TABLE lock 차단(2026-05-15 RLS migration 사고). connect 시점에 PostgreSQL `idle_in_transaction_session_timeout = '300s'` 강제(`db.py` event listener) → backend cleanup 누락돼도 5분 안에 DB측 자동 rollback + close. /api/health/db 응답에 SHOW 결과 노출해 운영 검증("5min" 확인). 운영 사고 영향: PR-AO 재발 / RLS migration 차단 / 주기적 backend restart 필요성 모두 해소 | 2687eb4 / 0a6f663 |
| **PR-DC Phase 4-J 13단계 — projects 라우터 패키지 변환** | `routers/projects.py` (1040 lines) → `routers/projects/__init__.py` 패키지 변환 (`git mv`). 가장 작은 read-only endpoint `GET /options` (~32 lines, ProjectOptions model 포함)를 `routers/projects/options.py` sub-router로 분리. 19 endpoint 모두 정상 등록 확인, pytest 63 passed | cb4f2cc |
| **PR-DD Phase 4-J 14단계 — projects/drive sub-router** | WORKS Drive 임베디드 탐색기 영역 통째로 분리 — 7 endpoint(review-folder GET/POST + drive/children + issue-token + stream + upload + delete) + 5 helper(`_extract_resource_key`/`_today_ymd`/`_review_folder_state`/`_issue/_verify_drive_stream_token`) + 6 model을 `routers/projects/drive.py`로 이동(~473 lines). 자체 logger("projects.drive"). __init__.py 1013 → 576 lines (-43%). 고아 import 12개 정리(time/date/Any/parse_qs/httpx/jose/BackgroundTask/File/UploadFile 등). test 1건 import path 갱신, pytest 63 passed | 793f2c0 |
| **PR-DE Phase 4-J 15단계 — quote_calculator 패키지 + struct strategy 분리** | `services/quote_calculator.py` (1585 lines) → `services/quote_calculator/__init__.py` 패키지 변환. `strategies/struct.py` 신설(106 lines): `_calculate_struct_design` + `_calculate_struct_review`. 4 호출처(sales/quote_meta·sales/__init__·quote_code·quote_pdf) import 변경 없음. _DISPATCH 정의 직전에 strategies.struct를 import → partial loading 시점에 helper(baseline_manhours/_excel_round_half_up/_resolve_rate)와 model 모두 attribute 확보 → 순환 import 충돌 없음. import + 산출 smoke 검증 + pytest 63 passed | 82ab200 |
| **PR-DF Phase 4-J 16단계 — inspection 짝 strategy 분리** | `_calculate_inspection_bma`(건축물관리법점검, ~248줄) + `_calculate_inspection_legal`(시특법 정기/정밀/진단, ~395줄) 한 짝 → `strategies/inspection.py` (674 줄). PR-DE 동일 패턴 — model(QuoteInput/QuoteResult/QuoteType/OptionalTaskBreakdown/ManhourFormulaStep) + helper(_excel_round_half_up/_resolve_rate)는 부모 package import. `bma_table`/`inspection_legal_table` 함수 내부 lazy import 그대로 유지. seismic helper(`interpolate_seismic_manhours`)는 분리 대상 아님(__init__.py 잔류, PR-DG 동반 이동). __init__.py 1512 → 870 (-642 줄, -42%). pytest 63 passed | e3d4bff |
| **PR-DG Phase 4-J 17단계 — seismic_eval strategy 분리** | `_calculate_seismic_eval`(내진성능평가, ~141줄) + helper 두 개(`interpolate_seismic_manhours` ~50줄, `_SEISMIC_AREA_TABLE` ~14줄) → `strategies/seismic.py` (230 줄). helper는 seismic_eval만 사용 + 외부 import 0건 확인 후 통째 동반 이동(모듈 응집도). __init__.py 870 → 660 (-210 줄, -24%). 누적(PR-DC ~ PR-DG): quote_calculator 1585 → 660 (-58%) / projects 1040 → 576 (-45%). xlsx AA58/AB58/AC58 보간 sanity ±0.001 일치, pytest 63 passed | 2802266 |
| **PR-DH Phase 4-J 18단계 — 소형 4 strategy simple.py 일괄 분리** | `_calculate_field_support`(현장지원, 74줄) + `_calculate_supervision`(구조감리, 72줄) + `_calculate_reinforcement_design`(내진보강, 66줄) + `_calculate_third_party_review`(3자검토, 58줄) → `strategies/simple.py` (297 줄). 응집도 결정 — 4개 모두 단일 인.일 입력 모델 + 단가만 다른 단순 산식이라 한 파일에 묶음(strategies/ 파일 수 8 폭증 회피). __init__.py 660 → 403 (-257 줄, -39%). 누적 quote_calculator 1585 → 403 (-75%) / strategies(struct 106 + inspection 674 + seismic 229 + simple 297) = 1306줄. pytest 63 passed | 24ae196 |
| **PR-DI Phase 4-J 19단계 — weekly_report 패키지 변환 + helpers.py** | `services/weekly_report.py` (1261 줄) → `services/weekly_report/__init__.py` 패키지 변환(`git mv` rename 추적). 작은 helper 10개 + 상수 3개(`_KST`/`_OCCUPATION_RULES`/`_SCHEDULE_TEXT_CATEGORIES`)를 `weekly_report/helpers.py`로 추출(181 줄). External API 표면(`build_weekly_report`/`WeeklyReport`/`SealLogItem`/`SuggestionLogItem`)은 그대로 — `__init__.py`에서 noqa F401 re-export. `weekly_snapshot.py`의 `_avg_task_progress` import만 동시 갱신(Codex 권고 — re-export로 점진 마이그레이션 대신 즉시 갱신). 큰 helper(`_employee_*` / `_project_weekly_plans` ~280줄)는 차기 PR에서 team aggregate와 함께. __init__.py 1261 → 1123 (-138 줄, -11%). pytest 63 passed | dbcbfb5 |
| **PR-DJ Phase 4-J 20단계 — notices 짝 aggregate 분리** | `aggregate_holidays`(법정 공휴일 + 사내휴일 합치기, ~35줄) + `aggregate_notices`(공지/교육 title list, ~22줄) → `weekly_report/notices.py` (87줄). Codex 권고 "PR 작게 유지" → 가장 작고 응집도 높은 짝(둘 다 Notice 모델 + 단순 SQL) 선택. `HolidayItem` model은 __init__.py 잔류, build_weekly_report 직전 import. __init__.py 1123 → 1070 (-53 줄, -5%). pytest 63 passed | 4dec0ed |
| **PR-DK Phase 4-J 21단계 — personnel + sales aggregate 분리** | `aggregate_headcount`(인원현황, ~38줄) + `aggregate_team_members`(팀원 명단, ~29줄) → `weekly_report/personnel.py` (99줄, 인원 짝 — 둘 다 Employee 동일 재직 조건). `aggregate_sales`(영업시작일 cutoff, ~41줄) → `weekly_report/sales.py` (67줄, MirrorSales 단독). 누적 weekly_report __init__.py 1261 → 967 (-23%) / sub-module 4(helpers/notices/personnel/sales) = 434줄. pytest 63 passed | 48721da |
| **PR-DL Phase 4-J 22단계 — projects 도메인 3 aggregate 분리** | `aggregate_stage_projects`(stage 매칭 + 90일 stale, ~49줄) + `aggregate_completed`(end_date cutoff, ~59줄) + `aggregate_new_projects`(start_date cutoff + sales scale, ~57줄) → `weekly_report/projects.py` (217줄). `_TERMINATED_STAGES` 상수도 aggregate_completed 단독 사용 → 동반 이동. `_NEW_STAGES`는 docstring만 언급된 dead code(외과적 수정으로 잔류). 누적 weekly_report __init__.py 1261 → 790 (-37%) / sub-module 5 = 651줄. pytest 63 passed | 954a85b |
| **PR-DM Phase 4-J 23단계 — personal_schedule aggregate 분리** | `aggregate_personal_schedule`(직원×요일 일정 매트릭스, ~53줄) → `weekly_report/personal.py` (84줄). `_SCHEDULE_CATEGORIES` 모듈 상수도 단독 사용 → 동반 이동. helpers의 `_normalize_schedule_category`(휴가→연차/반차 분기 + activity fallback) 의존. 누적 weekly_report __init__.py 1261 → 734 (-42%) / sub-module 6(helpers/notices/personnel/sales/projects/personal) = 735줄. pytest 63 passed | db65ee8 |
| **PR-DN Phase 4-J 24단계 — team 도메인 마지막 분리 (4-J 마무리)** | `aggregate_team_projects`(~84줄) + `aggregate_team_work`(가장 무거움, bulk pre-fetch + bucket 패턴으로 N+1 회피, ~190줄) → `weekly_report/team.py` (446줄). 정렬 상수 `_ACTIVE_STAGES`/`_STAGE_SORT_PRIORITY` + "dead helper" 3개(`_employee_*` / `_project_weekly_plans` — 현재 호출처 없음, docstring 명시 후 잔류) 동반 이동. **누적 weekly_report __init__.py 1261 → 337 (-73%)** / sub-module 7(helpers/notices/personnel/sales/projects/personal/team) = 1174줄. **Phase 4-J 완료** — sales 4 + seal_requests 8 + projects 2 + quote_calculator 4 + weekly_report 7 = 25 sub-module. pytest 63 passed | 91c3e1f |
| **PR-DO Phase 4-J 후속 — dead code cleanup** | `_NEW_STAGES` 상수(weekly_report/__init__.py, docstring만 언급되던 dead) + team.py의 3 dead helper(`_employee_last_week_done` / `_employee_this_week_plan` / `_project_weekly_plans`, PR-W 1차 N+1 fallback이었으나 bulk pre-fetch로 대체됨)와 "사용 X 안내" 주석 정리. dead가 된 `_relation_column` import만 team.py에서 제거(helpers.py 정의 + __init__.py re-export 잔류). __init__.py 337→333, team.py 446→328 (-26%). pytest 63 passed | fa0b5f6 |
| **PR-DP Phase 4-F 잔여 — dashboard /summary role-scope 차등** | `_resolve_user_scope(db, user) -> (scope, team, employee_name)` helper 신설. admin/manager → all / team_lead → team (Employee.linked_user_id 경유, 미연결 시 self fallback + `scope_degraded` 로그) / member → self (canonical Employee.name 사용). /summary endpoint에 적용: 진행중·정체·마감임박 카운트를 scope 필터, top_team도 scope에 맞게, 재무(week_income/expense)는 scope='all'에서만 채움. cache key에 (scope, team, employee_name) 추가, `_CACHE_MAX` 16→64 (Codex 권고). /actions·/insights는 차기 PR. pytest 63 passed + scope helper 6 시나리오 smoke | d773861 |
| **PR-DQ Phase 4-F — dashboard /actions role-scope 차등** | 5 항목 모두 scope 분기: stalled/due_soon/stuck은 teams/assignees 메모리 필터, overloaded_team은 'team'→자기 팀 진행건수·'self'→0(개인 단위 의미 X), overdue_seals는 'all'만 notion query_all 호출(운영 6.4초 병목 회피 — 다른 role count=0). 조건부 query 분기로 scope='all' 단일 query 성능 보존. pytest 63 passed | d51143c |
| **PR-DR Phase 4-F 마무리 — dashboard /insights role-scope 차등 (4-F 완료)** | RecentUpdates(7일 이내 변경 Top 10) + Warnings(미종결 4 flag Top 12) 두 패널에 동일 scope 필터. cache key에 scope 추가. **Phase 4-F 완료** — dashboard 3 endpoint(/summary, /actions, /insights) 모두 admin·manager → 전체 / team_lead → 자기 팀 teams[] / member → 자기 Employee.name이 assignees[]. 재무 + overdue_seals notion 호출은 admin·manager만 노출. pytest 63 passed | 512ce40 |
| **PR-DS Phase 4-E useRoleGuard 잔여 적용** | admin only 2 페이지(`admin/notices` / `admin/employees`)의 useAuth + 인라인 가드 메시지를 useRoleGuard(["admin"]) + UnauthorizedRedirect 표준 패턴으로 일치화. 나머지 useAuth 미적용 페이지(weekly-report/seal-requests/me/suggestions/schedule)는 전 직원 진입 + isAdmin UI 분기 패턴이라 useRoleGuard 부적합 → STATUS 결정 그대로 유지. tsc + lint 통과 | 36064f1 |
| **PR-DT INCIDENT #4/#5 회귀 vitest 보강** | `auth.test.ts`에 5 시나리오 추가 — PR-CX silent flag TTL 회복(legacy "1" → fresh timestamp 자동 갱신 + 5분 전 stale → 재시도 허용) 2 + PR-CY verifyAndHydrateFromMe(200/401/network) 3. 회귀 시 사용자 영구 차단 loop(PR-CX 사고) / callback 무한 재귀(PR-BP/BQ 사고) 즉시 검출. vitest unit이 e2e보다 적합(시간 mock + storage 직접 조작, 3초 fast feedback). 11 passed | 3119ba9 |
| **PR-DU 4-F dashboard role-scope 문서 반영** | USER_MANUAL.md 3.1 대시보드에 KPI/액션/Warnings의 노출 범위가 역할에 따라 다름 1~2 문장 추가 (관리자/관리팀 → 전체 + 재무 / 팀장 → 자기 팀만, 재무·날인 숨김). PERMISSIONS.md "모든 로그인 사용자" 표에 /api/dashboard row 추가 — scope helper, fail-closed self fallback, 재무 admin/manager 전용 명시. PR-DP/DQ/DR의 운영자 안내 / audit 참고 동시 cover | 9d16f85 |
| **PR-DV INCIDENT #5 체크리스트 #3 충족 — authFetch silent retry 제외 list** | `_authFetchInternal`에 `isAuthVerifyEndpoint` 분기 추가 — `/api/auth/me` / `/api/auth/status` 시작 path는 silent SSO trigger 안 함 (미래 회귀 방지 예방, 현재 callsite 없음). silent SSO 자체가 callback page 사용이라 인증 검증 endpoint에서 trigger 시 PR-BP/BQ 패턴 무한 재귀 위험. INCIDENT.md 체크리스트 audit 갱신 — #1/#3/#4 충족, #2 결과적 안전(설계 차이). 4-G PR-BP/BQ 2단계 재시도 가능 상태 진입(staging dual-run 안전망은 추가 필요). vitest 13 passed (2 신규) | aec8e01 |
| **PR-DW /help page USER_MANUAL sync — dashboard role-scope** | PR-DU에서 USER_MANUAL.md 3.1에 추가한 role-scope 차등 안내(KPI/액션/Warnings 노출 범위가 역할에 따라 다름)를 in-app `/help` page에도 sync. 운영자가 실제로 시스템에서 보는 콘텐츠와 일치하도록 — V-3 cross-check 컨벤션 유지. tsc + lint 통과 | 740fc60 |
| **PR-DX INCIDENT #1 추적 4항목 audit (모두 clean)** | 2026-05-12 SQLAlchemy connection leak 사고의 "추적 항목 (별도 cycle 진행)" 4개 모두 audit → 모두 [x]: (1) `_report_cache`는 Pydantic DTO만 보관 ORM X (2) sync.py 11 callsites + 다른 background 5 service 모두 with/try-finally close 보장 (3) PDF service는 Session 의존 0 + 라우터는 Depends(get_db) 자동 close (4) silent except 안 SessionLocal() 호출 0건. 근본 안전망은 PR-AQ + PR-DA로 cover. **INCIDENT #1 클로즈** | cf4eab8 |
| **PR-DY INCIDENT #1 교훈 #1 — healthCheckPath 교체** | `backend/render.yaml` `healthCheckPath` `/health` → `/api/health/db` 1줄 변경. `/health`는 DB 안 거쳐 connection pool 고갈 시 Render auto-restart trigger 안 됐던 문제(2026-05-12 사고 시 수동 Restart 필요) 해소. `/api/health/db`(PR-DB)는 SELECT 1 + idle_in_transaction_session_timeout SHOW 거쳐 DB 끊김이면 503 반환 → Render auto-restart 자동 트리거. PR-AQ + PR-DA 안전망과 합쳐 sub-5분 사고 복구 가능 | 4bbfb44 |
| **PR-DZ Phase 4-C 1차 — list_projects 페이지네이션** | backend `list_projects`에 `offset` / `limit` Query + `total` 필드 추가. Codex 권고: limit 미지정 unbounded(backward-compat) / 명시 시 max 500 cap / count(현 페이지)+total(filter 적용 후 전체) 동시 노출 / total Optional(None default — frontend 타입 충돌 회피) / ORDER BY code+page_id tie-breaker. SELECT COUNT(*) subquery는 offset/limit 명시 시에만 호출 → 기존 호출처 성능/응답 영향 0. frontend SWR 갱신은 차기 PR. pytest 63 passed | 502a4b8 |
| **PR-EA Phase 4-C 2차 — list_tasks 페이지네이션** | PR-DZ 동일 패턴: backend `list_tasks`에 `offset` / `limit` + `total` Optional 추가, max 500 cap, ORDER BY `end_date NULLS LAST` + `page_id` tie-breaker. SELECT COUNT(*) subquery 조건부 호출. 기존 frontend `listTasks()` 호출 영향 0. pytest 63 passed | 8c17f57 |
| **PR-EB Phase 4-C 3차 — list_sales 페이지네이션 (backend 1차 완료)** | PR-DZ/EA 동일 패턴: backend `list_sales` offset/limit + total Optional, ORDER BY `created_time DESC NULLS LAST` + `page_id` tie-breaker. **4-C backend 1차 완료** — list_projects/tasks/sales 3 endpoint 일관 페이지네이션. pytest 63 passed | ad0abb3 |
| **PR-EC Phase 4-C frontend 노출 — domain + lib/api option** | 3 `ListResponse` 타입(Project/Task/Sale)에 `total?: number` 추가 + 3 lib/api 함수(listProjects/Tasks/Sales) filters에 `offset?: number` / `limit?: number` 옵션 추가. 기존 호출처 0 영향(option 미지정 시 동일 동작). pagination UI(URL ?page=N) 적용은 차기 PR. tsc + lint 통과 | c12d4e7 |
| **PR-ED Phase 4-C 3차 — q search push-down** | backend list_projects/tasks/sales에 `q` 파라미터(ILIKE 부분 일치, 대소문자 무시) 추가: projects/sales는 `code OR name`, tasks는 `title OR code`. frontend listX filters에도 `q?: string` 추가. 기존 호출처 0 영향. /projects 페이지의 client-side 검색을 backend로 push down 가능 + pagination과 조합으로 검색 결과 page 단위 fetch 가능. pytest 63 + tsc + lint 통과 | d20cea0 |
| **PR-EE 4-C 인프라 종료 표기 + 4-H 1단계 docs_audit** | 4-C는 backend pagination/search 인프라 완료 + frontend lib/api 옵션 노출까지 충분 — 페이지 UI 적용은 row 수 임계점(1000+) 넘을 시점으로 보류(현재 client 즉시 검색이 UX 우위, 의도된 결정). `scripts/docs_audit.py` 신설(4-H 1단계): STATUS.md commit hash 99개를 `git rev-parse`로 일관성 검증 — 모두 git log에 존재 확인. stdlib만 사용(venv 불필요) | 0eb561a |
| **PR-EF 4-H 2단계 — USER_MANUAL ↔ /help section sync 자동화** | docs_audit.py에 검사 추가 — 두 파일의 섹션 번호(N.M) set 일치(문구는 의도적으로 다를 수 있어 번호만). 초회 실행에서 `### 9.4 「Sync 관리」`가 /help page에 누락된 것 발견(PR-AR 도입 시 USER_MANUAL만 추가, /help sync 누락) → /help page에 9.4 섹션 추가 후 19/19 일치 OK. V-3 cross-check 수동 작업 자동화 | ea17a0a |
| **PR-EG 4-H 3단계 — docs_audit CI job 통합** | `.github/workflows/ci.yml`에 신규 job `docs` 추가 — ubuntu-latest, python 3.12, `checkout@v4 fetch-depth: 0`(STATUS의 옛 hash까지 rev-parse 가능), `python scripts/docs_audit.py` 실행. dependency 0 (stdlib만). PR 시점 자동 회귀 검출 → 운영자 수동 V-3 cross-check 부담 해소 | d1f125e |
| **PR-EH 4-H 4단계 — INCIDENT 체크리스트 형식 audit** | docs_audit.py에 3번째 검사 추가: `- [ ]` / `- [x]` 만 valid, `- [X]` / `- []` / `- [ x]` / `- [xx]` 등 GitHub markdown 렌더 안 되는 오타 검출. pending(미완료) 카운트는 정보용 표시(FAIL 아님). 5/5 valid 통과. 잔여: PERMISSIONS ↔ backend require_* cross-check | ab4aa60 |
| **PR-EI 4-H 5단계 완료 — PERMISSIONS ↔ backend require_* sync** | docs_audit.py에 4번째 검사 추가 — `backend/app/security.py`의 `def require_X(...)` set과 PERMISSIONS.md의 \`require_X\` 백틱 set 양방향 비교. 신규 helper 추가 + 문서 누락 / deprecated 제거 + 문서 잔존 즉시 검출. 현재 4개(`require_admin`/`_admin_or_lead`/`_admin_or_manager`/`_editor`) 모두 일치. **4-H 5 검사 모두 통과 + CI 통합 완료** | 2a61ca5 |
| **PR-EJ 4-D 1단계 — admin 운영 페이지 → /operations/ 재구성** | 사이드바 3 그룹과 URL 계층 일치화. 운영 영역 4 페이지(`admin/incomes`+`clients` / `admin/expenses` / `admin/contracts`)를 `app/operations/` 하위로 `git mv` 폴더 단위 이동(history 보존). Sidebar/KPICards href 5건 갱신. Codex 권고: 폴더 단위 mv + sub-route 별도 명시 + employee-work 차기 PR. tsc + lint 통과. **주: next.config.ts redirects 4건이 commit에 누락된 것을 PR-EK에서 발견 → PR-EK가 5건 모두 보강** | 9cc755c |
| **PR-EK 4-D 2단계 — admin/employee-work → /operations/ + PR-EJ redirects 보강** | `app/admin/employee-work/` → `app/operations/employee-work/` git mv (팀장 권한, 운영성 페이지). callsite 4 갱신 (Sidebar / ReportPreview sourceHref / PriorityActionsPanel ctaHref / help page). next.config.ts redirects 5건 한 번에 추가 — PR-EJ에서 누락됐던 4건(incomes/clients/expenses/contracts) + 이번 1건(employee-work). 모두 308 permanent. /operations/incomes/layout.tsx tabs path도 PR-EJ 폴더 이동 후 옛 path 잔존 → 갱신. tsc + lint 통과 / `/admin/(incomes|expenses|contracts|employee-work)` 잔존 0건. **4-D 1·2단계 완료** | b731285 |

## 미완료 / 보류

### ✅ Phase 1·2·3 — 모두 완료
DASH-001~004 / PROJ-001~005 / MY-001~005 / WEEK-001~005 / COMMON-001~003 항목 모두 PR-A ~ PR-R로 완료.

### Phase 4 잔여 (장기 인프라 — 외부 1번 리뷰 12.3, 12.4)

| 항목 | 상태 | 비고 |
|---|---|---|
| **4-A** lib/api.ts 도메인 분리 | ✅ 완료 (PR-S/S2/AR/BD/BE/BG, 100%) | 15/15 도메인 lib/api/*.ts. lib/api.ts는 49줄 re-export hub만 남음 |
| **4-B** 대형 컴포넌트 외과적 분리 | ✅ 완료 (PR-AE~BC, 13 cycle) | -2701줄/-26%, 신규 분리 18개. 본격 design refactor는 별도 cycle |
| **4-C** 리스트 서버 필터링·페이지네이션 | ✅ 인프라 완료 (PR-DZ/EA/EB/EC/ED, backend + frontend lib option). 페이지 UI 적용은 row 수가 client-side filter 임계점(1000+) 넘을 시점에 활성 — 현재 수백 row 수준에선 client 즉시 검색이 UX 우위라 의도된 보류 |
| **4-D** 메뉴 그룹 URL 재구성 | ✅ 1·2단계 완료 (PR-EJ/EK) | 운영 5 페이지(incomes/clients/expenses/contracts/employee-work) → /operations/. next.config redirects 5건 308 영구. 사이드바 그룹과 URL 일치. 잔여 /admin/* 5개(notices/employees/users/sync/drive)는 시스템 관리 적합 — 유지 |
| **4-E** 권한 로직 layout 통합 | 미진행 | 페이지마다 분산된 가드를 layout 레벨로 |
| **4-F** 대시보드/주간보고 집계 API 별도 | 미진행 | client-side aggregation을 backend로 push |
| **4-G** JWT localStorage → httpOnly cookie | 1단계 완료(PR-BH) / 2단계(PR-BI/BP/BQ 3회 시도 모두 운영 회귀로 revert). 안전망(PR-BN saveAuth backward-compat / PR-BO 401 silent retry / PR-BL-5 e2e)은 살아있음. 다음 재시도 전 INCIDENT.md PR-BP/BQ entry 체크리스트 4항목(hydrate raw fetch / callback에서 호출 X / silent retry 인증 endpoint 제외 / PR-BP 후 PR-BQ) 충족 필요 | XSS 방어 강화 |
| **4-F** 대시보드/주간보고 집계 API | ✅ 완료 (PR-BJ-1~5 + PR-BK 1차 backend 집계 + TTL cache, PR-DP/DQ/DR 3 endpoint 모두 role-scope 차등) | dashboard N+1 → 1 fetch, 4 role 권한 차등 |
| **4-I** 테스트 framework | Vitest(PR-BL-1/2, 18 단위 테스트) + Playwright(PR-BL-3 smoke + PR-BL-5 4 role 시나리오, 누적 5 e2e) + GitHub Actions CI(PR-BL-4) 완료 / 잔여(backend full mock e2e — 미정밀) | PR-BI 같은 회귀 자동 검출 |
| **4-E** 권한 layout 통합 | ✅ 완료 (PR-BS/BT/BU + PR-DS, 누적 12 page) | useRoleGuard 적용 가능한 admin/role-list 가드 페이지 모두 완료. 나머지(weekly-report/seal-requests/me/suggestions/schedule)는 전 직원 진입 + UI 분기 패턴이라 useAuth 유지가 적합 |
| **4-H** 문서 자동 동기화 체계 | ✅ 완료 (PR-EE~EI, 4 검사 + CI 통합) — STATUS hash / USER_MANUAL ↔ /help section / INCIDENT 체크리스트 형식 / PERMISSIONS ↔ backend require_* 자동 검증 |
| **4-I** Frontend 테스트 framework | 미진행 | Vitest + Playwright |
| **4-J** Backend 라우터/서비스 분할 | ✅ 완료 (PR-CC ~ PR-DO, 24단계 + cleanup) | sales 4 + seal_requests 8 + projects 2(1040→576, -45%) + quote_calculator 4 strategy(1585→403, -75%) + weekly_report 7 sub-module(1261→333, -74%). 총 25 sub-module. PR-DO dead code cleanup 적용 |

### Backend atomicity·페이징·silent except (외부 리뷰 12.x — 1차 모두 완료)
| 항목 | 상태 | 비고 |
|---|---|---|
| Drive↔Notion atomicity | 1차 완료 (PR-CA) | seal_requests 마지막 update_page 실패를 partial_errors 노출. 2차 보상 트랜잭션은 워크플로 검토 후 |
| `_sync_sale_estimated_amount` race | ✅ 완료 (PR-BZ) | `db.get()` → `SELECT ... FOR UPDATE` row lock |
| `query_all` 페이징 | ✅ 완료 (PR-CB) | max_pages=200 + cursor 검증 + cycle 검증 fail-fast |
| silent except → partial-failure | ✅ 1차 완료 (PR-BV/BW/BX/BY) | partial_errors schema + 사용자 안내 alert. `docs/audit/silent_except.md` 참조 |

### 작은 잔여 (낮은 우선순위)
| 항목 | 비고 |
|---|---|
| **PR-BI 재시도 (Phase 4-G 2단계)** | INCIDENT.md PR-BP/BQ 체크리스트 4항목 충족 후. 안전망(PR-BN/BO/BL-5/CX/CY) 모두 적용됨 |
| **mirror endpoint slow** | PR-CR 계측 수집 후 진단. PR-CL/CQ로 dashboard 6.4초 병목은 해소 |

### 사용자 결정으로 close
| 항목 | 비고 |
|---|---|
| **#113** /sales — onClose ?sale= query 정리 | 이미 처리됨 (commit 9dea4a9 + e0fade2). task list만 stale였음 |
| **#116** /weekly-report 페이지 PDF와 양식 통일 | 데이터/섹션 순서/컬럼 라벨 모두 1:1 동일 (ReportPreview 헤더 주석에도 명시). 시각 차이(폰트 사이즈/cell-shrink/badge-bid/empty placeholder)는 PDF 인쇄용 vs 모니터 화면용으로 의도된 차이 |

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
- `pool_reset_on_return="rollback"` (PR-AQ — 명시적 표기)
- connect 시 `SET idle_in_transaction_session_timeout = '300s'` (PR-DA — backend cleanup 누락돼도 5분 후 DB측 자동 회수)
- Supavisor 50까지 여유 35

근본 leak source 추적은 PR-DA로 사실상 해소. 자세한 내역은 [INCIDENT.md](INCIDENT.md#2026-05-15--idle-in-transaction-connection-4시간-잔존--alter-table-lock-wait) 참조.

### Supabase 진단 도구

`mcp__plugin_supabase_supabase__get_logs(project_id="hxhdqjbzfuddinoejoyo", service="postgres")` —
정상 backend connection은 `application_name=Supavisor`로 노출. `supabase/dashboard`만 보이고 `Supavisor`가 없으면 backend connect 실패 신호.

### 사고 대응 매뉴얼

운영 사고 발생 시 [INCIDENT.md](INCIDENT.md#사고-대응-체크리스트-재발-시) 의 체크리스트 참조.
주요 매핑: `QueuePool limit` → SQLAlchemy 풀 고갈 / `EMAXCONNSESSION` → Supavisor 풀 고갈 / `Network is unreachable` (`2406:...`) → IPv6 endpoint 시도.
