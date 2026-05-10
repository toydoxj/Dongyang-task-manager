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
    scale: str = ""  # "44,594.71㎡ / 지하6층, 지상12층"
    estimated_amount: float | None = None
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


def aggregate_stage_projects(
    db: Session,
    stages: list[str],
    *,
    exclude_ids: set[str] | None = None,
) -> list[StageProjectItem]:
    """주어진 stage들에 속한 active 프로젝트 list — cutoff 없음.

    컬럼: CODE / 용역명 / 발주처 / 담당팀. 정렬: 담당팀 → CODE.
    is_long_stalled: 대기(stages가 ['대기']에 한정)일 때만 의미 — last_edited_time이
    90일 전 이상이면 True (3개월 이상 활동 없음, 사용자 결정 2026-05-10).
    exclude_ids에 들어있는 page_id는 결과에서 제외.
    """
    excl = exclude_ids or set()
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .filter(M.MirrorProject.stage.in_(stages))
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    long_stall_threshold = datetime.now(timezone.utc) - timedelta(days=90)
    is_waiting_only = stages == ["대기"]
    items: list[StageProjectItem] = []
    for r in rows:
        if r.page_id in excl:
            continue
        if not r.name and not r.code:
            continue
        proj = project_from_mirror(r)
        is_long = (
            is_waiting_only
            and r.last_edited_time is not None
            and r.last_edited_time < long_stall_threshold
        )
        items.append(
            StageProjectItem(
                page_id=r.page_id,
                code=r.code,
                name=r.name,
                client=_resolve_client_label(proj, client_name_by_id),
                teams=list(r.teams or []),
                is_long_stalled=is_long,
            )
        )
    # 정렬: 담당팀 → CODE (팀 미지정은 마지막)
    items.sort(key=lambda x: (x.teams[0] if x.teams else "￿", x.code))
    return items


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
    """완료 프로젝트 — Project.end_date(노션 "완료일")가 저번주 범위 안.

    기준 (사용자 결정 2026-05-09):
    - 완료일(end_date)이 [last_week_start, last_week_end] 안
    - completed=True 또는 stage in {종결, 타절} (운영자가 명시적으로 표시한 것)
    - 완료일 비어있는 row는 제외 (운영자가 노션 "완료일" 입력 안 한 경우 표시 X)
    """
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(
            or_(
                M.MirrorProject.completed.is_(True),
                M.MirrorProject.stage.in_(_TERMINATED_STAGES),
            )
        )
        .order_by(M.MirrorProject.code)
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    range_start_iso = last_week_start.isoformat()
    range_end_iso = last_week_end.isoformat()
    items: list[CompletedProjectItem] = []
    for r in rows:
        proj = project_from_mirror(r)
        ed = (proj.end_date or "")[:10]
        if not ed or not (range_start_iso <= ed <= range_end_iso):
            continue
        label = r.stage if r.stage in _TERMINATED_STAGES else "완료"
        items.append(
            CompletedProjectItem(
                page_id=r.page_id,
                code=r.code,
                name=r.name,
                teams=list(r.teams or []),
                assignees=list(r.assignees or []),
                client=_resolve_client_label(proj, client_name_by_id),
                status_label=label,
                completed_at=proj.end_date,
            )
        )
    return items


def aggregate_new_projects(
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[NewProjectItem]:
    """신규 프로젝트 — 저번주 범위 내 수주된 프로젝트.

    기준: 노션 "시작일"(수주확정일) = Project.start_date가 [last_week_start, last_week_end]
    범위 안. completed=False (이미 완료된 건 제외 — 완료 표에 별도 표시).
    이전 stage 휴리스틱(_NEW_STAGES) 폐기 — mirror_projects.stage가 운영상태(진행중/대기/보류)라
    작업단계 가정이 맞지 않았음 (사용자 피드백 2026-05-09).
    """
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .order_by(M.MirrorProject.code)
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    range_start_iso = last_week_start.isoformat()
    range_end_iso = last_week_end.isoformat()

    # 영업 → 프로젝트 변환된 경우 sales의 규모(연면적/층수) lookup
    sales_by_converted_pid: dict[str, M.MirrorSales] = {
        s.converted_project_id: s
        for s in db.query(M.MirrorSales)
        .filter(M.MirrorSales.archived.is_(False))
        .filter(M.MirrorSales.converted_project_id != "")
        .all()
    }

    items: list[NewProjectItem] = []
    for r in rows:
        proj = project_from_mirror(r)
        sd = (proj.start_date or "")[:10]  # YYYY-MM-DD prefix만
        # 시작일이 저번주 범위 안에 있어야 신규 — 문자열 비교(ISO 형식이라 안전)
        if not sd or not (range_start_iso <= sd <= range_end_iso):
            continue
        sale = sales_by_converted_pid.get(r.page_id)
        scale = _scale_text(sale) if sale else ""
        items.append(
            NewProjectItem(
                page_id=r.page_id,
                code=r.code,
                name=r.name,
                teams=list(r.teams or []),
                assignees=list(r.assignees or []),
                client=_resolve_client_label(proj, client_name_by_id),
                work_types=list(proj.work_types or []),
                scale=scale,
                contract_amount=proj.contract_amount,
                stage=r.stage,
                started_at=proj.start_date,
            )
        )
    return items


def aggregate_sales(
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[SalesItem]:
    """저번주 범위 내 시작된 영업 — 영업시작일(sales_start_date) 기준.

    종결 단계(수주확정/실주/취소/전환완료)는 제외. sales_start_date 비어있으면
    무시 (운영자가 노션에서 입력 안 한 영업).
    """
    rows = (
        db.query(M.MirrorSales)
        .filter(M.MirrorSales.archived.is_(False))
        .filter(~M.MirrorSales.stage.in_(["수주확정", "실주", "취소", "전환완료"]))
        .filter(M.MirrorSales.sales_start_date.isnot(None))
        .filter(M.MirrorSales.sales_start_date >= last_week_start)
        .filter(M.MirrorSales.sales_start_date <= last_week_end)
        .order_by(M.MirrorSales.code)
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    items: list[SalesItem] = []
    for s in rows:
        client_name = client_name_by_id.get(s.client_id, "") if s.client_id else ""
        items.append(
            SalesItem(
                page_id=s.page_id,
                code=s.code,
                category=list(s.category or []),
                name=s.name,
                client=client_name,
                scale=_scale_text(s),
                estimated_amount=s.estimated_amount,
                is_bid=s.is_bid,
                stage=s.stage,
                submission_date=s.submission_date.isoformat() if s.submission_date else None,
                sales_start_date=s.sales_start_date.isoformat() if s.sales_start_date else None,
            )
        )
    return items


def aggregate_personal_schedule(
    db: Session, week_start: date, week_end: date
) -> list[PersonalScheduleEntry]:
    """직원×요일 매트릭스.

    포함 조건: task.category가 일정성 카테고리 OR task.activity가 외근/출장.
    (프로젝트 task가 분류='프로젝트'여도 활동이 외근/출장이면 일정에 표시)
    """
    rows = (
        db.query(M.MirrorTask)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(
            or_(
                M.MirrorTask.category.in_(_SCHEDULE_CATEGORIES),
                M.MirrorTask.activity.in_({"외근", "출장"}),
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


def _vacation_label(task: M.MirrorTask) -> str:
    """휴가 task → 라벨. 우선순위: task 제목 키워드 > duration fallback.

    사용자 요청(2026-05-10): 일률 "연차"가 아니라 제목에 명시된 표현 그대로
    표시. 운영자가 "오전반차" / "오후반차" / "반차" / "연차" 등 자유 입력 가능.
    제목에 키워드가 없으면 duration ≥ 4h '연차', < 4h '반차'로 fallback.
    """
    title = (task.title or "").strip()
    for kw in ("오전반차", "오후반차", "반차", "연차"):
        if kw in title:
            return kw
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


_SCHEDULE_TEXT_CATEGORIES = frozenset(
    {"외근", "출장", "교육", "연차", "반차", "오전반차", "오후반차", "파견", "동행"}
)


def _normalize_schedule_category(task: M.MirrorTask) -> str:
    """schedule 매트릭스 표시용 category 라벨 정규화.

    사용자 결정(2026-05-10): 텍스트는 일정성 카테고리만 표시.
    "프로젝트"/"영업(서비스)" 같은 업무 분류는 적지 않고 activity(외근/출장) 사용.

    - "휴가" / "휴가(연차)" → duration 기반 "연차"(≥4h) 또는 "반차"(<4h)
    - 일정성 카테고리(_SCHEDULE_TEXT_CATEGORIES) → 그대로
    - 그 외(프로젝트/영업/개인업무/사내잡무 등) → task.activity (외근/출장)
    - 둘 다 없으면 빈 문자열 (호출자가 skip)
    """
    cat = task.category or ""
    if cat in ("휴가", "휴가(연차)"):
        return _vacation_label(task)
    if cat in _SCHEDULE_TEXT_CATEGORIES:
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
