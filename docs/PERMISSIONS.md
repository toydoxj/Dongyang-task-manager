# 권한 정책 (Permissions)

본 문서는 Dongyang-task-manager의 라우터별 권한 정책 source-of-truth.
변경 시 backend/app/security.py + 본 문서 동시 갱신.

## 역할 (Role)

`backend/app/auth.py VALID_ROLES = {admin, team_lead, manager, member}`

| 역할 | 한글 라벨 | 정책상 의미 |
|---|---|---|
| `admin` | 관리자 | 전체 권한. 시스템 관리·민감 작업 단독 보유. |
| `team_lead` | 팀장 | 팀 운영 + 일부 승인(날인 1차 등). |
| `manager` | 관리팀 | 운영 관리(수금·발주처·계약분담 등). 시스템 관리·일반 직원 작업 영역은 미노출. |
| `member` | 일반 직원 | 자기 업무 위주. 운영 데이터는 read 위주. |

## 보안 헬퍼 (`backend/app/security.py`)

| 헬퍼 | 통과 역할 | 사용처 |
|---|---|---|
| `get_current_user` | 모든 로그인 사용자 | 일반 read·자기 데이터 작업 |
| `require_admin` | admin | 시스템 관리·승인·삭제 등 |
| `require_admin_or_lead` | admin + team_lead | 직원 명부, 날인 1차 승인·반려 |
| `require_admin_or_manager` | admin + manager | 수금(cashflow incomes) |
| `require_editor` | admin + team_lead + manager | 운영 편집(프로젝트 일반 편집·계약분담) |

## 권한 매트릭스

### 시스템 관리 (admin only)

| 라우터 | 작업 | 비고 |
|---|---|---|
| `/api/auth/users/*` | 승인·역할 변경·수정·삭제 | |
| `/api/admin-bot/*` | bot 테스트 메시지 | |
| `/api/admin-calendar/*` | 공유 캘린더·sync·backfill | |
| `/api/admin-drive/*` | Drive 연결·status | |
| `/api/admin/sync/status` `/api/admin/sync/run` | 노션 미러 sync 상태 조회·강제 트리거 | PR-AR |
| `/api/employees POST/PATCH/DELETE/resign/restore/reorder/upload` | 직원 명부 관리 | |
| `/api/notices POST/PATCH/DELETE` | 공지/교육/휴일 등록·수정·삭제 | 사용자 결정 2026-05-11: admin only 유지 |
| `/api/projects/{id}/stage` | 프로젝트 단계 변경 | 진행중/대기/보류/완료/타절/종결/이관 |
| `/api/weekly-report/publish` | 주간업무일지 발행 (Drive 업로드 + 알림) | |
| `/api/clients DELETE` | 발주처 삭제 | 보수적 유지 (PR-AC) |

### 운영 편집 (admin + team_lead + manager)

`require_editor` 적용. member는 read-only.

| 라우터 | 작업 | 비고 |
|---|---|---|
| `/api/projects/{id} PATCH` | 프로젝트 일반 편집 (이름·발주처·금액·phase 등) | PR-Y |
| `/api/contract-items POST/PATCH/DELETE` | 계약 분담 (공동수급·추가용역) | PR-Y |
| `/api/admin/employees GET ""` | 직원 명부 조회 | PR-AT (manager 휴가·연락처 등 운영 참조 필요) |

### admin + manager (관리팀 운영)

`require_admin_or_manager` 적용.

| 라우터 | 작업 | 비고 |
|---|---|---|
| `/api/cashflow/incomes POST/PATCH/DELETE` | 수금 등록·수정·삭제 | PR-AB |

### admin + team_lead (팀장 권한)

| 라우터 | 작업 | 비고 |
|---|---|---|
| `/api/seal-requests/{id}/approve-lead` | 날인 1차 승인 | |
| `/api/seal-requests/{id}/reject` | 날인 반려 | |
| `/api/seal-requests/{id}/approve-admin` | 날인 최종 승인 | admin only (위계상 admin 단독) |
| `/api/seal-requests "" GET (project_id 없이)` | 회사 전체 날인 목록 | project_id 있으면 모든 직원 가능 |

### 모든 로그인 사용자 (전 직원)

| 라우터 | 작업 | 비고 |
|---|---|---|
| `/api/auth/me` GET/PUT, `/api/auth/me/midas` | 본인 정보 | |
| `/api/cashflow GET` | 수금·지출 통합 시계열 | |
| `/api/clients GET/POST/PATCH` | 발주처 read·생성·수정 | DELETE만 admin (PR-AC) |
| `/api/contract-items GET` | 계약 분담 목록 | |
| `/api/employees/teams-map` | 팀 매핑 | |
| `/api/master-projects *` | 마스터 프로젝트 read·PATCH·이미지 CRUD | audit 미결정 (현재 누구나) |
| `/api/notices GET` | 공지 목록 | |
| `/api/projects POST/GET/works-drive/assign/sync-stage/Drive children/Drive 업로드/삭제 등` | 프로젝트 생성·담당자 배정·Drive 작업 | 사용자 결정 2026-05-11: 현재 유지 |
| `/api/sales *` (POST/PATCH/DELETE/quote/convert/quotes 등 전부) | 영업 등록·수정·삭제·견적·전환 | 사용자 결정 2026-05-11: 현재 유지 |
| `/api/seal-requests POST/PATCH/attachments/redo/delete/download/preview` | 날인요청 등록·수정·첨부 (status 가드 자체에 위계 분기) | |
| `/api/suggestions *` | 건의 등록·수정·삭제 | 본인것만 수정·삭제 (내부 가드) |
| `/api/tasks *` | TASK 생성·수정·삭제 (담당자/생성자 본인) | |
| `/api/weekly-report GET/.pdf/last-published/last-published.pdf` | 주간업무일지 조회·다운로드 | 모든 직원 동일 콘텐츠 (날인대장 포함, PR-AA) |

## 프론트엔드 가드

### 사이드바 (`frontend/components/Sidebar.tsx`)

3개 그룹 — 공통(label 없음, 항상 펼침) / 운영 관리 / 시스템 관리.

| 그룹 | 노출 역할 | 메뉴 |
|---|---|---|
| 공통 | 모두 | 대시보드 / 내 업무 / 프로젝트 / 영업 / 날인 / **건의사항 (manager 포함 PR-AS)** / 직원 일정 / 사용 매뉴얼 |
| 운영 관리 | admin + team_lead + manager | 발주처 / 수금 / 지출 / 계약서 / 공지 / 직원 명부 |
| 시스템 관리 | admin only | 사용자 관리 / **Sync 관리 (PR-AR)** / 캘린더 / 봇 / 드라이브 |

`NavItem.hiddenForRoles`로 manager에 일부 메뉴 비노출 (member 작업 영역).

### 페이지 가드

`frontend/components/AuthGuard.tsx useAuth()` 훅으로 user.role 분기.

| 페이지 | 가드 | 비고 |
|---|---|---|
| `/projects` | admin + manager | (현 정책 — team_lead 검토 필요) |
| `/sales` | admin + manager | |
| `/admin/incomes` | admin + manager | backend cashflow와 일치 (PR-AB) |
| `/admin/clients` | (확인 필요) | |
| `/admin/notices` | admin only | backend notices와 일치 |
| `/admin/users` | admin only | |
| `/project/{id}` 편집 버튼 | admin + team_lead + manager | PR-Y |
| ContractItemsEditor 입력 | canEdit prop (default true). 부모가 admin+team_lead+manager 분기 | PR-Y |
| `/seal-requests` (목록) | admin + team_lead | backend list_seal_requests와 일치 |
| `/weekly-report` 발행 버튼 | admin only | publish endpoint 가드와 일치 |
| `/weekly-report` PDF 확인/다운 버튼 | admin: PDF 확인/최근 발행 PDF / 비admin: PDF 다운로드(=최근 발행본) | PR-Z |

## 변경 이력

| PR | 날짜 | 변경 |
|---|---|---|
| PR-X | 2026-05-11 | contract_items CUD: admin → admin+manager (이후 PR-Y에서 require_editor로 확장) |
| PR-Y | 2026-05-11 | require_editor 헬퍼 추가. projects.update + contract_items CUD = admin+team_lead+manager |
| PR-Z | 2026-05-11 | weekly_report — admin도 [최근 발행 PDF] 다운 버튼 |
| PR-AA | 2026-05-11 | weekly_report 날인대장 가드 제거 — 모든 직원에게 보고용 콘텐츠 동일 노출 |
| PR-AB | 2026-05-11 | cashflow incomes CUD: admin → admin+manager |
| PR-AC | 2026-05-11 | clients PATCH: admin → 전 직원. DELETE는 admin 유지 |
| PR-AR | 2026-05-12 | `/api/admin/sync/*` 신규 라우터 (require_admin). 업무시간(KST 06~20) cron 회피 + admin 강제 트리거 페이지 `/admin/sync` |
| PR-AS | 2026-05-12 | Sidebar 「건의사항」 manager 노출 (backend는 이미 모든 직원 허용 — UI gap 해소) |
| PR-AT | 2026-05-12 | employees.GET "" 직원 명부: admin+팀장 → admin+팀장+manager (require_editor). master_projects는 현재 유지(전 직원) 결정 |

## audit 결과 (모든 결정 항목)

- 모든 운영/시스템 라우터 권한 매트릭스 완료
- master_projects = 전 직원 read/PATCH/이미지 CRUD (포트폴리오 운영 흐름상 의도된 개방)
- 미결정 항목 없음 (PR-AT 시점)
- `seal_requests` 내부 status 가드 통일 (현재 라우트별 분산 — 점검 필요).
