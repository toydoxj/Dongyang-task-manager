# PRD — 동양구조 업무관리

## 목적

1. (주)동양구조의 업무관리를 위한 사내 웹 애플리케이션.
2. 사내 구성원이 로그인하여 자신의 프로젝트 진행현황·업무·날인요청을 기입한다.
3. 프로젝트의 업무 현황을 시각적으로 표현(대시보드, 칸반, 차트).
4. 노션 DB와 연계되어 단일 진실 원천을 유지하고, NAVER WORKS Drive·Bot·Calendar 와도 통합된다.

## 구현 방식

1. **웹 애플리케이션** — 브라우저로 `https://task.dyce.kr` 접속.
2. 노션 DATABASE 와 연계 — `mirror_*` Postgres 테이블로 5분 incremental sync, 매일 03:00 full reconcile.
3. 인증은 NAVER WORKS SSO (JWT, HS256). 일반 가입 흐름은 관리자 승인 절차.

## 호스팅

| 영역 | 플랫폼 |
|---|---|
| Frontend | Vercel (Next.js 16, App Router) |
| Backend | Render Starter (FastAPI / uvicorn) |
| DB | Supabase Postgres (Pooled URI) |
| Sync Cron | Render Cron Job (5분 incremental + 매일 full) |

## 노션 DATABASE

운영 DB ID는 backend `.env` 에 정의. 주요:

- `NOTION_DB_PROJECTS` — 메인 프로젝트
- `NOTION_DB_TASKS` — 업무 TASK
- `NOTION_DB_CASHFLOW` / `NOTION_DB_EXPENSE` — 수금 / 지출
- `NOTION_DB_CLIENTS` — 발주처(협력업체)
- `NOTION_DB_MASTER` — 마스터 프로젝트
- `NOTION_DB_SEAL_REQUESTS` — 날인요청
- `NOTION_DB_ASSIGN_LOG` — 담당 변경 이력
- `NOTION_DB_SUGGESTIONS` — 건의사항

## 외부 연동

- **NAVER WORKS SSO**: 사용자 로그인 (`works_user_id` 매핑).
- **NAVER WORKS Drive**: 프로젝트 폴더 자동 생성 + 날인요청 검토자료 폴더(`0.검토자료/YYYYMMDD/`) 관리.
- **NAVER WORKS Bot**: 날인요청 단계별 알림 (트리거 매트릭스: [`docs/bot_trigger.md`](./docs/bot_trigger.md)).
- **NAVER WORKS Calendar**: 업무 일정 동기화.

## 비기능 요구사항

- **응답 시간**: read는 mirror 우선이라 100ms 이내 목표. write는 노션 응답 + write-through 1~3초.
- **장애 회복**: 노션 502/503/504/429 transient 자동 retry (max 4회, deadline 60초).
- **보안**: JWT secret 운영자 토글. 일반 사용자 가입은 관리자 승인 후 활성.
- **권한**: admin / team_lead / member 3단계.
