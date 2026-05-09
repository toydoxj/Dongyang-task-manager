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


class TeamMember(BaseModel):
    """팀별 명단 표시용 — 일정 없는 직원도 행이 보이도록."""

    name: str
    position: str = ""
    team: str = ""
    sort_order: int = 0


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
    project_code: str
    project_name: str
    client: str = ""
    stage: str = ""
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


# ── helper ──


def _classify_occupation(team: str, position: str) -> str:
    """employees.team / position을 직종 라벨로 매핑. 미매칭은 '기타'."""
    blob = f"{team} {position}".strip()
    for label, keywords in _OCCUPATION_RULES:
        if any(k in blob for k in keywords):
            return label
    return "기타"


def _kst_range(week_start: date, week_end: date | None = None) -> tuple[datetime, datetime]:
    """[week_start KST 00:00, week_end KST 23:59:59.999999) UTC aware datetime.

    week_end가 None이면 월~금(default = week_start + 4일).
    """
    if week_start.weekday() != 0:
        raise ValueError(f"week_start must be Monday, got {week_start.isoformat()} ({week_start.strftime('%A')})")
    end = week_end if week_end is not None else (week_start + timedelta(days=4))
    start_local = datetime.combine(week_start, time.min, tzinfo=_KST)
    end_local = datetime.combine(end, time.max, tzinfo=_KST)
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


def _client_name_lookup(db: Session) -> dict[str, str]:
    """mirror_clients의 (page_id → name) 딕셔너리 — 발주처 relation 이름 해결.

    노션 프로젝트의 "발주처" relation은 거래처 DB의 page_id를 가리킨다. mirror_dto의
    Project.client_text는 "발주처(임시)" rich_text fallback 컬럼이라 비어있는 경우가
    많고, 정식 발주처는 client_relation_ids → mirror_clients 조회가 필요.
    """
    return {
        c.page_id: c.name or ""
        for c in db.query(M.MirrorClient.page_id, M.MirrorClient.name).all()
    }


def _resolve_client_label(
    proj: "Project", client_name_by_id: dict[str, str]
) -> str:
    """발주처 relation 이름 우선 → 임시 텍스트 fallback."""
    for cid in proj.client_relation_ids:
        name = client_name_by_id.get(cid, "").strip()
        if name:
            return name
    return proj.client_text or ""


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


def _relation_column(kind: str):  # noqa: ANN201 — return SQLAlchemy column
    """kind='project' → MirrorTask.project_ids, 'sale' → sales_ids."""
    if kind == "sale":
        return M.MirrorTask.sales_ids
    return M.MirrorTask.project_ids


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


def aggregate_team_members(
    db: Session, week_end: date
) -> dict[str, list[TeamMember]]:
    """팀별 재직 직원 명단 — 개인일정 grid에서 빈 칸이라도 행이 보이도록.

    재직 = resigned_at IS NULL or resigned_at > week_end (주차 안에 퇴사한 사람도
    표시). 팀별로 sort_order → 이름 정렬. 팀이 비어있는 직원은 제외.
    """
    rows = (
        db.query(Employee)
        .filter(or_(Employee.resigned_at.is_(None), Employee.resigned_at > week_end))
        .all()
    )
    by_team: dict[str, list[TeamMember]] = defaultdict(list)
    for e in rows:
        team = (e.team or "").strip()
        if not team:
            continue
        by_team[team].append(
            TeamMember(
                name=e.name,
                position=e.position or "",
                team=team,
                sort_order=e.sort_order or 0,
            )
        )
    for members in by_team.values():
        members.sort(key=lambda m: (m.sort_order, m.name))
    return dict(by_team)


def aggregate_holidays(
    db: Session, week_start: date, week_end: date
) -> list[HolidayItem]:
    """주차 내 공휴일/사내휴일 — 법정(holidays lib) + notices kind='휴일' 합치기.

    동일 날짜에 두 source가 겹치면 사내(company) 먼저 + 법정 뒤 (frontend에서
    구분 표시 가능). 정렬: 날짜 오름차순.
    """
    items: list[HolidayItem] = []
    # 법정공휴일 — 대체공휴일 포함
    kr = holidays.country_holidays("KR", years=[week_start.year, week_end.year])
    cur = week_start
    while cur <= week_end:
        name = kr.get(cur)
        if name:
            items.append(HolidayItem(date=cur, name=name, source="legal"))
        cur = cur + timedelta(days=1)
    # 사내휴일 — notices kind='휴일' 게시기간 교집합
    company_rows = (
        db.query(Notice)
        .filter(Notice.kind == "휴일")
        .filter(Notice.start_date <= week_end)
        .filter(or_(Notice.end_date.is_(None), Notice.end_date >= week_start))
        .all()
    )
    for n in company_rows:
        # 게시기간이 주차와 교집합인 모든 일자에 등록
        s = max(n.start_date, week_start)
        e = min(n.end_date or week_end, week_end)
        cur = s
        while cur <= e:
            items.append(HolidayItem(date=cur, name=n.title, source="company"))
            cur = cur + timedelta(days=1)
    items.sort(key=lambda h: (h.date, 0 if h.source == "company" else 1))
    return items


def aggregate_notices(
    db: Session, week_start: date, week_end: date
) -> tuple[list[str], list[str]]:
    """게시기간이 주차와 겹치는 공지/교육의 title list 반환 — (notices, education).

    end_date NULL = 무기한 게시. start_date <= week_end and (end_date IS NULL or end_date >= week_start).
    """
    rows = (
        db.query(Notice)
        .filter(Notice.start_date <= week_end)
        .filter(or_(Notice.end_date.is_(None), Notice.end_date >= week_start))
        .order_by(Notice.start_date.desc(), Notice.id.desc())
        .all()
    )
    notices: list[str] = []
    education: list[str] = []
    for r in rows:
        if r.kind == "교육":
            education.append(r.title)
        else:
            notices.append(r.title)
    return notices, education


_TERMINATED_STAGES = frozenset({"종결", "타절"})


def aggregate_completed(
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[CompletedProjectItem]:
    """완료 프로젝트 — 저번주 범위(last_week_start ~ last_week_end) 내 변경.

    기준: last_edited_time이 [last_week_start, last_week_end] 안에 있고
    completed=True 또는 stage in {종결, 타절} (사용자 결정 2026-05-09).
    """
    start_local = datetime.combine(last_week_start, time.min, tzinfo=_KST)
    end_local = datetime.combine(last_week_end, time.max, tzinfo=_KST)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(
            or_(
                M.MirrorProject.completed.is_(True),
                M.MirrorProject.stage.in_(_TERMINATED_STAGES),
            )
        )
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


def aggregate_new_projects(
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[NewProjectItem]:
    """신규 프로젝트 — 저번주 범위(last_week_start ~ last_week_end) 내 등장.

    기준: last_edited_time이 [last_week_start, last_week_end] + 초기 stage 휴리스틱.
    mirror_projects.created_time 부재로 정확도는 last_edited_time에 의존.
    """
    start_local = datetime.combine(last_week_start, time.min, tzinfo=_KST)
    end_local = datetime.combine(last_week_end, time.max, tzinfo=_KST)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
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
    start_utc, end_utc = _kst_range(week_start, week_end)
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
    client_name_by_id = _client_name_lookup(db)
    items: list[SalesItem] = []
    for s in rows:
        # mirror_clients lookup (N+1 제거)
        client_name = client_name_by_id.get(s.client_id, "") if s.client_id else ""
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

    # ── 3. 관련 task 한 번에 fetch (지난주 완료 또는 이번주 활성) ──
    tasks = (
        db.query(M.MirrorTask)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(
            or_(
                # 지난주에 완료
                and_(
                    M.MirrorTask.actual_end_date.isnot(None),
                    M.MirrorTask.actual_end_date >= last_week_start,
                    M.MirrorTask.actual_end_date <= last_week_end,
                ),
                # 이번주 활성 — 기간이 [week_start, week_end]와 교집합
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
        is_last_week = (
            t.actual_end_date is not None
            and last_week_start <= t.actual_end_date <= last_week_end
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
                project_code=p.code,
                project_name=p.name,
                client=client,
                stage=p.stage,
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
                project_code=s.code,
                project_name=s.name,
                client=sale_client,
                stage=f"영업·{s.stage}" if s.stage else "영업",
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
    # 지난주 업무 범위 끝 = 이번주 시작(월요일) 직전 금요일. week_start - 3일.
    # 사용자 사례(2026-05-09): last_week_start=4/27, week_start=5/11이면 last_week_end=5/8.
    # 즉 지난주 업무 = 4/27 ~ 5/8 (지난 2주 평일 cover, 마지막 토일 제외).
    # 완료/신규 cutoff_start = last_week_end + 1 = week_start - 2 (직전 토요일).
    last_week_end = week_start - timedelta(days=3)

    notices, education = aggregate_notices(db, week_start, week_end)
    return WeeklyReport(
        period_start=week_start,
        period_end=week_end,
        headcount=aggregate_headcount(db, week_start, week_end),
        notices=notices,
        education=education,
        seal_log=[],  # 라우터에서 노션 직접 조회로 채움
        completed=aggregate_completed(db, last_week_start, last_week_end),
        new_projects=aggregate_new_projects(db, last_week_start, last_week_end),
        sales=aggregate_sales(db, week_start, week_end),
        personal_schedule=aggregate_personal_schedule(db, week_start, week_end),
        teams=aggregate_team_projects(db, week_start, week_end),
        team_work=aggregate_team_work(
            db, week_start, week_end, last_week_start, last_week_end
        ),
        team_members=aggregate_team_members(db, week_end),
        holidays=aggregate_holidays(db, week_start, week_end),
    )
