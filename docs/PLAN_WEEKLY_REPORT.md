# 주간 업무일지 통합 계획 (Weekly Report Integration Plan)

> 대상 리포지토리: `toydoxj/Dongyang-task-manager`
> 기준 문서: `2026_04_27_업무일지.pdf` (2026년 4월 27일 ~ 5월 1일)
> 작성일: 2026-05-04

---

## 1. 목적

매주 수기로 작성되는 4페이지짜리 PDF 업무일지를 **task-manager 앱이 자동 생성·관리**하도록 통합한다. 업무일지에 있는 정보가 이미 시스템에 존재하는지를 매핑하고, **누락된 데이터 도메인**을 식별하여 모델·라우터·UI 단계의 작업을 정의한다.

목표는 두 단계로 분리됨:

| 단계 | 목표 | 효과 |
|---|---|---|
| **1단계 (Read-only)** | 현재 시스템 데이터를 조립하여 PDF/HTML 형식의 주간업무일지 자동 출력 | 수기 작성 시간 제거, 데이터 일관성 확보 |
| **2단계 (Read-write)** | 업무일지에만 존재하던 도메인(영업, 날인대장, 개인일정 등) 신규 모델링 + 입력 UI | 단일 진실 원천 확장, 노션·앱·일지 완전 동기화 |

---

## 2. 업무일지 ↔ 시스템 매핑 분석

### 2.1 페이지별 섹션 분해

| 섹션 | 페이지 | 현재 시스템 매핑 상태 | 비고 |
|---|---|---|---|
| 인원현황 (총원/직종별) | 1 | **존재** — `employees` 테이블 집계 | `resigned_at IS NULL` count |
| 주요 공지사항 | 1 | **부재** | 신규 모델 필요 |
| 개인 일정 (월~금 매트릭스) | 1 | **부분 존재** — `mirror_tasks.activity` (외근/출장) 일부 커버, 연차/반차/파견/퇴사는 부재 | Task `category=휴가`로는 표현 불완전 |
| 날인대장 | 1 | **부분 존재** — `seal_requests` 라우터 존재, 단 출력 컬럼(계산서/안전확인서/검토서/보고서/기타)과 매핑 검증 필요 | 컬럼 매핑만 추가 |
| 완료 (구조1/2/3/4팀, 진단팀) | 1 | **존재** — `mirror_projects.stage='완료'` + `last_edited_time` | 주간 cutoff 필터 |
| 영업 (영26-XXX) | 1 | **부재** | 신규 도메인 — 견적·입찰 단계 |
| 신규 (구조설계/현장지원/구조검토 등) | 1 | **부분 존재** — `mirror_projects.created_time` 기반 추출 가능 | 분류 컬럼 매핑 |
| 교육 일정 | 1 | **부재** | 신규 모델 필요 (소규모) |
| 팀별 진행 프로젝트 (2~4페이지) | 2~4 | **존재** — `mirror_projects` + `assignees`/`teams` + `progress` | 팀 필터 + ■ 마크는 `assignees` 매칭으로 도출 |
| 금주예정사항 | 2~4 | **부재** | 신규 컬럼/노션 필드 필요 |

### 2.2 결론

**대부분의 데이터가 노션 미러에 이미 있다.** 핵심 갭은 다음 4개 도메인이다:

1. **영업 파이프라인** (영26-XXX 코드 체계 — 견적가/입찰 여부 추적)
2. **금주예정사항** (프로젝트별 자유텍스트 — 노션 컬럼 추가로 해결 가능)
3. **개인 주간 일정** (요일×직원 매트릭스 — 연차/반차/파견/외근/퇴사)
4. **주요 공지사항 / 교육 일정** (작은 메타 도메인)

---

## 3. 데이터 모델 변경안

### 3.1 신규 노션 DB / 미러 테이블

#### A) `NOTION_DB_SALES` — 영업 파이프라인

업무일지의 "영업" 표 (영26-147 ~ 영26-153 등)에 해당.

| 노션 컬럼 | 타입 | 미러 컬럼 (`mirror_sales`) | 설명 |
|---|---|---|---|
| 영업번호 | title | `code` (text, indexed) | 영26-147 형식 |
| 내용 | select | `category` (text) | 정밀진단/정밀점검/정기점검/내진평가/증축설계/구조설계/설계변경 |
| PROJECT | rich_text | `name` (text) | 프로젝트명 |
| 발주처 | rich_text/relation | `client_text`, `client_relation_id` | |
| 규모 | rich_text | `scale` (text) | "44,594.71㎡ / 지하6층, 지상12층" 형식 |
| 견적가 | number | `estimated_amount` (numeric) | KRW |
| 입찰여부 | checkbox | `is_bid` (bool) | 입찰 여부 표시 |
| 단계 | select | `stage` (text) | 견적준비/입찰대기/낙찰/실주 |
| 등록일 | date | `created_at_notion` | |
| 전환된 프로젝트 | relation → 프로젝트DB | `converted_project_id` | 수주 시 메인 DB로 승격 |

**라우팅**: `/api/sales` (CRUD), `/api/sales/{id}/convert` (수주 시 `mirror_projects`로 승격).

#### B) `NOTION_DB_PERSONAL_SCHEDULE` — 개인 주간 일정 (또는 Task 확장)

**선택지 2개 — 권장은 (B-1)**:

**(B-1) 권장: 기존 `mirror_tasks` 활용 + `category` 확장**

현재 `category` 값: `프로젝트|개인업무|사내잡무|교육|서비스|외근|출장|휴가`

추가 필요 값: **`연차`(휴가 분리), `반차`(오전/오후), `파견`, `퇴사`**

업무일지의 표는 결국 "직원 × 날짜 × 활동분류"의 pivot 테이블이므로, **task의 `category` + `assignees` + `start_date~end_date`로 완전히 표현 가능**하다.

마이그레이션:
- `category` select에 `연차/반차/파견/퇴사` 추가 (`notion_schema.py`의 자동 보강 로직 활용)
- 반차의 경우 추가 필드 필요 → `note`에 "오전반차"/"오후반차" 텍스트로 충분

**(B-2) 대안: 별도 모델 (지양)** — 데이터 중복 우려, `task_calendar_sync`와 충돌

#### C) `NOTION_DB_NOTICES` — 주요 공지사항 + 교육 일정

| 컬럼 | 타입 | 설명 |
|---|---|---|
| 제목 | title | "구조설계 업무용 폴더 체계 변경 내용 확인" |
| 분류 | select | `공지사항\|교육일정` |
| 게시기간 | date range | 시작~종료 (해당 주차 표시 여부 판단) |
| 본문 | rich_text | |
| 작성자 | people | |

**라우팅**: `/api/notices` (admin write, all read).

### 3.2 기존 모델 확장

#### `mirror_tasks` 컬럼 추가

| 신규 컬럼 | 타입 | 노션 매핑 | 용도 |
|---|---|---|---|
| `weekly_plan_text` | text | "금주예정사항" rich_text | 업무일지의 금주예정사항 컬럼 직접 매핑 |

> 기존 `note` 컬럼은 영구 비고 용도이므로, **주간 단위로 쓰고 지우는 "이번 주 할 일"은 별도 컬럼이 적절**하다. 대안으로는 노션의 별도 weekly_plan DB를 두고 task에 relation을 거는 방식도 있으나, 단일 텍스트 컬럼이 운영 부담이 가장 낮다.

#### `mirror_projects` 컬럼 추가

| 신규 컬럼 | 타입 | 용도 |
|---|---|---|
| `report_kind` | text | 날인대장의 5개 컬럼 표시용 (계산서/안전확인서/검토서/보고서/기타). multi-select |

> 만약 `seal_requests`에 이미 종류 컬럼이 있으면 거기서 집계만 하면 됨 — 미러링 컬럼 추가 불필요.

---

## 4. 구현 계획 (단계별)

### Phase 1: 주간 업무일지 자동 생성 (Read-only)

> **선결 조건**: 현재 시스템 데이터만으로 약 70~80%의 업무일지를 재현할 수 있음. 우선 이 부분만 출력하여 가치를 확인.

#### 1.1 백엔드 — 주간 보고서 집계 서비스

**신규 파일**: `backend/app/services/weekly_report.py`

```python
"""주간 업무일지 데이터 집계.

기준 주차의 월요일 00:00 ~ 금요일 23:59:59 (Asia/Seoul) 범위로
- mirror_projects (팀별 진행/완료/신규)
- mirror_tasks (담당자별 ■ 마크)
- seal_requests (날인대장)
- employees (인원현황)
를 합산하여 weekly_report DTO를 반환.
"""
from datetime import date, timedelta
from pydantic import BaseModel

class WeeklyReportRequest(BaseModel):
    week_start: date  # Monday

class TeamRow(BaseModel):
    code: str
    project_name: str
    client: str
    pm: str
    stage: str
    progress: float
    weekly_plan: str
    note: str
    assignee_marks: dict[str, bool]  # {"서동균": True, ...}

class WeeklyReport(BaseModel):
    period: tuple[date, date]
    headcount: dict[str, int]  # {"total": 32, "구조설계": 22, ...}
    notices: list[str]
    personal_schedule: list[dict]  # 직원×요일 매트릭스
    seal_log: list[dict]
    completed: list[dict]
    sales: list[dict]
    new_projects: list[dict]
    education: list[dict]
    teams: dict[str, list[TeamRow]]  # {"구조1팀": [...], ...}
```

**신규 라우터**: `backend/app/routers/weekly_report.py`

| 엔드포인트 | 권한 | 설명 |
|---|---|---|
| `GET /api/weekly-report?week_start=2026-04-27` | member | 집계 JSON |
| `GET /api/weekly-report.pdf?week_start=...` | member | PDF 다운로드 |
| `GET /api/weekly-report.xlsx?week_start=...` | member | Excel 다운로드 (현재 양식 그대로) |

#### 1.2 프론트엔드 — 주간 보고서 페이지

**신규 페이지**: `frontend/app/weekly-report/page.tsx`

- 주차 선택 (date picker — 월요일만 선택 가능)
- 미리보기 (현재 PDF 양식 그대로 HTML 렌더)
- "PDF 다운로드" / "Excel 다운로드" / "Notion 페이지 생성" 버튼
- admin 권한자만 "전체 직원에게 발송" 버튼

#### 1.3 출력 양식 — `xlsx` 우선

현재 PDF가 Excel에서 출력된 양식임이 명확하므로 (셀 병합 패턴), **`openpyxl`로 동일 양식의 xlsx 생성을 1차 출력으로** 한다. PDF 출력은 xlsx → PDF 변환(LibreOffice headless) 또는 추후 `reportlab` 직접 작성.

---

### Phase 2: 누락 도메인 모델링 (Read-write)

#### 2.1 영업 파이프라인 (`/api/sales`)

| 작업 | 파일 |
|---|---|
| 노션 DB 생성 (수동) + `.env`에 `NOTION_DB_SALES` 추가 | — |
| `models/sale.py` (Pydantic + ORM `mirror_sales`) | 신규 |
| `services/notion_schema.py`에 sales DB 스키마 자동 보강 추가 | 수정 |
| `services/sync.py`에 sales sync 추가 | 수정 |
| `routers/sales.py` (CRUD + convert) | 신규 |
| Alembic 마이그레이션 (`mirror_sales` 테이블) | 신규 |
| 프론트 `app/sales/page.tsx` + 모달 | 신규 |

**핵심 로직 — 수주 전환**:

```python
# routers/sales.py
@router.post("/{sale_id}/convert")
async def convert_to_project(sale_id: str, ...):
    """영업 → 메인 프로젝트 DB 페이지 생성 + sale.converted_project_id 채움."""
    # 1. sale 조회
    # 2. ProjectCreateRequest로 변환 (code, name, client, contract_amount=estimated_amount 등)
    # 3. notion.create_project 호출 (기존 라우터 재사용)
    # 4. sale.converted_project_id 업데이트
```

#### 2.2 금주예정사항

| 작업 | 파일 |
|---|---|
| 노션 `업무TASK` DB에 `금주예정사항` rich_text 컬럼 추가 (자동 보강 활용) | `services/notion_schema.py` |
| `models/task.py`에 `weekly_plan_text` 필드 추가 | 수정 |
| Alembic 마이그레이션 (`mirror_tasks.weekly_plan_text`) | 신규 |
| `TaskEditModal.tsx`에 입력란 추가 | 수정 |
| **자동화 옵션**: 매주 월요일 06:00 cron — 지난 주 `weekly_plan_text` 비어있는 항목을 일괄 비움 (선택) | `services/scheduler.py` |

#### 2.3 개인 주간 일정 — Task category 확장

| 작업 | 파일 |
|---|---|
| `notion_schema.py`의 task `분류` select options에 `연차/반차/파견` 추가 | 수정 |
| `models/task.py`의 `category` 주석에 새 값 명시 | 수정 |
| `frontend/lib/types.ts`의 category enum 확장 | 수정 |
| `TaskCreateModal.tsx` — 분류=반차 선택 시 오전/오후 토글 표시 | 수정 |
| 주간 보고서 집계 시 직원×요일 매트릭스 생성 로직 | `weekly_report.py` |

> **`퇴사`는 task의 category가 아닌 `Employee.resigned_at` 필드로 처리해야 한다.** 업무일지에는 "퇴사" 표시가 들어가는데, 이는 별도 정책으로 — 해당 주에 `resigned_at`이 떨어지는 직원은 자동으로 매트릭스에 "퇴사" 표시.

#### 2.4 공지사항 + 교육 일정

소규모 도메인이므로 노션 DB를 별도로 만들지 않고 **`services/sso_works_bot.py`의 공지 메커니즘과 통합**하거나, **단일 mirror 테이블 `notices`**를 만들어 처리. 의사결정 필요 — 권장은 후자(단순함, 검색 가능).

---

### Phase 3: 운영 자동화

#### 3.1 매주 월요일 자동 생성

`services/scheduler.py`에 cron job 추가:

```python
# 매주 월요일 08:00 KST: 지난 주 보고서 자동 생성 + admin에게 Bot 알림
@scheduler.scheduled_job("cron", day_of_week="mon", hour=8, minute=0, timezone="Asia/Seoul")
async def generate_weekly_report_job():
    last_monday = today - timedelta(days=7)  # 지난 주 월요일
    report = await weekly_report.build(last_monday)
    pdf_path = await render_pdf(report)
    # NAVER WORKS Drive 업로드 + Bot 알림 (sso_drive + sso_works_bot 활용)
```

#### 3.2 PM 입력 알림 — 매주 금요일 16:00

각 PM에게 "다음 주 금주예정사항을 입력하세요" Bot 알림. 입력 안된 task가 있으면 목록 첨부.

---

## 5. 마이그레이션 우선순위 및 일정 추정

| 우선순위 | 작업 | 난이도 | 효과 | 추정 |
|---|---|---|---|---|
| **P0** | Phase 1.1 — `weekly_report.py` 서비스 + JSON 라우터 | 중 | 즉시 가치 | 1~2일 |
| **P0** | Phase 1.3 — xlsx 출력 (현재 양식 재현) | 중상 | 시각적 검증 가능 | 2~3일 |
| **P1** | Phase 1.2 — 프론트 미리보기 페이지 | 중 | UX 완성 | 1~2일 |
| **P1** | Phase 2.2 — 금주예정사항 컬럼 추가 | 하 | 일지 핵심 컬럼 채움 | 0.5일 |
| **P1** | Phase 2.3 — 분류 옵션 확장 (연차/반차/파견) | 하 | 개인일정 매트릭스 가능 | 0.5일 |
| **P2** | Phase 2.1 — 영업 파이프라인 신규 도메인 | 상 | 신규 도메인 모델링 | 3~5일 |
| **P2** | Phase 2.4 — 공지/교육 도메인 | 중 | 일지 완전성 | 1~2일 |
| **P3** | Phase 3.1 — 자동 생성 cron + Bot 발송 | 중 | 운영 자동화 | 1일 |
| **P3** | Phase 3.2 — PM 입력 알림 | 하 | 데이터 품질 | 0.5일 |

**총 추정**: 10~17일 (단독 개발 기준).

**권장 진행 순서**: P0 → P1 → 운영 검증 (2주) → P2 → P3.

---

## 6. 리스크 및 검토사항

| 리스크 | 대응 |
|---|---|
| 업무일지 양식이 부서별 미세하게 다름 (예: 진단팀 컬럼 구성) | xlsx 템플릿을 부서별로 분기. `weekly_report.py`에서 팀별 별도 builder. |
| 노션 DB ID 추가 시 schema sync 부하 증가 | 신규 DB는 sync 주기 분리 (영업 DB는 15분, 메인은 5분 유지) |
| 개인 일정의 "퇴사" 표시가 task category 확장과 의미적으로 안 맞음 | `Employee.resigned_at` 기반 별도 처리 — 위 2.3 참조 |
| 금주예정사항 자유텍스트가 길어지면 표 셀 넘침 | xlsx 셀 자동 줄바꿈 + 최대 길이 200자 권장 (UI hint) |
| **인증 부정 일관성 (CR 결과: `_can_access` 갭)** | 신규 라우터(`weekly_report`, `sales`, `notices`) 작성 시 동일 권한 체크 패턴 강제. **신규 라우터 작성 전에 `_can_access` 인가 갭부터 수정 권장.** |

---

## 7. 결정 필요 사항 (의사결정 요청)

다음 항목은 진행 전 의사결정이 필요하다:

1. **공지사항/교육 일정** — 노션 DB 분리 vs 단일 `notices` 테이블? (권장: 단일 테이블)
2. **금주예정사항** — task 컬럼 vs 별도 weekly_plan DB? (권장: task 컬럼)
3. **PDF vs xlsx** 우선 출력? (권장: xlsx 우선 — 양식 재현 용이)
4. **영업 파이프라인** — 즉시 진행 vs 후행? (권장: P2로 후행, Phase 1 운영 안정화 후)
5. **자동 생성 시점** — 매주 월요일 08:00 vs 금요일 17:00? (권장: 월요일 — 직전 주 마감 후)

---

## 8. 다음 액션

선결 조건이 정리되면 다음 순서로 작업 가능:

1. 위 결정 필요 사항(7항)에 대한 답변 정리
2. `feature/weekly-report` 브랜치 생성
3. P0 작업부터 착수 (`backend/app/services/weekly_report.py` 스켈레톤)
4. 한 주차 데이터로 xlsx 출력 검증 → 실제 업무일지와 diff 확인
5. 검증 후 P1 진행
