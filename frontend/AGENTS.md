<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
React 19 + Tailwind 4도 동일 — 변경된 API 확인 후 작성. 타입 검증: `npx tsc --noEmit`.
<!-- END:nextjs-agent-rules -->

## 명령어
- `npm run dev` — dev 서버 (port 3000)
- `npm run build` — production build
- `npm run lint` — ESLint (eslint.config.mjs)
- `npx tsc --noEmit` — type check

## 구조
- `app/` — App Router 페이지 (sales/, project/, seal-requests/, weekly-report/, admin/notices/, me/, ...)
- `components/` — UI components (sales/, project/, seal-requests/, me/, dashboard/, ui/)
- `lib/` — domain.ts (타입), api.ts (fetch), hooks.ts (SWR — useProjects/useSales/useEmployees), types.ts (UserRole/ROLE_LABEL), utils.ts

## 라우트 패턴
- 프로젝트 상세: `/project?id={page_id}` — 단일 page (Suspense + ProjectClient)
- 영업 상세: `/sales?sale={page_id}&from={referrer}` — list page에서 modal 자동 open. `from` query 있으면 모달 닫을 때 그 path로 router.push 복귀(weekly-report·project 사용). 없으면 query만 정리해 모달 재오픈 방지.
- 주간 일지: `/weekly-report` — 사이드바엔 없음. 진입은 대시보드/`/me` 우상단 emerald `[주간업무일지 보기]` 버튼.
  - admin: `[PDF 확인]` (현재 입력 기간 빌드) + `[발행]` (확인 dialog → Drive 업로드 + Bot 전직원 알림 + log)
  - 비admin: `[PDF 다운로드]` (마지막 발행본만, `/api/weekly-report/last-published.pdf`)
  - mount 시 `last-published` fetch → lastWeekStart 자동 셋팅 (사용자가 직접 수정하면 차단)
  - 표 내부 자간 좁힘 + nowrap + ellipsis: `.weekly-report-tables` class scope
  - 프로젝트명/용역명 link: `ProjectLink` (blue) / `SaleLink` (emerald) — admin만 navigable, 비admin은 plain text
- /me: 담당 프로젝트(`ProjectTaskRow`) + 내 영업(`SaleTaskRow`, `sales_ids` 기반 task Kanban). 휴가 카드 우상단 `+ 새 휴가` 버튼 → TaskCreateModal initialCategory='휴가(연차)'.

## 사이드바
`Sidebar.tsx`는 3-그룹 구조 — 공통(label 없음, 항상 펼침) / 운영 관리(admin·manager) / 시스템 관리(admin only). 후자 두 그룹은 `▶/▼` 펼침/접힘 (in-memory state). NavItem.hiddenForRoles로 manager에 9개 메뉴만 노출.

## role
- `UserRole = "admin" | "team_lead" | "manager" | "member"` (`lib/types.ts`)
- manager(관리팀) — 대시보드/직원일정/사용매뉴얼 + 운영 관리 6개 메뉴만 노출. 일반 직원 작업 영역(내 업무/날인/건의/유틸)과 시스템 관리는 미노출.

## 환경변수
`NEXT_PUBLIC_API_BASE` — backend FastAPI URL (개발 `http://localhost:8000`)
