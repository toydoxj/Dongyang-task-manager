"""대시보드 집계 API (Phase 4-F PR-BJ).

기존 frontend가 list endpoint 5개(/projects /tasks /cashflow/incomes /cashflow/expenses
/seal-requests)를 모두 fetch한 뒤 client-side로 KPI/액션을 계산하던 N+1 패턴을
backend에서 single query로 집계해 응답한다. 1차는 KPI 6개(/summary)만.
액션 5개(/actions)는 PR-BJ-3에서 추가.

KST 경계: `_KST = timezone(+9)`. 모든 "오늘"·"이번 주"·"+N일" 계산은 KST 기준.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.mirror import MirrorCashflow, MirrorProject, MirrorTask
from app.security import get_current_user
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

logger = logging.getLogger("dashboard")

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_KST = timezone(timedelta(hours=9))

# 임계값 — frontend KPICards.tsx와 동일 (USER_MANUAL 컨벤션)
_STALE_DAYS = 90
_DUE_SOON_DAYS = 7
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


def _week_bounds(today: date) -> tuple[date, date]:
    """월요일 시작 (KST). end는 다음 월요일 00:00 (exclusive)."""
    weekday = today.weekday()  # 월=0
    week_start = today - timedelta(days=weekday)
    week_end = week_start + timedelta(days=7)
    return week_start, week_end


_PENDING_SEAL_STATUSES = {"1차검토 중", "2차검토 중"}


async def _count_pending_seals(notion: NotionService) -> int:
    """1차/2차 검토중 status인 날인 페이지 수.

    notion `상태` column type(select vs status)이나 enum값 변경에 영향 안 받도록
    server-side filter는 쓰지 않고 in-memory에서 매칭. WeeklyReport pattern과 동일.
    """
    s = get_settings()
    db_id = s.notion_db_seal_requests
    if not db_id:
        logger.warning("seal pending count: NOTION_DB_SEAL_REQUESTS 미설정")
        return 0
    try:
        pages = await notion.query_all(db_id)
    except Exception:  # noqa: BLE001
        logger.exception("seal pending count 조회 실패")
        return 0

    count = 0
    for p in pages:
        props = p.get("properties", {})
        if not isinstance(props, dict):
            continue
        status_obj = props.get("상태")
        if not isinstance(status_obj, dict):
            continue
        # select 또는 status 둘 다 호환 — 노션은 두 type을 비슷한 shape으로 직렬화
        inner = status_obj.get("select") or status_obj.get("status")
        if not isinstance(inner, dict):
            continue
        name = inner.get("name") or ""
        if name in _PENDING_SEAL_STATUSES:
            count += 1
    logger.info("seal pending count = %d (of %d pages)", count, len(pages))
    return count


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    user: User = Depends(get_current_user),  # noqa: ARG001 — 권한 차등은 PR-BJ-5
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> DashboardSummary:
    """KPI 6개 집계.

    frontend KPICards.tsx와 동일 로직:
    1) 진행중 — projects.stage='진행중'
    2) 장기 정체 — (진행중|대기) AND start_date ≤ today-90d
    3) 마감 임박 TASK — status≠'완료' AND today ≤ end_date ≤ today+7d
    4) 승인 대기 날인 — seal status ∈ {1차검토 중, 2차검토 중}
    5) 이번 주 수금/지출 — cashflow week_start ≤ date < week_end
    6) 최다 부하 팀 — 진행중 프로젝트의 teams[] 카운트 1위
    """
    today = _kst_today()
    stale_cutoff = today - timedelta(days=_STALE_DAYS)
    due_soon_end = today + timedelta(days=_DUE_SOON_DAYS)
    week_start, week_end = _week_bounds(today)

    # 1·2·6 — projects (단일 query)
    proj_rows = db.execute(
        select(MirrorProject.stage, MirrorProject.teams, MirrorProject.properties).where(
            MirrorProject.archived.is_(False)
        )
    ).all()

    in_progress_count = 0
    stalled_count = 0
    team_load: Counter[str] = Counter()
    for stage, teams, props in proj_rows:
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

    # 3 — tasks (status, end_date 인덱스 활용)
    due_soon_tasks = db.execute(
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
    due_soon_tasks_count = len(due_soon_tasks)

    # 5 — cashflow (date 인덱스)
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

    # 4 — seal pending count (PR-BJ-3a). notion status filter로 페이지 수만 카운트.
    # 운영 시 매 호출 notion API hit이라 미세하게 비용. 추후 짧은 TTL cache(BJ-5)
    # 또는 mirror_seal 신설로 개선 여지.
    pending_seal_count = await _count_pending_seals(notion)

    return DashboardSummary(
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
