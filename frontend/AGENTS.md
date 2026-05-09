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
- `app/` — App Router 페이지 (sales/, project/, seal-requests/, weekly-report/, admin/notices/, ...)
- `components/` — UI components (sales/, project/, seal-requests/, ui/)
- `lib/` — domain.ts (타입), api.ts (fetch), hooks.ts (SWR — useProjects/useSales/useEmployees), utils.ts

## 라우트 패턴
- 프로젝트 상세: `/project?id={page_id}` — 단일 page (Suspense + ProjectClient)
- 영업 상세: `/sales?sale={page_id}` — list page에서 modal 자동 open
- 주간 일지: `/weekly-report` — 3개 날짜 input(지난주 시작 / 이번주 시작 / 종료) + PDF 다운로드
  - 표 내부 자간 좁힘 + nowrap + ellipsis: `.weekly-report-tables` class scope
  - 프로젝트명/용역명 link: `ProjectLink` (blue) / `SaleLink` (emerald) 헬퍼 컴포넌트

## 환경변수
`NEXT_PUBLIC_API_BASE` — backend FastAPI URL (개발 `http://localhost:8000`)
