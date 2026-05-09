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

from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import mirror as M
from app.models.employee import Employee
from app.services.mirror_dto import project_from_mirror

_KST = timezone(timedelta(hours=9))

# 직종 분류 휴리스틱 — employees.team 또는 position에서 추출.
# 명확한 매핑 테이블이 없으므로 prefix/keyword 매칭.
_OCCUPATION_RULES = (
    ("구조설계", ("구조1팀", "구조2팀", "구조3팀", "구조4팀", "구조설계")),
    ("안전진단", ("진단팀", "안전진단")),
    ("관리세무", ("관리팀", "세무팀", "관리세무", "총무")),
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
# "외근/출장"은 task.activity로도 표현 가능하므로 두 source 모두 lookup.
_SCHEDULE_CATEGORIES = frozenset(
    {"외근", "출장", "휴가", "휴가(연차)", "교육"}
)


# ── DTO ──


class HeadcountSummary(BaseModel):
    total: int = 0
    by_occupation: dict[str, int] = Field(default_factory=dict)  # 구조설계/안전진단/관리세무
    by_team: dict[str, int] = Field(default_factory=dict)  # 구조1팀/...
    new_this_week: int = 0  # created_at in week
    resigned_this_week: list[str] = Field(default_factory=list)  # 이름 리스트


class SealLogItem(BaseModel):
    project_name: str
    client: str = ""
    seal_type: str = ""  # 구조계산서/구조검토서/...
    status: str = ""  # 1차검토 중/2차검토 중/...
    handler: str = ""  # 현재 단계 처리자
    due_date: str | None = None
    requested_at: str | None = None


class CompletedProjectItem(BaseModel):
    code: str
    name: str
    teams: list[str] = Field(default_factory=list)
    completed_at: str | None = None  # last_edited_time iso


class NewProjectItem(BaseModel):
    code: str
    name: str
    teams: list[str] = Field(default_factory=list)
    stage: str = ""
    started_at: str | None = None


class SalesItem(BaseModel):
    code: str
    category: list[str] = Field(default_factory=list)
    name: str
    client: str = ""
    scale: str = ""  # "44,594.71㎡ / 지하6층, 지상12층"
    estimated_amount: float | None = None
    is_bid: bool = False
    stage: str = ""
    submission_date: str | None = None


class PersonalScheduleEntry(BaseModel):
    """직원의 한 활동 — 표시는 (요일별) cell로 펼침."""

    employee_name: str
    team: str = ""
    category: str  # 외근/출장/연차/반차/파견/교육
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


# ── helper ──


def _classify_occupation(team: str, position: str) -> str:
    """employees.team / position을 직종 라벨로 매핑. 미매칭은 '기타'."""
    blob = f"{team} {position}".strip()
    for label, keywords in _OCCUPATION_RULES:
        if any(k in blob for k in keywords):
            return label
    return "기타"


def _kst_range(week_start: date) -> tuple[datetime, datetime]:
    """월~금 [KST 00:00, 금 23:59:59.999999) 범위. UTC aware datetime 반환."""
    if week_start.weekday() != 0:
        raise ValueError(f"week_start must be Monday, got {week_start.isoformat()} ({week_start.strftime('%A')})")
    start_local = datetime.combine(week_start, time.min, tzinfo=_KST)
    end_local = datetime.combine(week_start + timedelta(days=4), time.max, tzinfo=_KST)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _client_name(props: dict[str, Any]) -> str:
    """프로젝트 properties에서 발주처 이름 휴리스틱 추출 — 임시 텍스트 우선."""
    p = props or {}
    txt = p.get("발주처(임시)", {})
    if isinstance(txt, dict):
        rt = txt.get("rich_text") or []
        if rt and isinstance(rt[0], dict):
            return rt[0].get("plain_text") or rt[0].get("text", {}).get("content") or ""
    return ""


def _scale_text(sale: M.MirrorSales) -> str:
    """영업 row의 규모 표기 — '44,594.71㎡ / 지하6층, 지상12층' 형식."""
    parts: list[str] = []
    if sale.gross_floor_area:
        parts.append(f"{sale.gross_floor_area:,.2f}㎡")
    floors: list[str] = []
    if sale.floors_below:
        floors.append(f"지하{int(sale.floors_below)}층")
    if sale.floors_above:
        floors.append(f"지상{int(sale.floors_above)}층")
    if floors:
        parts.append(", ".join(floors))
    return " / ".join(parts)


def _avg_task_progress(db: Session, project_id: str) -> float:
    """프로젝트에 속한 active task들의 progress 평균. mirror_projects에 진행률 컬럼 부재 대응."""
    rows = (
        db.query(M.MirrorTask.progress)
        .filter(
            M.MirrorTask.archived.is_(False),
            M.MirrorTask.project_ids.any(project_id),
            M.MirrorTask.progress.isnot(None),
        )
        .all()
    )
    vals = [r[0] for r in rows if r[0] is not None]
    return sum(vals) / len(vals) if vals else 0.0


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


def aggregate_headcount(db: Session, week_start: date, week_end: date) -> HeadcountSummary:
    """재직자 수 + 직종/팀별 분포 + 주간 신규/퇴사."""
    # 재직 = resigned_at is None or resigned_at > week_end (퇴사일이 이번 주 이후면 아직 재직)
    rows = (
        db.query(Employee)
        .filter(or_(Employee.resigned_at.is_(None), Employee.resigned_at > week_end))
        .all()
    )
    by_occ: dict[str, int] = defaultdict(int)
    by_team: dict[str, int] = defaultdict(int)
    for e in rows:
        by_occ[_classify_occupation(e.team, e.position)] += 1
        if e.team:
            by_team[e.team] += 1

    # 이번 주 신규 (created_at은 datetime, KST 자정 기준)
    new_count = (
        db.query(Employee)
        .filter(Employee.created_at >= datetime.combine(week_start, time.min))
        .filter(Employee.created_at <= datetime.combine(week_end, time.max))
        .count()
    )

    # 이번 주 퇴사
    resigned_rows = (
        db.query(Employee.name)
        .filter(Employee.resigned_at >= week_start)
        .filter(Employee.resigned_at <= week_end)
        .all()
    )

    return HeadcountSummary(
        total=len(rows),
        by_occupation=dict(by_occ),
        by_team=dict(by_team),
        new_this_week=new_count,
        resigned_this_week=[r[0] for r in resigned_rows],
    )


def aggregate_completed(db: Session, week_start: date, week_end: date) -> list[CompletedProjectItem]:
    """이번 주 완료 (completed=True + last_edited_time in week)."""
    start_utc, end_utc = _kst_range(week_start)
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(True))
        .filter(M.MirrorProject.last_edited_time >= start_utc)
        .filter(M.MirrorProject.last_edited_time <= end_utc)
        .order_by(M.MirrorProject.code)
        .all()
    )
    return [
        CompletedProjectItem(
            code=r.code,
            name=r.name,
            teams=list(r.teams or []),
            completed_at=r.last_edited_time.isoformat() if r.last_edited_time else None,
        )
        for r in rows
    ]


def aggregate_new_projects(db: Session, week_start: date, week_end: date) -> list[NewProjectItem]:
    """이번 주 신규 — mirror_projects.created_time 부재로 last_edited_time + 초기 stage 휴리스틱.

    추후 mirror_projects에 created_time 컬럼 추가하면 정확도 개선 (PR-W Phase 2 후속).
    """
    start_utc, end_utc = _kst_range(week_start)
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .filter(M.MirrorProject.last_edited_time >= start_utc)
        .filter(M.MirrorProject.last_edited_time <= end_utc)
        .filter(M.MirrorProject.stage.in_(_NEW_STAGES))
        .order_by(M.MirrorProject.code)
        .all()
    )
    items: list[NewProjectItem] = []
    for r in rows:
        proj = project_from_mirror(r)
        items.append(
            NewProjectItem(
                code=r.code,
                name=r.name,
                teams=list(r.teams or []),
                stage=r.stage,
                started_at=proj.start_date,
            )
        )
    return items


def aggregate_sales(db: Session, week_start: date, week_end: date) -> list[SalesItem]:
    """이번 주 활성 영업 — 진행 단계가 살아있고 last_edited_time 또는 submission_date in week."""
    start_utc, end_utc = _kst_range(week_start)
    rows = (
        db.query(M.MirrorSales)
        .filter(M.MirrorSales.archived.is_(False))
        # 종결 단계 제외
        .filter(~M.MirrorSales.stage.in_(["수주확정", "실주", "취소", "전환완료"]))
        .filter(
            or_(
                M.MirrorSales.last_edited_time >= start_utc,
                M.MirrorSales.submission_date.between(week_start, week_end),
            )
        )
        .order_by(M.MirrorSales.code)
        .all()
    )
    items: list[SalesItem] = []
    for s in rows:
        # client_id 매핑 — mirror_clients에서 이름 조회
        client_name = ""
        if s.client_id:
            cli = db.get(M.MirrorClient, s.client_id)
            if cli:
                client_name = cli.name
        items.append(
            SalesItem(
                code=s.code,
                category=list(s.category or []),
                name=s.name,
                client=client_name,
                scale=_scale_text(s),
                estimated_amount=s.estimated_amount,
                is_bid=s.is_bid,
                stage=s.stage,
                submission_date=s.submission_date.isoformat() if s.submission_date else None,
            )
        )
    return items


def aggregate_personal_schedule(
    db: Session, week_start: date, week_end: date
) -> list[PersonalScheduleEntry]:
    """직원×요일 매트릭스 — mirror_tasks 중 일정성 category가 주차와 겹치는 row."""
    rows = (
        db.query(M.MirrorTask)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(M.MirrorTask.category.in_(_SCHEDULE_CATEGORIES))
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
        for assignee in t.assignees or []:
            entries.append(
                PersonalScheduleEntry(
                    employee_name=assignee,
                    team=team_by_name.get(assignee, ""),
                    category=label,
                    start_date=(t.start_date or week_start).isoformat(),
                    end_date=(t.end_date or t.start_date or week_end).isoformat(),
                    note="",
                    project_code=(t.code or "")[:32],
                )
            )
    return entries


def _vacation_label(task: M.MirrorTask) -> str:
    """휴가 task를 duration 기반으로 '연차'/'반차' 라벨로 변환.

    노션 task의 "기간" date range — properties JSONB에 시:분 정보 포함.
    duration ≥ 4h면 연차, < 4h면 반차. 사용자 결정(2026-05-09):
    frontend는 단일 "휴가(연차)" 옵션 유지, backend가 표시 시점에 분기.

    파싱 실패 또는 date-only(시간 정보 없음)는 '연차'로 fallback.
    """
    period = (task.properties or {}).get("기간", {}).get("date") or {}
    start_iso = period.get("start") or ""
    end_iso = period.get("end") or ""
    if "T" not in start_iso or not end_iso or "T" not in end_iso:
        return "연차"
    try:
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except ValueError:
        return "연차"
    hours = (end_dt - start_dt).total_seconds() / 3600
    return "연차" if hours >= 4.0 else "반차"


def _normalize_schedule_category(task: M.MirrorTask) -> str:
    """schedule 매트릭스 표시용 category 라벨 정규화.

    - "휴가" / "휴가(연차)" → duration 기반 "연차" 또는 "반차"
    - 그 외 (외근/출장/교육) → 원본 그대로
    - task.category가 비어있으면 task.activity fallback
    """
    cat = task.category or ""
    if cat in ("휴가", "휴가(연차)"):
        return _vacation_label(task)
    if cat:
        return cat
    return task.activity or ""


def aggregate_team_projects(
    db: Session, week_start: date, week_end: date
) -> dict[str, list[TeamProjectRow]]:
    """팀별 진행 중 프로젝트 — completed=False, stage가 active."""
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .order_by(M.MirrorProject.code)
        .all()
    )
    by_team: dict[str, list[TeamProjectRow]] = defaultdict(list)
    for r in rows:
        # active stage 필터 (보류·대기 포함, 완료/타절은 제외)
        if r.stage and r.stage not in _ACTIVE_STAGES:
            # 빈 stage는 그냥 표시
            continue
        proj = project_from_mirror(r)
        progress = _avg_task_progress(db, r.page_id)
        weekly_plan = _project_weekly_plans(db, r.page_id, week_start, week_end)
        # 팀 미지정 프로젝트는 보고서에서 제외 (사용자 결정 2026-05-09).
        teams = [t for t in (r.teams or []) if t]
        if not teams:
            continue
        assignees = list(r.assignees or [])
        row = TeamProjectRow(
            code=r.code,
            name=r.name,
            client=proj.client_text or (proj.client_names[0] if proj.client_names else ""),
            pm=assignees[0] if assignees else "",
            stage=r.stage,
            progress=progress,
            weekly_plan=weekly_plan,
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


# ── main ──


def build_weekly_report(db: Session, week_start: date) -> WeeklyReport:
    """주차 보고서 build. week_start는 월요일 (validation in `_kst_range`)."""
    if week_start.weekday() != 0:
        raise ValueError(f"week_start must be Monday, got {week_start.isoformat()}")
    week_end = week_start + timedelta(days=4)

    return WeeklyReport(
        period_start=week_start,
        period_end=week_end,
        headcount=aggregate_headcount(db, week_start, week_end),
        notices=[],  # PR-W Phase 2.4
        education=[],  # PR-W Phase 2.4
        seal_log=[],  # 라우터에서 노션 직접 조회로 채움
        completed=aggregate_completed(db, week_start, week_end),
        new_projects=aggregate_new_projects(db, week_start, week_end),
        sales=aggregate_sales(db, week_start, week_end),
        personal_schedule=aggregate_personal_schedule(db, week_start, week_end),
        teams=aggregate_team_projects(db, week_start, week_end),
    )
