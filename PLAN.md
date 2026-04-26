# (주)동양구조 업무관리 앱 — 상세 계획

> 원천 요구사항: `PRD.md`
> 참조 자산: https://github.com/toydoxj/DY_MIDAS_PROJECT
> 최종 갱신: 2026-04-26 (실제 노션 스키마 반영)

---

## 1. 시스템 아키텍처

```
┌────────────────────────────────────────────────┐
│ Electron Shell (main.js, preload.js)           │
│  ├─ Next.js Renderer (UI, port 3000)           │
│  └─ FastAPI Sidecar (PyInstaller, port 8000)   │
└────────────────────────────────────────────────┘
              │              │
              ▼              ▼
   ┌──────────────────┐  ┌──────────────────────┐
   │ Local SQLite      │  │ Notion API           │
   │ (사용자/세션/캐시) │  │ (프로젝트/업무 SSOT)  │
   └──────────────────┘  └──────────────────────┘
```

- **Local SQLite**: 사용자 계정·JWT 세션·노션 응답 캐싱·변경이력
- **Notion**: 프로젝트/업무/금액의 단일 원천(SSOT)
- **유틸 런처**: 외부 도구(MIDAS Civil/Gen NX, Drive 등) 사이드바 카드

---

## 2. 노션 DB 매핑 (실측)

### 2.1 메인 — `(주)동양구조 업무관리 - 프로젝트`
- 데이터소스: `collection://307e8498-6c86-8063-af41-000b4d2777e2`
- URL: https://www.notion.so/307e84986c8680d6a817e626e99c73c8
- 부모 페이지: `Project` (`41895be5a9644284a5c7ec568f2f9b18`)

| 분류 | 핵심 속성 |
|---|---|
| 식별 | 프로젝트명(title), Sub_CODE, Master Project(relation), Master Code(rollup) |
| 조직 | 담당팀(구조1~4팀/진단팀/기타), 담당자(30+명), 퇴사 담당 |
| 업무 유형 | 업무내용(36종 multi_select) |
| 상태 | 진행단계(진행중/대기/보류/완료/타절/종결/이관), 계약✓, 완료✓ |
| 일정 | 시작일(수주확정), 계약기간(range), 완료일 |
| 금액 | 용역비(VAT제외), VAT, 공법검토비, 외주비(예정), 기성금, 실금액(formula) |
| 재무 추적 | 수금률, 수금합(rollup), 지출(외주비포함)(rollup), 연도구간 수금/지출(formula) |
| Relations | 발주처, 공법업체, 견적서, 날인, 업무TASK★, 업무TASK(완료)†, Task†, 회사 지출내역, 수금현황, Master Project |

★ 새로 생성, † 마이그레이션 후 폐기 예정

### 2.2 신규 — `업무TASK` (통합)
- 데이터소스: `collection://9210a5ac-4531-4610-bcb9-76806fe06560`
- URL: https://www.notion.so/f18078a0fd7647359b9b3990632abc0c
- 양방향 관계: 메인 프로젝트 DB

| 속성 | 타입 | 비고 |
|---|---|---|
| 내용 | title | |
| 프로젝트 | relation (메인, dual) | |
| CODE | text | |
| 담당자 | multi_select (28명, 색상 통일) | |
| 담당팀 | multi_select (5팀) | |
| 상태 | status | ⚠️ "보류" 옵션 노션에서 수동 추가 필요 |
| 진행률 | number(percent) | 0~100 |
| 기간 | date range | 시작일~예상완료일 (간트 X축) |
| 실제 완료일 | date | 완료 시 자동 채움 |
| 우선순위 | select (높음/보통/낮음) | |
| 비고 | text | |
| 생성일 | created_time | 자동 |

### 2.3 보조 DB
| 이름 | 데이터소스 | 핵심 속성 |
|---|---|---|
| 💰 프로젝트 수금 내역 | `310e8498-6c86-804b-bc3e-000b8442d2e8` | 수금일, 수금액(원), 회차 |
| 회사 지출내역 | `310e8498-6c86-8015-a1ff-000bd01a9ace` | 지출일, 금액, 구분(19종), 외주업체 |
| 업무TASK(완료) † | `31ce8498-6c86-80a1-80e1-000b47ccbfe7` | 마이그레이션 후 archive |
| 업무TASK(예정) † | `31ce8498-6c86-8169-8822-000b0e42c569` | 마이그레이션 후 archive |
| Task † | `31be8498-6c86-805a-9222-000bfe621ba7` | 통합 권한 없음 → 폐기 검토 |
| 발주처 | `307e8498-6c86-8004-982e-000b611ac246` | |
| 견적서 | `324e8498-6c86-80b6-a330-000b4e71c63a` | |
| 날인 | `320e8498-6c86-80fe-9beb-000b972ae431` | |
| 공법업체 | `31ee8498-6c86-8195-8c1a-000be765e7ad` | |
| Master Project | `307e8498-6c86-80a7-8f0a-000b24f6af88` | |

---

## 3. 시각화 설계 (관건 영역)

### 레이어 A — 전사 대시보드 (홈)
| # | 위젯 | MVP | 데이터 |
|---|---|---|---|
| A1 | 진행단계별 칸반 (건수+금액합) | ★ | 메인.진행단계 그룹 |
| A4 | 월별 매출/수금 콤보차트 | ★ | 메인.시작일 × 용역비 / 수금합 |
| A2 | 팀별 부하 히트맵 | △ | 메인.담당팀 × 계약기간 |
| A3 | 업무유형 매출 트리맵 | △ | 메인.업무내용 × 용역비 |
| A8 | 시작전 TASK 적체 알림 | △ | 업무TASK.상태=시작전 + 생성일 |
| A5 | 현금흐름 예측 라인 | × P4 | 계약기간 균등 분배 |
| A6 | 지출 구분 월간 추이 | × P4 | 지출내역.구분 × 지출일 |

### 레이어 B — 프로젝트 상세 (관건)
```
┌────────────────────────────────────────────────────┐
│ B1. 헤더: 프로젝트명·발주처·담당팀·진행단계 배지     │
├────────────────────────────────────────────────────┤
│ B2. 라이프사이클 타임라인 (수주→계약기간→완료)       │
│     + 업무TASK 마일스톤 점 오버레이                 │
├────────────────────┬───────────────────────────────┤
│ B3. 진행률 종합     │ B4. 현금흐름 (실측)            │
│   - 프로젝트%       │   - 수금: 회차별 누적 영역     │
│     = TASK% 평균    │   - 지출: 구분별 누적 영역     │
│   - 수금률 도넛     │   - 용역비 라인(목표선)        │
├────────────────────┴───────────────────────────────┤
│ B5. 업무TASK 칸반 (시작전/진행중/완료) + 진행률 바  │
├────────────────────────────────────────────────────┤
│ B6. 지출 구분 도넛 (Top 5 + 기타)  [△ 후순위]       │
└────────────────────────────────────────────────────┘
```
B1~B5 ★ MVP, B6 △ Phase 3 후반

### 레이어 C — 마이페이지
| # | 위젯 | MVP |
|---|---|---|
| C1 | 본인 담당 프로젝트 카드 그리드 | ★ |
| C3 | 본인 업무TASK Today 위젯 | ★ |
| C2 | 마감 임박 타임라인 (D-day) | △ |

> **"진행 중" 정의**: 신규 통합 `업무TASK.상태`로 단순 판정. (기존 예정/완료 분리 워크플로 폐기)

---

## 4. 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| Electron 셸 | Electron + electron-builder | 기존 패턴 |
| 프론트엔드 | Next.js 15, TS, shadcn/ui, Tailwind | `AppShell`, `AuthGuard` 포팅 |
| 백엔드 | FastAPI, SQLAlchemy 2.x, Pydantic v2, JWT | 인증 모듈 이식 |
| Python 매니저 | **uv** | 참조 저장소 동일 |
| DB | SQLite + Alembic | 단일 사용자 환경 |
| 노션 SDK | `notion-client` (공식) | 캐싱 레이어 자체 구현 |
| 차트 — 타임라인/간트 | `vis-timeline` | B2, A2 |
| 차트 — 칸반 | `@dnd-kit/core` + 커스텀 카드 | A1, B5 |
| 차트 — 히트맵/트리맵 | `@nivo/heatmap`, `@nivo/treemap` | A2, A3 |
| 차트 — 도넛/콤보/영역 | `recharts` | B3, B4, A4 |
| 패키징 | PyInstaller + electron-builder NSIS | Windows 우선 |

---

## 5. Phase 별 체크리스트

### Phase 1 — 기반 구축 (1~1.5주)
- [x] PLAN.md 저장 / 본 갱신
- [x] `.claude/rule/error.md` 초기화
- [x] 모노레포 디렉토리 스캐폴딩 (`backend/`, `frontend/`, `electron/`, `scripts/`, `docs/`, `_reference/`)
- [x] 루트 `.gitignore`, `.env.example`, `README.md`
- [x] `DY_MIDAS_PROJECT`를 `_reference/`에 clone
- [x] 노션 메인/보조 DB 스키마 조사
- [x] 신규 `업무TASK` DB 자동 생성 + 양방향 관계 검증
- [ ] `backend/`: `uv venv`, `pyproject.toml`, FastAPI/SQLAlchemy/JWT/notion-client 의존성
- [ ] 인증 모듈 이식 (`auth_middleware.py`, `models/auth.py`, `routers/auth.py`)
- [ ] SQLite + Alembic 초기 마이그레이션 (users 테이블)
- [ ] `frontend/`: `create-next-app` + shadcn 초기화, `AppShell` / `AuthGuard` 포팅
- [ ] `electron/`: `main.js`, `preload.js`, FastAPI sidecar 기동 PoC
- [ ] 로컬 통합 실행 스크립트 (`scripts/dev.ps1`)

### Phase 2 — Notion 통합 (1주)
- [ ] `notion-client` 래퍼 + 응답 캐싱 (`backend/services/notion.py`)
- [ ] 노션 DB ID `.env` 분리, 스키마 검증 스크립트 (`scripts/check_notion_schema.py`)
- [ ] `/api/projects` 조회 (메인 DB → DTO 변환, 담당자 필터)
- [ ] `/api/tasks` CRUD (신규 업무TASK DB)
- [ ] `/api/cashflow` (수금내역 + 지출내역 시계열)
- [ ] Rate limit 처리 (노션 3 req/s, 백오프 + 큐)
- [ ] 변경 이력 로컬 Activity Log 기록
- [ ] (선택) 기존 (예정)/(완료) → 통합 업무TASK 마이그레이션 스크립트

### Phase 3 — UI/UX (1.5~2주)
**MVP 위젯만 구현 (★표시):**
- [ ] **B1~B5** 프로젝트 상세 (헤더·타임라인·진행률·현금흐름·칸반)
- [ ] **A1, A4** 전사 대시보드 (진행단계 칸반·매출 콤보)
- [ ] **C1, C3** 마이페이지 (본인 프로젝트 카드·Today 위젯)
- [ ] 유틸 런처 사이드바
- [ ] 다크 모드 / i18n 한글 우선

**후순위 (Phase 3 후반):**
- [ ] B6 지출 구분 도넛
- [ ] A2, A3, A8, C2

### Phase 4 — 패키징·배포 (0.5~1주)
- [ ] PyInstaller `backend.spec` (불필요 패키지 제외 패턴)
- [ ] electron-builder NSIS 설치파일
- [ ] 자동 업데이트 (electron-updater + GitHub Releases)
- [ ] A5, A6 (현금흐름 예측·지출 추이)
- [ ] 설치/사용 매뉴얼 (`docs/USER_MANUAL.md`)

---

## 6. 보안·운영 고려사항

1. **시크릿 보관**: JWT 시크릿/Notion 토큰은 Electron `safeStorage`(OS 키체인) → 렌더러 노출 금지, IPC 경유
2. **노션 Rate Limit**: 백엔드 캐싱 + debounce, 충돌 감지는 `last_edited_time` 비교
3. **오프라인 대응**: 입력은 로컬 큐 적재 후 온라인 시 동기화 (Phase 2 후반)
4. **에러 로깅**: 발생 에러는 `.claude/rule/error.md`에 기록 (claude.md 지침)
5. **Python 가상환경**: 모든 Python 작업은 `backend/.venv` 내에서만 실행
6. **Windows 한글 인코딩**: 콘솔 cp949 이슈, 파일은 UTF-8(BOM 없이) 통일
7. **노션 통합 권한**: 새 DB는 통합에 자동 공유됨. 신규 DB 생성 시 항상 동일 워크스페이스 사용

---

## 7. 디렉토리 구조 (목표)

```
Task_DY/
├─ PRD.md, PLAN.md, README.md, claude.md
├─ .env.example, .gitignore
├─ .claude/rule/error.md
├─ backend/
│  ├─ .venv/
│  ├─ pyproject.toml
│  ├─ alembic/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ auth_middleware.py
│  │  ├─ db.py
│  │  ├─ models/
│  │  ├─ routers/
│  │  └─ services/{notion.py, cashflow.py}
│  └─ tests/
├─ frontend/
│  ├─ package.json, next.config.ts
│  ├─ app/{login, dashboard, projects/[id], me}/
│  ├─ components/{charts/, AppShell.tsx, AuthGuard.tsx}
│  └─ lib/{api.ts, types.ts}
├─ electron/{package.json, main.js, preload.js}
├─ scripts/{dev.ps1, check_notion_schema.py}
├─ docs/
└─ _reference/DY_MIDAS_PROJECT/
```

---

## 8. 사용자 액션 백로그 (노션 작업)

다음 항목은 사용자가 노션에서 직접 처리해야 합니다:

- [ ] 새 `업무TASK` DB의 **상태** 옵션에 "보류" 추가
- [ ] (선택) 새 `업무TASK` DB에 **Master 롤업** (프로젝트 → Master Project) 추가
- [ ] (Phase 2 후) 메인 프로젝트 DB에서 폐기 대상 relation 정리: `Task`, `업무TASK(완료)`
- [ ] (선택) `Task` DB(`31be...`)를 본 통합에 공유하거나 archive 결정
