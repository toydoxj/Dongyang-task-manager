"""프로젝트 진행단계 자동 동기화 — task의 이번주 활성도로 결정.

기존 `/api/projects/{id}/sync-stage` 엔드포인트(`projects.py`)의 코어 로직을
별도 helper로 추출. task create/update 직후 background로 호출되어
'task는 진행 중인데 프로젝트는 대기' 같은 불일치를 즉시 해소한다.

정책:
- 프로젝트 stage가 '진행중' 또는 '대기' 일 때만 자동 변경 (보류/완료/타절/종결/이관은 수동 설정 존중)
- task 기간이 이번주(월~일)에 걸침 OR 실제 완료일이 이번주 → '진행중', 아니면 '대기'
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import mirror as M
from app.services.notion import NotionService
from app.services.sync import get_sync

logger = logging.getLogger("project.stage_sync")


def this_week_range() -> tuple[date, date]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def has_active_task_this_week(db: Session, project_id: str) -> bool:
    monday, sunday = this_week_range()
    return (
        db.execute(
            select(M.MirrorTask.page_id)
            .where(
                M.MirrorTask.project_ids.contains([project_id]),  # type: ignore[attr-defined]
                M.MirrorTask.archived.is_(False),
                or_(
                    (M.MirrorTask.start_date <= sunday)
                    & (M.MirrorTask.end_date >= monday),
                    (M.MirrorTask.actual_end_date >= monday)
                    & (M.MirrorTask.actual_end_date <= sunday),
                ),
            )
            .limit(1)
        ).first()
        is not None
    )


def _read_desired_stage(project_id: str) -> tuple[str, str] | None:
    """short-lived 세션으로 (current_stage, desired_stage) 결정.

    네트워크 호출 전에 세션을 즉시 닫아 풀 압박 방지. 변경 대상이 아니면 None.
    """
    with SessionLocal() as db:
        proj = db.get(M.MirrorProject, project_id)
        if proj is None or proj.archived:
            return None
        if proj.stage not in ("진행중", "대기"):
            return None
        desired = "진행중" if has_active_task_this_week(db, project_id) else "대기"
        return (proj.stage, desired)


async def reconcile_project_stage(
    notion: NotionService,
    project_id: str,
) -> dict | None:
    """프로젝트 한 건의 stage를 task 활성도 기준으로 재산정.

    반환값: 변경 시 노션이 응답한 갱신 page dict, 변경 없으면 None.
    호출자는 page dict를 그대로 `Project.from_notion_page` 에 넘겨 응답에 사용 가능.

    DB 세션은 _read_desired_stage 안에서만 열고 바로 닫는다 — notion await 동안
    connection pool을 점유하지 않는다.
    """
    decision = _read_desired_stage(project_id)
    if decision is None:
        return None
    current, desired = decision
    if desired == current:
        return None
    updated = await notion.update_page(
        project_id, {"진행단계": {"select": {"name": desired}}}
    )
    get_sync().upsert_page("projects", updated)
    return updated


async def reconcile_projects_for_task(
    notion: NotionService,
    project_ids: list[str],
) -> None:
    """task create/update/PATCH 의 BackgroundTasks 진입점.

    호출자는 (이전 project_ids ∪ 신규 project_ids) 를 넘겨 task가 떠난
    프로젝트도 재산정되도록 한다. 각 프로젝트를 직렬로 처리하며 매번
    helper가 자체 short-lived 세션을 생성 — 풀 점유 없음.
    """
    cleaned = list({pid for pid in project_ids if pid})
    if not cleaned:
        return
    for pid in cleaned:
        try:
            updated = await reconcile_project_stage(notion, pid)
            if updated is not None:
                new_stage = (
                    updated.get("properties", {})
                    .get("진행단계", {})
                    .get("select", {})
                    or {}
                ).get("name", "?")
                logger.info(
                    "project %s stage → %s (task 변경에 의한 자동 동기화)",
                    pid,
                    new_stage,
                )
        except Exception:  # noqa: BLE001
            logger.exception("project stage 재산정 실패 page_id=%s", pid)
