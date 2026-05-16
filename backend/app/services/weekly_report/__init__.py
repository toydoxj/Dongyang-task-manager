"""주간 업무일지 데이터 집계 (PR-W Phase 1).

월요일 00:00 ~ 금요일 23:59:59 (Asia/Seoul) 주차 기준으로 mirror 데이터를
집계해 WeeklyReport DTO를 반환. 라우터(`routers/weekly_report.py`)에서 호출.

데이터 부재 항목 (1차 빈 값으로):
- 공지사항/교육일정: 별도 모델 미생성 (PR-W Phase 2.4)
- 금주예정사항: mirror_tasks에 컬럼 부재 (PR-W Phase 2.2)
- 진행률 Δ: project_snapshots 4주 누적 후 활성 (PR-W weekly_snapshot)
- 신규 cutoff: mirror_projects.created_time 부재 → last_edited_time + stage 휴리스틱
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import holidays
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import mirror as M
from app.models.employee import Employee
from app.models.notice import Notice
from app.models.project import Project
from app.services.mirror_dto import project_from_mirror

# PR-DI/2: 작은 helper 10개 + 모듈 상수 3개는 weekly_report/helpers.py로 이동.
# backward compat을 위해 본 모듈에서 re-export — `from weekly_report import _KST` 등.
from app.services.weekly_report.helpers import (  # noqa: E402, F401
    _KST,
    _OCCUPATION_RULES,
    _SCHEDULE_TEXT_CATEGORIES,
    _avg_task_progress,
    _classify_occupation,
    _client_name,
    _client_name_lookup,
    _kst_range,
    _normalize_schedule_category,
    _relation_column,
    _resolve_client_label,
    _scale_text,
    _vacation_label,
)


# ── DTO ──


class HeadcountSummary(BaseModel):
    total: int = 0
    by_occupation: dict[str, int] = Field(default_factory=dict)  # 구조설계/안전진단/관리세무
    by_team: dict[str, int] = Field(default_factory=dict)  # 구조1팀/...
    new_this_week: int = 0  # created_at in week
    resigned_this_week: list[str] = Field(default_factory=list)  # 이름 리스트


class SealLogItem(BaseModel):
    """날인대장 한 행 — 최종 승인된 항목만 (PR-W 사용자 결정 2026-05-09).

    seal_type: 구조계산서 + with_safety_cert인 경우 "계산서(w/안전)"으로 변환.
    """

    project_id: str = ""             # 프로젝트 page_id (상세 link용)
    code: str = ""                   # 프로젝트 CODE
    name: str = ""                   # 용역명
    submission_target: str = ""      # real_source_id 우선, 없으면 발주처
    seal_type: str = ""
    requester: str = ""              # 담당자(요청자)
    approved_at: str | None = None   # 최종 승인일 (admin_handled_at)


class CompletedProjectItem(BaseModel):
    page_id: str = ""  # 프로젝트 상세 link용
    code: str
    name: str
    teams: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)  # 담당자 (PR-W follow-up)
    client: str = ""  # 발주처
    status_label: str = "완료"  # 완료 | 타절 | 종결 — UI 구분 표시용
    completed_at: str | None = None  # last_edited_time iso
    started_at: str | None = None  # 수주확정일 (Project.start_date) — 소요기간 산정 기준
    duration_months: float | None = None  # (end - start)/30, 소수 1자리


class NewProjectItem(BaseModel):
    page_id: str = ""
    code: str
    name: str
    teams: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    client: str = ""
    work_types: list[str] = Field(default_factory=list)  # 업무내용 multi_select
    scale: str = ""  # "44,594.71㎡ / 지하6층, 지상12층" — 영업 lookup
    contract_amount: float | None = None  # 용역비(VAT제외)
    stage: str = ""
    started_at: str | None = None  # 수주일 (start_date)


class SalesItem(BaseModel):
    page_id: str = ""  # 영업 상세 link용
    code: str
    category: list[str] = Field(default_factory=list)
    name: str
    client: str = ""
    scale: str = ""  # "44,594.71㎡ / 지하6층, 지상12층 / 3동"
    estimated_amount: float | None = None
    probability: float | None = None  # 수주확률 0~100
    is_bid: bool = False
    stage: str = ""
    submission_date: str | None = None
    sales_start_date: str | None = None  # 영업시작일 (PR-W)


class PersonalScheduleEntry(BaseModel):
    """직원의 한 활동 — 표시는 (요일별) cell로 펼침.

    kind: task의 source — 'project'(파랑) | 'sale'(초록) | 'other'(회색).
    개인일정 매트릭스에서 셀 색상은 kind 기준, 텍스트는 category 그대로.
    """

    employee_name: str
    team: str = ""
    category: str  # 외근/출장/연차/반차/파견/교육
    kind: str = "other"  # project | sale | other
    start_date: str
    end_date: str
    note: str = ""  # 반차의 오전/오후 등
    project_code: str = ""  # 연결된 프로젝트 (있으면)


class TeamProjectRow(BaseModel):
    code: str
    name: str
    client: str = ""
    pm: str = ""  # assignees[0]
    stage: str = ""
    progress: float = 0.0  # 0~1
    weekly_plan: str = ""  # 금주예정사항 (현재 빈 값)
    note: str = ""
    assignees: list[str] = Field(default_factory=list)  # 담당자 전체
    end_date: str | None = None  # 마감 (계약 end 또는 완료일)


class TeamMember(BaseModel):
    """팀별 명단 표시용 — 일정 없는 직원도 행이 보이도록."""

    name: str
    position: str = ""
    team: str = ""
    sort_order: int = 0


class SuggestionLogItem(BaseModel):
    """건의사항 — 저번주 cycle 등록된 항목 (created_time 기준)."""

    title: str
    author: str = ""
    status: str = "접수"
    created_at: str | None = None


class StageProjectItem(BaseModel):
    """대기/보류 프로젝트 list 한 행. 컬럼: CODE/용역명/발주처/담당팀."""

    page_id: str = ""
    code: str
    name: str
    client: str = ""
    teams: list[str] = Field(default_factory=list)  # 담당팀
    is_long_stalled: bool = False  # 3개월 이상 대기 (대기 프로젝트만 의미)


class HolidayItem(BaseModel):
    """공휴일/사내휴일 한 건. weekly_report 주차 내 일자만 반환."""

    date: date
    name: str
    source: str  # 'legal' (법정공휴일 lib) | 'company' (notices kind=휴일)


class EmployeeWorkRow(BaseModel):
    """직원 × 프로젝트 한 행 — 팀별 업무 현황 표 (PR-W follow-up).

    한 직원이 N개 프로젝트 담당이면 N개 row. 같은 직원의 첫 row만 이름/직책 표시
    하는 처리는 frontend/PDF 책임 (rowspan).
    """

    employee_name: str
    position: str = ""  # 직책 (employees.position)
    kind: str = "project"  # 'project' | 'sale' — frontend 색상 구분 (프로젝트=파랑, 영업=초록)
    source_id: str = ""  # mirror_projects/sales의 page_id — 대기 프로젝트 exclude 등 backend 용
    project_code: str
    project_name: str
    client: str = ""
    stage: str = ""  # 운영 stage (진행중/대기/보류 등) — 정렬용. UI는 phase 표시.
    phase: str = ""  # 작업단계 (계획설계/실시설계 등) — 업무일지의 "진행단계" 컬럼
    last_week_summary: str = ""  # 지난주 actual_end_date 기준 task title 합치기
    this_week_plan: str = ""  # weekly_plan_text 우선, 없으면 활성 task title
    note: str = ""


class WeeklyReport(BaseModel):
    period_start: date  # 월요일
    period_end: date  # 금요일

    headcount: HeadcountSummary
    notices: list[str] = Field(default_factory=list)  # 1차 빈 값
    education: list[str] = Field(default_factory=list)  # 1차 빈 값

    seal_log: list[SealLogItem] = Field(default_factory=list)
    completed: list[CompletedProjectItem] = Field(default_factory=list)
    new_projects: list[NewProjectItem] = Field(default_factory=list)
    sales: list[SalesItem] = Field(default_factory=list)
    personal_schedule: list[PersonalScheduleEntry] = Field(default_factory=list)

    # 팀별 진행 프로젝트 — key 정렬은 라우터/템플릿에서
    teams: dict[str, list[TeamProjectRow]] = Field(default_factory=dict)

    # 팀별 업무 현황 (직원 × 프로젝트 행 단위) — PDF 일지 본래 양식
    team_work: dict[str, list[EmployeeWorkRow]] = Field(default_factory=dict)

    # 팀별 재직 직원 명단 — 개인일정 grid에서 일정 없는 직원도 row 표시용.
    # 키는 employees.team 그대로. 정렬은 sort_order → 이름.
    team_members: dict[str, list[TeamMember]] = Field(default_factory=dict)

    # 주차 내 공휴일/사내휴일 — frontend에서 요일 헤더 색상 + 라벨 표시
    holidays: list[HolidayItem] = Field(default_factory=list)

    # 건의사항 — 저번주 cycle 동안 등록된 글 (라우터에서 노션 직접 조회 후 주입)
    suggestions: list[SuggestionLogItem] = Field(default_factory=list)

    # 대기 / 보류 프로젝트 (stage 기준, cutoff 없음 — 현 시점 active list)
    waiting_projects: list[StageProjectItem] = Field(default_factory=list)
    on_hold_projects: list[StageProjectItem] = Field(default_factory=list)


# ── main ──

# PR-DJ: notices 짝(holidays + 공지/교육) → weekly_report/notices.py 분리.
# PR-DK: 인원 짝(headcount + team_members) → personnel.py / 영업(sales) → sales.py.
# build_weekly_report 직전에 import — partial loading 시점에 model
# (BaseModel) attribute가 확보된 상태 → 순환 import 충돌 없음.
from app.services.weekly_report.notices import (  # noqa: E402
    aggregate_holidays,
    aggregate_notices,
)
from app.services.weekly_report.personnel import (  # noqa: E402
    aggregate_headcount,
    aggregate_team_members,
)
from app.services.weekly_report.sales import aggregate_sales  # noqa: E402
# PR-DL: 프로젝트 도메인(stage_projects + completed + new) → projects.py.
from app.services.weekly_report.projects import (  # noqa: E402
    aggregate_completed,
    aggregate_new_projects,
    aggregate_stage_projects,
)
# PR-DM: 개인 일정(personal_schedule) → personal.py.
from app.services.weekly_report.personal import (  # noqa: E402
    aggregate_personal_schedule,
)
# PR-DN: 팀 도메인(team_projects + team_work + 정렬 상수) → team.py. 4-J 마지막.
from app.services.weekly_report.team import (  # noqa: E402
    aggregate_team_projects,
    aggregate_team_work,
)


def build_weekly_report(
    db: Session,
    week_start: date,
    *,
    week_end: date | None = None,
    last_week_start: date | None = None,
) -> WeeklyReport:
    """주차 보고서 build.

    - week_start: 이번주 시작일 (월요일 권장 — validation in `_kst_range`)
    - week_end: 이번주 종료일 (default: week_start + 4일 = 금요일)
    - last_week_start: 지난주 시작일 (default: week_start - 7일).
      last_week_end는 동일 길이로 자동 계산 — last_week_start + (week_end - week_start).
    """
    if week_start.weekday() != 0:
        raise ValueError(f"week_start must be Monday, got {week_start.isoformat()}")
    if week_end is None:
        week_end = week_start + timedelta(days=4)
    if week_end < week_start:
        raise ValueError(
            f"week_end({week_end}) must be >= week_start({week_start})"
        )
    if last_week_start is None:
        last_week_start = week_start - timedelta(days=7)
    # 지난주 범위 끝 = 이번주 시작(월요일) 직전 일요일. week_start - 1일.
    # 사용자 결정(2026-05-09): 토/일 시작 데이터 누락 방지 — week_start - 3 → -1.
    # 사례: last_week_start=4/27, week_start=5/11이면 last_week_end=5/10 (월~일 14일 cover).
    last_week_end = week_start - timedelta(days=1)

    notices, education = aggregate_notices(db, week_start, week_end)
    team_work = aggregate_team_work(
        db, week_start, week_end, last_week_start, last_week_end
    )
    # 팀별 업무 현황에 이미 표시된 프로젝트 page_id set (kind='project'만).
    # 사용자 결정(2026-05-09): "대기 프로젝트"는 팀별 업무에 안 올라온 것만.
    team_work_project_ids: set[str] = {
        r.source_id
        for rows in team_work.values()
        for r in rows
        if r.kind == "project" and r.source_id
    }
    return WeeklyReport(
        period_start=week_start,
        period_end=week_end,
        headcount=aggregate_headcount(db, week_start, week_end),
        notices=notices,
        education=education,
        seal_log=[],  # 라우터에서 노션 직접 조회로 채움
        completed=aggregate_completed(db, last_week_start, last_week_end),
        new_projects=aggregate_new_projects(db, last_week_start, last_week_end),
        sales=aggregate_sales(db, last_week_start, last_week_end),
        personal_schedule=aggregate_personal_schedule(db, week_start, week_end),
        teams=aggregate_team_projects(db, week_start, week_end),
        team_work=team_work,
        team_members=aggregate_team_members(db, week_end),
        holidays=aggregate_holidays(db, week_start, week_end),
        # 대기 프로젝트: 팀별 업무에 없는 [진행중, 대기] 프로젝트
        waiting_projects=aggregate_stage_projects(
            db, ["진행중", "대기"], exclude_ids=team_work_project_ids
        ),
        on_hold_projects=aggregate_stage_projects(db, ["보류"]),
        # suggestions는 라우터에서 노션 직접 조회 후 주입
    )
