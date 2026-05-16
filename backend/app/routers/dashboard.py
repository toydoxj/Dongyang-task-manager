"""대시보드 집계 API (Phase 4-F PR-BJ).

기존 frontend가 list endpoint 5개(/projects /tasks /cashflow/incomes /cashflow/expenses
/seal-requests)를 모두 fetch한 뒤 client-side로 KPI/액션을 계산하던 N+1 패턴을
backend에서 single query로 집계해 응답한다. 1차는 KPI 6개(/summary)만.
액션 5개(/actions)는 PR-BJ-3에서 추가.

KST 경계: `_KST = timezone(+9)`. 모든 "오늘"·"이번 주"·"+N일" 계산은 KST 기준.
"""
from __future__ import annotations

import logging
import time
from collections import Counter, OrderedDict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.employee import Employee
from app.models.mirror import MirrorCashflow, MirrorProject, MirrorTask
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

logger = logging.getLogger("dashboard")

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_KST = timezone(timedelta(hours=9))

# 임계값 — frontend KPICards.tsx / PriorityActionsPanel.tsx와 동일 (USER_MANUAL 컨벤션)
_STALE_DAYS = 90  # 장기 정체 프로젝트 (진행중·대기)
_DUE_SOON_DAYS = 7  # KPI '마감 임박 TASK'
_ACTION_DUE_SOON_DAYS = 3  # 액션 '마감 가까운 업무' (KPI보다 짧음)
_STALE_TASK_DAYS = 60  # 액션 '오래 멈춘 TASK' (시작 전)
_RECENT_DAYS = 7  # 최근 변경 프로젝트
_RECENT_TOP_N = 10
_WARNING_TOP_N = 12
_INCOME_ISSUE_RATIO = 0.3  # 수금 지연 (수금합 < 용역비 * ratio)
_CLOSED_STAGES = {"완료", "타절", "종결", "이관"}
_PENDING_SEAL_STATUSES = {"1차검토 중", "2차검토 중"}


class TopTeam(BaseModel):
    name: str
    count: int


class DashboardSummary(BaseModel):
    in_progress_count: int
    stalled_count: int
    due_soon_tasks: int
    pending_seal_count: int
    week_income: int
    week_expense: int
    top_team: Optional[TopTeam] = None
    # 운영 검증용 — backend가 어떤 KST 기준일을 사용했는지 응답에 포함
    today: str  # YYYY-MM-DD (KST)
    week_start: str  # 월요일 (KST)
    week_end: str  # 다음 월요일 (exclusive)


def _kst_today() -> date:
    return datetime.now(_KST).date()


# ── PR-DP: role-scope 차등 ──
# admin / manager → "all"  (전체 조직)
# team_lead      → "team"  (Employee.team 매칭 프로젝트, 미연결 시 self fallback)
# member         → "self"  (Employee.name이 assignees에 포함된 항목만)
# scope_degraded는 운영 로그/디버깅 용 — 응답엔 노출 X.
def _resolve_user_scope(
    db: Session, user: User
) -> tuple[str, str | None, str | None]:
    """(scope, team, employee_name) 반환.

    Codex 권고:
    - team_lead Employee 미연결 → fail-closed self fallback (401/422 대신).
    - member는 User.name 직접 매칭 X — Employee.linked_user_id 경유 canonical name.
    """
    role = (user.role or "").strip()
    if role in ("admin", "manager"):
        return ("all", None, None)
    emp = (
        db.query(Employee.name, Employee.team)
        .filter(Employee.linked_user_id == user.id)
        .first()
    )
    if emp is None:
        # 미연결 사용자 — 권한 좁히기 (Codex 권고). 운영 로그로 추적.
        logger.warning(
            "dashboard scope degraded — user.id=%s role=%s Employee 미연결",
            user.id, role,
        )
        return ("self", None, None)
    emp_name, emp_team = emp
    if role == "team_lead":
        if not emp_team:
            logger.warning(
                "team_lead scope degraded — user.id=%s Employee.team 빈 값",
                user.id,
            )
            return ("self", None, emp_name or None)
        return ("team", emp_team, emp_name or None)
    # member (기타 role 포함)
    return ("self", emp_team or None, emp_name or None)


def _week_bounds(today: date) -> tuple[date, date]:
    """월요일 시작 (KST). end는 다음 월요일 00:00 (exclusive)."""
    weekday = today.weekday()  # 월=0
    week_start = today - timedelta(days=weekday)
    week_end = week_start + timedelta(days=7)
    return week_start, week_end


_PENDING_SEAL_STATUSES = {"1차검토 중", "2차검토 중"}


# ── PR-BJ-5: in-memory TTL cache ─────────────────────────────────────────────
# WeeklyReport pattern과 동일. cache key는 KST 기준일(today) — 자정 넘어가면 자동
# 무효화. 운영 user 액션(프로젝트/날인/cashflow 변경)이 30초 이내 반영되도록 짧게.
# PR-DP: role-scope 분리로 key에 scope tuple 추가. _CACHE_MAX는 active user 수
# 만큼 늘려 thrash 회피 (Codex 권고 64~128).
_CACHE_TTL_SEC = 30
_CACHE_MAX = 64

_summary_cache: OrderedDict[tuple, tuple[float, "DashboardSummary"]] = OrderedDict()
_actions_cache: OrderedDict[tuple, tuple[float, "DashboardActions"]] = OrderedDict()
_insights_cache: OrderedDict[tuple, tuple[float, "DashboardInsights"]] = OrderedDict()


def _cache_get(cache: OrderedDict, key: tuple):
    entry = cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL_SEC:
        cache.pop(key, None)
        return None
    cache.move_to_end(key)
    return value


def _cache_set(cache: OrderedDict, key: tuple, value) -> None:
    cache[key] = (time.monotonic(), value)
    cache.move_to_end(key)
    while len(cache) > _CACHE_MAX:
        cache.popitem(last=False)


# _count_pending_seals — PR-CK에서 제거 (운영 6.4초 병목 원인).
# /api/seal-requests/pending-count endpoint가 동일 로직을 별도로 제공.
# frontend KPICards가 별도 fetch (Sidebar SWR cache 공유).


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    force_refresh: bool = Query(default=False, description="cache 우회 (사용자 새로고침)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> DashboardSummary:
    """KPI 6개 집계 — role-scope 차등 (PR-DP).

    frontend KPICards.tsx와 동일 로직:
    1) 진행중 — projects.stage='진행중'
    2) 장기 정체 — (진행중|대기) AND start_date ≤ today-90d
    3) 마감 임박 TASK — status≠'완료' AND today ≤ end_date ≤ today+7d
    4) 승인 대기 날인 — seal status ∈ {1차검토 중, 2차검토 중}
    5) 이번 주 수금/지출 — cashflow week_start ≤ date < week_end
    6) 최다 부하 팀 — 진행중 프로젝트의 teams[] 카운트 1위

    role-scope:
    - admin/manager: 전체
    - team_lead   : 자기 팀 teams[] 포함 프로젝트/태스크. top_team은 자기 팀.
    - member       : Employee.name이 assignees[] 포함된 항목.
    재무(week_income/expense)는 scope='all'에서만 채움 — 다른 role 0.
    """
    today = _kst_today()
    scope, scope_team, scope_emp = _resolve_user_scope(db, user)
    cache_key = ("summary", today.isoformat(), scope, scope_team or "", scope_emp or "")
    if not force_refresh:
        cached = _cache_get(_summary_cache, cache_key)
        if cached is not None:
            return cached

    stale_cutoff = today - timedelta(days=_STALE_DAYS)
    due_soon_end = today + timedelta(days=_DUE_SOON_DAYS)
    week_start, week_end = _week_bounds(today)

    # 1·2·6 — projects (단일 query, scope는 메모리 필터)
    proj_rows = db.execute(
        select(
            MirrorProject.stage,
            MirrorProject.teams,
            MirrorProject.assignees,
            MirrorProject.properties,
        ).where(MirrorProject.archived.is_(False))
    ).all()

    def _proj_in_scope(teams: list[str] | None, assignees: list[str] | None) -> bool:
        if scope == "all":
            return True
        if scope == "team":
            return bool(scope_team) and scope_team in (teams or [])
        # self
        return bool(scope_emp) and scope_emp in (assignees or [])

    in_progress_count = 0
    stalled_count = 0
    team_load: Counter[str] = Counter()
    for stage, teams, assignees, props in proj_rows:
        if not _proj_in_scope(teams, assignees):
            continue
        if stage == "진행중":
            in_progress_count += 1
            for t in (teams or []):
                if t:
                    team_load[t] += 1
        if stage in ("진행중", "대기"):
            # start_date — Project 테이블이 별도. mirror_projects는 properties JSONB에 보관.
            # 노션 properties의 "수주일" date.start. weekly_report 패턴과 동일.
            sd = _extract_date(props, "수주일") or _extract_date(props, "시작일")
            if sd and sd <= stale_cutoff:
                stalled_count += 1

    top_team_entry = team_load.most_common(1)
    top_team = (
        TopTeam(name=top_team_entry[0][0], count=top_team_entry[0][1])
        if top_team_entry
        else None
    )

    # 3 — tasks (status, end_date 인덱스 활용. scope 적용 시 메모리 필터)
    if scope == "all":
        task_rows = db.execute(
            select(MirrorTask.page_id).where(
                and_(
                    MirrorTask.archived.is_(False),
                    MirrorTask.status != "완료",
                    MirrorTask.end_date.is_not(None),
                    MirrorTask.end_date >= today,
                    MirrorTask.end_date <= due_soon_end,
                )
            )
        ).all()
        due_soon_tasks_count = len(task_rows)
    else:
        task_rows = db.execute(
            select(MirrorTask.assignees, MirrorTask.teams).where(
                and_(
                    MirrorTask.archived.is_(False),
                    MirrorTask.status != "완료",
                    MirrorTask.end_date.is_not(None),
                    MirrorTask.end_date >= today,
                    MirrorTask.end_date <= due_soon_end,
                )
            )
        ).all()
        if scope == "team":
            due_soon_tasks_count = sum(
                1 for _, t_teams in task_rows
                if bool(scope_team) and scope_team in (t_teams or [])
            )
        else:  # self
            due_soon_tasks_count = sum(
                1 for t_assignees, _ in task_rows
                if bool(scope_emp) and scope_emp in (t_assignees or [])
            )

    # 5 — cashflow: admin/manager만. team_lead/member는 재무 정보 노출 X.
    if scope == "all":
        week_income_row = db.execute(
            select(MirrorCashflow.amount).where(
                and_(
                    MirrorCashflow.archived.is_(False),
                    MirrorCashflow.kind == "income",
                    MirrorCashflow.date.is_not(None),
                    MirrorCashflow.date >= week_start,
                    MirrorCashflow.date < week_end,
                )
            )
        ).all()
        week_expense_row = db.execute(
            select(MirrorCashflow.amount).where(
                and_(
                    MirrorCashflow.archived.is_(False),
                    MirrorCashflow.kind == "expense",
                    MirrorCashflow.date.is_not(None),
                    MirrorCashflow.date >= week_start,
                    MirrorCashflow.date < week_end,
                )
            )
        ).all()
        week_income = int(sum(r[0] or 0 for r in week_income_row))
        week_expense = int(sum(r[0] or 0 for r in week_expense_row))
    else:
        week_income = 0
        week_expense = 0

    # 4 — seal pending count: PR-CK에서 summary 응답 경로에서 제거 (운영 6.4초 병목).
    # frontend KPICards가 별도 endpoint(/api/seal-requests/pending-count)로 병렬 fetch.
    # Sidebar의 SWR cache와 공유되어 추가 노션 호출 없음.
    # 본 응답에서는 schema 호환 위해 0으로 보냄. 추후 mirror_seal_requests로 근본 fix.
    pending_seal_count = 0

    summary = DashboardSummary(
        in_progress_count=in_progress_count,
        stalled_count=stalled_count,
        due_soon_tasks=due_soon_tasks_count,
        pending_seal_count=pending_seal_count,
        week_income=week_income,
        week_expense=week_expense,
        top_team=top_team,
        today=today.isoformat(),
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
    )
    _cache_set(_summary_cache, cache_key, summary)
    return summary


def _extract_date(props: dict, key: str) -> Optional[date]:
    """노션 properties JSONB에서 date.start를 ISO 파싱. 없으면 None."""
    if not isinstance(props, dict):
        return None
    obj = props.get(key)
    if not isinstance(obj, dict):
        return None
    inner = obj.get("date")
    if not isinstance(inner, dict):
        return None
    s = inner.get("start")
    if not isinstance(s, str) or not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# ── PR-BJ-3b /actions ─────────────────────────────────────────────────────────


class ActionItem(BaseModel):
    """대시보드 '지금 처리할 것' 패널 단일 항목."""

    count: int
    preview: str = ""  # 가장 시급한 한 건 요약 (이름·제목·팀명 등)


class DashboardActions(BaseModel):
    stalled_projects: ActionItem  # 장기 정체 (90일+)
    overdue_seals: ActionItem  # 제출예정일 경과 + 1차/2차 검토중
    due_soon_tasks: ActionItem  # 오늘 ~ +3일 마감
    overloaded_team: ActionItem  # 진행중 프로젝트 수 1위 팀
    stuck_tasks: ActionItem  # 시작 전 + 60일 이상


async def _collect_overdue_seals(notion: NotionService, today: date) -> ActionItem:
    """1차/2차 검토중 + 제출예정일(due_date)이 today보다 이전. 가장 오래된 것 preview."""
    s = get_settings()
    db_id = s.notion_db_seal_requests
    if not db_id:
        return ActionItem(count=0)
    try:
        pages = await notion.query_all(db_id)
    except Exception:  # noqa: BLE001
        logger.exception("overdue seals 조회 실패")
        return ActionItem(count=0)

    overdue: list[tuple[str, str]] = []  # (due_date, title)
    today_iso = today.isoformat()
    for p in pages:
        props = p.get("properties", {})
        if not isinstance(props, dict):
            continue
        status_obj = props.get("상태")
        if not isinstance(status_obj, dict):
            continue
        inner = status_obj.get("select") or status_obj.get("status")
        if not isinstance(inner, dict):
            continue
        if inner.get("name") not in _PENDING_SEAL_STATUSES:
            continue
        # due_date 노션 property는 "제출예정일" date.start
        due = _extract_date(props, "제출예정일")
        if due is None or due.isoformat() >= today_iso:
            continue
        # title 추출 (날인요청 DB의 첫 title property)
        title = _extract_title(props)
        overdue.append((due.isoformat(), title))
    overdue.sort(key=lambda x: x[0])
    return ActionItem(
        count=len(overdue),
        preview=overdue[0][1] if overdue else "",
    )


def _extract_title(props: dict) -> str:
    """노션 properties에서 첫 title type property를 찾아 plain text 반환."""
    if not isinstance(props, dict):
        return ""
    for v in props.values():
        if not isinstance(v, dict):
            continue
        if v.get("type") != "title":
            continue
        arr = v.get("title") or []
        if isinstance(arr, list) and arr:
            first = arr[0]
            if isinstance(first, dict):
                txt = first.get("plain_text") or ""
                if isinstance(txt, str) and txt:
                    return txt
    return ""


@router.get("/actions", response_model=DashboardActions)
async def get_dashboard_actions(
    force_refresh: bool = Query(default=False, description="cache 우회 (사용자 새로고침)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> DashboardActions:
    """'지금 처리할 것' 패널 5개 항목 집계 — role-scope 차등 (PR-DQ).

    frontend PriorityActionsPanel.tsx와 동일 로직:
    1) 장기 정체 프로젝트 — (진행중|대기) AND start_date ≤ today-90d
    2) 승인 지연 날인 — seal status ∈ pending AND due_date < today
    3) 마감 가까운 업무 — task status≠완료 AND today ≤ end_date ≤ today+3d
    4) 담당 편중 팀 — 진행중 프로젝트 teams[] 카운트 1위 (count = 그 팀의 진행 건수)
    5) 오래 멈춘 TASK — status='시작 전' AND created_time ≤ today-60d

    role-scope:
    - stalled/due_soon/stuck: scope에 따라 teams[] 또는 assignees[] 필터.
    - overloaded_team: 'all'→전체 1위 / 'team'→자기 팀 진행건수 / 'self'→0(의미 X).
    - overdue_seals: 'all'만 notion 호출 (운영 6.4초 병목 회피 — 다른 role은 0).
    """
    today = _kst_today()
    scope, scope_team, scope_emp = _resolve_user_scope(db, user)
    cache_key = ("actions", today.isoformat(), scope, scope_team or "", scope_emp or "")
    if not force_refresh:
        cached = _cache_get(_actions_cache, cache_key)
        if cached is not None:
            return cached

    stale_cutoff = today - timedelta(days=_STALE_DAYS)
    action_due_end = today + timedelta(days=_ACTION_DUE_SOON_DAYS)
    stuck_cutoff = today - timedelta(days=_STALE_TASK_DAYS)

    def _proj_in_scope(teams: list[str] | None, assignees: list[str] | None) -> bool:
        if scope == "all":
            return True
        if scope == "team":
            return bool(scope_team) and scope_team in (teams or [])
        return bool(scope_emp) and scope_emp in (assignees or [])

    # 1·4 — projects (한 번 조회, scope는 메모리 필터)
    proj_rows = db.execute(
        select(
            MirrorProject.page_id,
            MirrorProject.stage,
            MirrorProject.teams,
            MirrorProject.assignees,
            MirrorProject.properties,
            MirrorProject.name,
        ).where(MirrorProject.archived.is_(False))
    ).all()

    stalled_list: list[tuple[str, str]] = []  # (start_date_iso, name)
    team_load: Counter[str] = Counter()
    for _pid, stage, teams, assignees, props, name in proj_rows:
        if not _proj_in_scope(teams, assignees):
            continue
        if stage == "진행중":
            for t in (teams or []):
                if t:
                    team_load[t] += 1
        if stage in ("진행중", "대기"):
            sd = _extract_date(props, "수주일") or _extract_date(props, "시작일")
            if sd and sd <= stale_cutoff:
                stalled_list.append((sd.isoformat(), name or ""))
    stalled_list.sort(key=lambda x: x[0])
    stalled_item = ActionItem(
        count=len(stalled_list),
        preview=stalled_list[0][1] if stalled_list else "",
    )

    # 4 — overloaded_team:
    # 'all' → 전체 1위 팀, 'team' → 자기 팀 진행건수, 'self' → 0(개인 단위 의미 X)
    if scope == "self":
        overloaded_team = ActionItem(count=0)
    else:
        top_team_entry = team_load.most_common(1)
        overloaded_team = (
            ActionItem(
                count=top_team_entry[0][1],
                preview=f"{top_team_entry[0][0]} — 진행중 {top_team_entry[0][1]}건",
            )
            if top_team_entry
            else ActionItem(count=0)
        )

    # 3·5 — task 공통 scope filter helper
    def _task_in_scope(t_assignees: list[str] | None, t_teams: list[str] | None) -> bool:
        if scope == "all":
            return True
        if scope == "team":
            return bool(scope_team) and scope_team in (t_teams or [])
        return bool(scope_emp) and scope_emp in (t_assignees or [])

    # 3 — 마감 임박 TASK (3일 cutoff). scope='all'은 단일 query, 그 외는 메모리 필터
    if scope == "all":
        due_soon_rows = db.execute(
            select(MirrorTask.title, MirrorTask.end_date).where(
                and_(
                    MirrorTask.archived.is_(False),
                    MirrorTask.status != "완료",
                    MirrorTask.end_date.is_not(None),
                    MirrorTask.end_date >= today,
                    MirrorTask.end_date <= action_due_end,
                )
            ).order_by(MirrorTask.end_date.asc())
        ).all()
        due_soon_item = ActionItem(
            count=len(due_soon_rows),
            preview=(due_soon_rows[0][0] or "") if due_soon_rows else "",
        )
    else:
        due_rows = db.execute(
            select(
                MirrorTask.title,
                MirrorTask.end_date,
                MirrorTask.assignees,
                MirrorTask.teams,
            ).where(
                and_(
                    MirrorTask.archived.is_(False),
                    MirrorTask.status != "완료",
                    MirrorTask.end_date.is_not(None),
                    MirrorTask.end_date >= today,
                    MirrorTask.end_date <= action_due_end,
                )
            ).order_by(MirrorTask.end_date.asc())
        ).all()
        filtered = [
            (title, end) for title, end, t_a, t_t in due_rows
            if _task_in_scope(t_a, t_t)
        ]
        due_soon_item = ActionItem(
            count=len(filtered),
            preview=(filtered[0][0] or "") if filtered else "",
        )

    # 5 — 오래 멈춘 TASK
    if scope == "all":
        stuck_rows = db.execute(
            select(MirrorTask.title, MirrorTask.created_time).where(
                and_(
                    MirrorTask.archived.is_(False),
                    MirrorTask.status == "시작 전",
                    MirrorTask.created_time.is_not(None),
                    MirrorTask.created_time <= datetime.combine(
                        stuck_cutoff, datetime.max.time(), tzinfo=_KST
                    ),
                )
            ).order_by(MirrorTask.created_time.asc())
        ).all()
        stuck_item = ActionItem(
            count=len(stuck_rows),
            preview=(stuck_rows[0][0] or "") if stuck_rows else "",
        )
    else:
        stuck_rows_raw = db.execute(
            select(
                MirrorTask.title,
                MirrorTask.created_time,
                MirrorTask.assignees,
                MirrorTask.teams,
            ).where(
                and_(
                    MirrorTask.archived.is_(False),
                    MirrorTask.status == "시작 전",
                    MirrorTask.created_time.is_not(None),
                    MirrorTask.created_time <= datetime.combine(
                        stuck_cutoff, datetime.max.time(), tzinfo=_KST
                    ),
                )
            ).order_by(MirrorTask.created_time.asc())
        ).all()
        stuck_filtered = [
            (title, ct) for title, ct, t_a, t_t in stuck_rows_raw
            if _task_in_scope(t_a, t_t)
        ]
        stuck_item = ActionItem(
            count=len(stuck_filtered),
            preview=(stuck_filtered[0][0] or "") if stuck_filtered else "",
        )

    # 2 — 승인 지연 날인 (notion 호출 — 운영 6.4초 병목. scope='all'만 호출)
    if scope == "all":
        overdue_seal_item = await _collect_overdue_seals(notion, today)
    else:
        overdue_seal_item = ActionItem(count=0)

    actions = DashboardActions(
        stalled_projects=stalled_item,
        overdue_seals=overdue_seal_item,
        due_soon_tasks=due_soon_item,
        overloaded_team=overloaded_team,
        stuck_tasks=stuck_item,
    )
    _cache_set(_actions_cache, cache_key, actions)
    return actions


# ── PR-BJ Phase 4-F 마감: /insights — RecentUpdates + Warnings 두 panel ─────


class RecentUpdate(BaseModel):
    id: str
    code: str
    name: str
    last_edited_time: str  # ISO datetime


class WarningRow(BaseModel):
    id: str
    name: str
    flags: list[str]  # stalled / noAssignee / incomeIssue / overdue


class DashboardInsights(BaseModel):
    recent_updates: list[RecentUpdate]
    warnings: list[WarningRow]


@router.get("/insights", response_model=DashboardInsights)
async def get_dashboard_insights(
    force_refresh: bool = Query(default=False, description="cache 우회"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardInsights:
    """RecentUpdatesPanel + WarningItemsPanel을 single fetch로 통합 — role-scope (PR-DR).

    frontend 컴포넌트와 동일 로직:
    - recent: last_edited_time 7일 이내, 내림차순 Top 10
    - warnings: 미종결 프로젝트 중 stalled/noAssignee/incomeIssue/overdue flag 합산,
      flag 수 많은 순 Top 12

    role-scope (PR-DR): 두 패널 모두 동일 필터.
    - admin/manager: 전체
    - team_lead   : MirrorProject.teams[]에 자기 팀 포함된 프로젝트만
    - member       : MirrorProject.assignees[]에 자기 이름 포함된 프로젝트만
    """
    today = _kst_today()
    scope, scope_team, scope_emp = _resolve_user_scope(db, user)
    cache_key = ("insights", today.isoformat(), scope, scope_team or "", scope_emp or "")
    if not force_refresh:
        cached = _cache_get(_insights_cache, cache_key)
        if cached is not None:
            return cached

    stale_cutoff = today - timedelta(days=_STALE_DAYS)
    today_iso = today.isoformat()
    recent_cutoff_dt = datetime.now(_KST) - timedelta(days=_RECENT_DAYS)

    rows = db.execute(
        select(
            MirrorProject.page_id,
            MirrorProject.code,
            MirrorProject.name,
            MirrorProject.stage,
            MirrorProject.teams,
            MirrorProject.assignees,
            MirrorProject.last_edited_time,
            MirrorProject.properties,
        ).where(MirrorProject.archived.is_(False))
    ).all()

    recent_pool: list[tuple[datetime, str, str, str]] = []  # (dt, id, code, name)
    warning_pool: list[tuple[str, str, list[str]]] = []  # (id, name, flags)

    def _in_scope(teams: list[str] | None, assignees: list[str] | None) -> bool:
        if scope == "all":
            return True
        if scope == "team":
            return bool(scope_team) and scope_team in (teams or [])
        return bool(scope_emp) and scope_emp in (assignees or [])

    for pid, code, name, stage, teams, assignees, last_edited, props in rows:
        if not _in_scope(teams, assignees):
            continue
        # recent
        if last_edited is not None:
            le = last_edited
            if le.tzinfo is None:
                le = le.replace(tzinfo=timezone.utc)
            if le >= recent_cutoff_dt:
                recent_pool.append((le, pid, code or "", name or ""))

        # warnings (종결류 제외)
        if stage in _CLOSED_STAGES:
            continue
        flags: list[str] = []
        # stalled: 진행중·대기 + 시작일 ≥ 90일 이상
        if stage in ("진행중", "대기"):
            sd = _extract_date(props, "수주일") or _extract_date(props, "시작일")
            if sd is not None and sd <= stale_cutoff:
                flags.append("stalled")
        # noAssignee
        if not (assignees or []):
            flags.append("noAssignee")
        # incomeIssue: 계약체결 + 용역비 > 0 + 수금합 < 용역비 * 0.3
        if isinstance(props, dict):
            contract_signed = P.checkbox(props, "계약")
            contract_amount = P.number(props, "용역비(VAT제외)") or 0.0
            collection_total_raw = P.rollup_value(props, "수금합")
            collection_total = (
                float(collection_total_raw)
                if isinstance(collection_total_raw, (int, float))
                else 0.0
            )
            if (
                contract_signed
                and contract_amount > 0
                and collection_total < contract_amount * _INCOME_ISSUE_RATIO
            ):
                flags.append("incomeIssue")
            # overdue: 계약기간 end < today AND 진행중
            _cs, ce = P.date_range(props, "계약기간")
            if ce and ce[:10] < today_iso and stage == "진행중":
                flags.append("overdue")

        if flags:
            warning_pool.append((pid, name or "", flags))

    recent_pool.sort(key=lambda x: x[0], reverse=True)
    recent_updates = [
        RecentUpdate(id=pid, code=c, name=n, last_edited_time=dt.isoformat())
        for dt, pid, c, n in recent_pool[:_RECENT_TOP_N]
    ]

    warning_pool.sort(key=lambda x: len(x[2]), reverse=True)
    warnings = [
        WarningRow(id=pid, name=n, flags=fl)
        for pid, n, fl in warning_pool[:_WARNING_TOP_N]
    ]

    insights = DashboardInsights(
        recent_updates=recent_updates,
        warnings=warnings,
    )
    _cache_set(_insights_cache, cache_key, insights)
    return insights
