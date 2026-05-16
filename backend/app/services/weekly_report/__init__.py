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


# 진행 중으로 간주할 stage (완료/타절/종결/이관 제외)
_ACTIVE_STAGES = frozenset({"진행중", "대기", "보류", "기본설계", "실시설계", "계획설계", "계획검토", "사업승인"})

# 팀별 표 내 정렬 우선순위 (사용자 결정 2026-05-09): 진행중 → 대기 → 보류 → 그 외.
# "기본설계/실시설계" 등 작업단계는 진행중 그룹으로 묶어 가장 위에 표시.
_STAGE_SORT_PRIORITY: dict[str, int] = {
    "진행중": 1,
    "기본설계": 1,
    "실시설계": 1,
    "계획설계": 1,
    "계획검토": 1,
    "사업승인": 1,
    "대기": 2,
    "보류": 3,
}

# 신규 프로젝트로 간주할 stage 휴리스틱
_NEW_STAGES = frozenset({"사업승인", "계획설계", "계획검토", "기본설계"})

# 개인 일정 매트릭스에 표시할 task category.
# "휴가(연차)"는 frontend의 통합 옵션 — 표시 시 duration 기반 연차/반차로 분기.
# "외근/출장/파견"은 task.activity로도 표현 가능하므로 두 source 모두 lookup.
_SCHEDULE_CATEGORIES = frozenset(
    {"외근", "출장", "파견", "휴가", "휴가(연차)", "교육"}
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


# ── helper ──


def _employee_last_week_done(
    db: Session,
    relation_id: str,
    employee: str,
    last_week_start: date,
    last_week_end: date,
    *,
    kind: str = "project",
) -> str:
    """지난주에 해당 직원이 (relation, employee) 조합으로 완료한 task title 합치기.

    relation은 mirror_projects 또는 mirror_sales의 page_id (kind에 따름).
    actual_end_date가 [last_week_start, last_week_end] 범위에 있는 task 기준.
    """
    col = _relation_column(kind)
    rows = (
        db.query(M.MirrorTask.title)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(col.any(relation_id))
        .filter(M.MirrorTask.assignees.any(employee))
        .filter(M.MirrorTask.actual_end_date.isnot(None))
        .filter(M.MirrorTask.actual_end_date >= last_week_start)
        .filter(M.MirrorTask.actual_end_date <= last_week_end)
        .all()
    )
    seen: set[str] = set()
    out: list[str] = []
    for (title,) in rows:
        s = (title or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return " · ".join(out)


def _employee_this_week_plan(
    db: Session,
    relation_id: str,
    employee: str,
    week_start: date,
    week_end: date,
    *,
    kind: str = "project",
) -> str:
    """이번 주 (relation, employee) 조합 — weekly_plan_text 우선, 없으면 활성 task title.

    활성 = 기간이 [week_start, week_end]와 교집합. relation은 project 또는 sale.
    """
    col = _relation_column(kind)
    rows = (
        db.query(M.MirrorTask.title, M.MirrorTask.weekly_plan_text)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(col.any(relation_id))
        .filter(M.MirrorTask.assignees.any(employee))
        .filter(or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= week_end))
        .filter(or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= week_start))
        .all()
    )
    plans: list[str] = []
    titles: list[str] = []
    seen_plans: set[str] = set()
    seen_titles: set[str] = set()
    for title, plan in rows:
        p = (plan or "").strip()
        if p and p not in seen_plans:
            seen_plans.add(p)
            plans.append(p)
        t = (title or "").strip()
        if t and t not in seen_titles:
            seen_titles.add(t)
            titles.append(t)
    # weekly_plan_text가 하나라도 있으면 그것 우선, 없으면 task title fallback
    if plans:
        return " · ".join(plans)
    return " · ".join(titles)


def _project_weekly_plans(
    db: Session, project_id: str, week_start: date, week_end: date
) -> str:
    """해당 주차에 활성인 task들의 금주예정사항 합치기 (중복 제거).

    활성 = (start_date, end_date) 구간이 [week_start, week_end]와 교집합. 두 날짜
    모두 없는 task는 만료 판단 불가하므로 포함 (사용자가 비워두면 항상 표시).
    """
    rows = (
        db.query(M.MirrorTask.weekly_plan_text)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(M.MirrorTask.project_ids.any(project_id))
        .filter(M.MirrorTask.weekly_plan_text != "")
        .filter(or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= week_end))
        .filter(or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= week_start))
        .all()
    )
    seen: set[str] = set()
    out: list[str] = []
    for (text,) in rows:
        s = (text or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return " · ".join(out)


# ── 집계 함수 ──




def aggregate_personal_schedule(
    db: Session, week_start: date, week_end: date
) -> list[PersonalScheduleEntry]:
    """직원×요일 매트릭스.

    포함 조건: task.category가 일정성 카테고리 OR task.activity가 외근/출장/파견.
    (프로젝트 task가 분류='프로젝트'여도 활동이 외근/출장/파견이면 일정에 표시)
    """
    rows = (
        db.query(M.MirrorTask)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(
            or_(
                M.MirrorTask.category.in_(_SCHEDULE_CATEGORIES),
                M.MirrorTask.activity.in_({"외근", "출장", "파견"}),
            )
        )
        # 일정 구간 [start_date, end_date]가 [week_start, week_end]와 교집합
        .filter(or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= week_end))
        .filter(or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= week_start))
        .all()
    )
    # 직원별 team 조회 캐시
    team_by_name: dict[str, str] = {}
    for emp in db.query(Employee.name, Employee.team).all():
        team_by_name[emp.name] = emp.team or ""

    entries: list[PersonalScheduleEntry] = []
    for t in rows:
        label = _normalize_schedule_category(t)
        if not label:
            continue
        # task source 판정 — sales_ids 있으면 영업, project_ids 있으면 프로젝트, 그 외 기타
        if t.sales_ids:
            kind = "sale"
        elif t.project_ids:
            kind = "project"
        else:
            kind = "other"
        for assignee in t.assignees or []:
            entries.append(
                PersonalScheduleEntry(
                    employee_name=assignee,
                    team=team_by_name.get(assignee, ""),
                    category=label,
                    kind=kind,
                    start_date=(t.start_date or week_start).isoformat(),
                    end_date=(t.end_date or t.start_date or week_end).isoformat(),
                    note="",
                    project_code=(t.code or "")[:32],
                )
            )
    return entries


def aggregate_team_projects(
    db: Session, week_start: date, week_end: date
) -> dict[str, list[TeamProjectRow]]:
    """팀별 진행 중 프로젝트 — completed=False, stage가 active.

    Bulk pre-fetch: mirror_tasks를 한 번에 가져와 진행률 평균/금주예정사항을
    메모리에서 계산 (N+1 제거).
    """
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .order_by(M.MirrorProject.code)
        .all()
    )
    # 한 번에 모든 active project의 task fetch — project_id 별로 메모리 그룹.
    task_rows = (
        db.query(
            M.MirrorTask.project_ids,
            M.MirrorTask.progress,
            M.MirrorTask.weekly_plan_text,
            M.MirrorTask.start_date,
            M.MirrorTask.end_date,
        )
        .filter(M.MirrorTask.archived.is_(False))
        .all()
    )
    progress_by_pid: dict[str, list[float]] = defaultdict(list)
    plans_by_pid: dict[str, list[str]] = defaultdict(list)
    for pids, prog, plan, sd, ed in task_rows:
        if not pids:
            continue
        # 이번주와 교집합 task만 weekly_plan 후보
        in_this_week = (sd is None or sd <= week_end) and (
            ed is None or ed >= week_start
        )
        plan_norm = (plan or "").strip()
        for pid in pids:
            if prog is not None:
                progress_by_pid[pid].append(prog)
            if in_this_week and plan_norm:
                plans_by_pid[pid].append(plan_norm)

    client_name_by_id = _client_name_lookup(db)
    by_team: dict[str, list[TeamProjectRow]] = defaultdict(list)
    for r in rows:
        if r.stage and r.stage not in _ACTIVE_STAGES:
            continue
        teams = [t for t in (r.teams or []) if t]
        if not teams:
            continue
        proj = project_from_mirror(r)
        plans = plans_by_pid.get(r.page_id, [])
        # 중복 제거 (순서 유지)
        seen: set[str] = set()
        plans_uniq: list[str] = []
        for p in plans:
            if p not in seen:
                seen.add(p)
                plans_uniq.append(p)
        progs = progress_by_pid.get(r.page_id, [])
        progress = sum(progs) / len(progs) if progs else 0.0
        assignees = list(r.assignees or [])
        row = TeamProjectRow(
            code=r.code,
            name=r.name,
            client=_resolve_client_label(proj, client_name_by_id),
            pm=assignees[0] if assignees else "",
            stage=r.stage,
            progress=progress,
            weekly_plan=" · ".join(plans_uniq),
            note="",
            assignees=assignees,
            end_date=proj.end_date or proj.contract_end,
        )
        for team in teams:
            by_team[team].append(row)

    # 팀 내 정렬: 진행중 → 대기 → 보류 → 그 외 (secondary: code)
    for team_rows in by_team.values():
        team_rows.sort(
            key=lambda x: (_STAGE_SORT_PRIORITY.get(x.stage, 99), x.code)
        )
    return dict(by_team)


def aggregate_team_work(
    db: Session,
    week_start: date,
    week_end: date,
    last_week_start: date,
    last_week_end: date,
) -> dict[str, list[EmployeeWorkRow]]:
    """팀별 (직원 × 프로젝트/영업) 행 단위 업무 현황 — PDF 일지 본래 양식.

    Bulk pre-fetch 방식 (성능 최적화):
    - mirror_tasks를 한 번에 fetch 후 메모리에서 (relation_id, kind, employee)로 bucket
    - mirror_projects/sales/clients/employees도 각 1회 fetch
    - row 후보는 bucket 키 — last_week 또는 this_week가 있는 (relation, employee) 쌍만
      펼쳐서 빈 row 자동 제거

    그룹 기준: 직원의 employees.team. 팀 소속 없는 직원(사장 등) 행 제외.
    팀 내 정렬: 직원 sort_order → 이름 → 단계 우선순위 → relation code.
    """

    # ── 1. 직원 lookup ──
    emp_meta: dict[str, tuple[str, str, int]] = {}
    for emp in db.query(
        Employee.name, Employee.position, Employee.team, Employee.sort_order
    ).all():
        emp_meta[emp.name] = (emp.position or "", emp.team or "", emp.sort_order or 0)

    # ── 2. mirror_projects / mirror_sales meta dict ──
    project_rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .all()
    )
    project_meta: dict[str, M.MirrorProject] = {}
    for r in project_rows:
        if r.stage and r.stage not in _ACTIVE_STAGES:
            continue
        project_meta[r.page_id] = r

    sales_rows = (
        db.query(M.MirrorSales)
        .filter(M.MirrorSales.archived.is_(False))
        .filter(~M.MirrorSales.stage.in_(["수주확정", "실주", "취소", "전환완료", "종결"]))
        .all()
    )
    sales_meta: dict[str, M.MirrorSales] = {s.page_id: s for s in sales_rows}

    client_name_by_id = _client_name_lookup(db)

    # ── 3. 관련 task 한 번에 fetch (지난주 활성/완료 또는 이번주 활성) ──
    tasks = (
        db.query(M.MirrorTask)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(
            or_(
                # 지난주에 완료된 task (actual_end_date 기준)
                and_(
                    M.MirrorTask.actual_end_date.isnot(None),
                    M.MirrorTask.actual_end_date >= last_week_start,
                    M.MirrorTask.actual_end_date <= last_week_end,
                ),
                # 지난주에 활성이었던 task — 기간이 last_week와 교집합 (진행 중 포함)
                and_(
                    or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= last_week_end),
                    or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= last_week_start),
                ),
                # 이번주 활성 task — 기간이 [week_start, week_end]와 교집합
                and_(
                    or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= week_end),
                    or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= week_start),
                ),
            )
        )
        .all()
    )

    # ── 4. (relation_id, kind, employee) bucket ──
    # value: (last_week_titles, this_week_plans, this_week_titles) — 모두 list (중복은 후처리)
    Bucket = dict[tuple[str, str, str], dict[str, list[str]]]
    buckets: Bucket = defaultdict(
        lambda: {"last": [], "this_plans": [], "this_titles": []}
    )
    for t in tasks:
        title = (t.title or "").strip()
        plan = (t.weekly_plan_text or "").strip()
        # 지난주 활성: actual_end가 last_week 안 (완료) OR task 기간이 last_week와 교집합 (진행 중 포함)
        is_last_week = (
            t.actual_end_date is not None
            and last_week_start <= t.actual_end_date <= last_week_end
        ) or (
            (t.start_date is None or t.start_date <= last_week_end)
            and (t.end_date is None or t.end_date >= last_week_start)
        )
        is_this_week = (t.start_date is None or t.start_date <= week_end) and (
            t.end_date is None or t.end_date >= week_start
        )
        relations: list[tuple[str, str]] = []
        for pid in t.project_ids or []:
            relations.append((pid, "project"))
        for sid in t.sales_ids or []:
            relations.append((sid, "sale"))
        if not relations:
            continue
        for assignee in t.assignees or []:
            for rid, kind in relations:
                key = (rid, kind, assignee)
                if is_last_week and title:
                    buckets[key]["last"].append(title)
                if is_this_week:
                    if plan:
                        buckets[key]["this_plans"].append(plan)
                    if title:
                        buckets[key]["this_titles"].append(title)

    # ── 5. row 생성 (빈 row 자동 제거 — bucket에 있는 키만) ──
    def _join_unique(items: list[str]) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for s in items:
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return " · ".join(out)

    by_team: dict[str, list[EmployeeWorkRow]] = defaultdict(list)
    for (rid, kind, assignee), data in buckets.items():
        position, emp_team, _ = emp_meta.get(assignee, ("", "", 0))
        if not emp_team:
            continue
        last = _join_unique(data["last"])
        this_plans = _join_unique(data["this_plans"])
        this_titles = _join_unique(data["this_titles"])
        # weekly_plan_text 우선, 없으면 활성 task title
        this = this_plans or this_titles
        if not last and not this:
            continue
        if kind == "project":
            p = project_meta.get(rid)
            if p is None:
                continue
            proj = project_from_mirror(p)
            client = _resolve_client_label(proj, client_name_by_id)
            row = EmployeeWorkRow(
                employee_name=assignee,
                position=position,
                kind="project",
                source_id=p.page_id,
                project_code=p.code,
                project_name=p.name,
                client=client,
                stage=p.stage,  # 운영 — 정렬용
                phase=proj.phase,  # 작업단계 — UI 표시
                last_week_summary=last,
                this_week_plan=this,
                note="",
            )
        else:  # kind == "sale"
            s = sales_meta.get(rid)
            if s is None:
                continue
            sale_client = ""
            if s.client_id:
                sale_client = (client_name_by_id.get(s.client_id) or "").strip()
            row = EmployeeWorkRow(
                employee_name=assignee,
                position=position,
                kind="sale",
                source_id=s.page_id,
                project_code=s.code,
                project_name=s.name,
                client=sale_client,
                stage=f"영업·{s.stage}" if s.stage else "영업",
                phase="영업",  # 영업은 작업단계 대신 라벨 고정
                last_week_summary=last,
                this_week_plan=this,
                note="",
            )
        by_team[emp_team].append(row)

    # 팀 내 정렬
    for team_rows in by_team.values():
        team_rows.sort(
            key=lambda x: (
                emp_meta.get(x.employee_name, ("", "", 9999))[2],
                x.employee_name,
                _STAGE_SORT_PRIORITY.get(x.stage, 99),
                x.project_code,
            )
        )
    return dict(by_team)


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
