"""task 시작일 도래 자동 처리 — 매일 한 번 cron으로 호출.

처리 규칙:
- mirror_tasks에서 status="시작 전" + start_date <= 오늘(KST)인 task 검색
- 노션에 status="진행 중"으로 update + write-through
- 그 task가 프로젝트 task면(project_ids 있으면) 프로젝트의 진행단계도 "진행중"으로
  (이미 "진행중"이면 skip)

호출:
- /api/cron/auto-progress (admin auth) — 외부 cron이 매일 호출
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select

from app.db import SessionLocal
from app.models import mirror as M
from app.services import notion_props as P
from app.services.notion import NotionService
from app.services.project_log import log_assign_change
from app.services.sync import get_sync

logger = logging.getLogger("task.auto_progress")

KST = timezone(timedelta(hours=9))


def _today_kst() -> date:
    return datetime.now(KST).date()


def _list_due_tasks() -> list[M.MirrorTask]:
    """mirror_tasks에서 자동 진행 대상 — '시작 전' + start_date <= 오늘."""
    today = _today_kst()
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(M.MirrorTask)
                .where(M.MirrorTask.archived.is_(False))
                .where(M.MirrorTask.status == "시작 전")
                .where(M.MirrorTask.start_date.is_not(None))
                .where(M.MirrorTask.start_date <= today)
            )
            .scalars()
            .all()
        )
        # detached로 반환 — 호출자는 read-only
        for r in rows:
            db.expunge(r)
        return rows


def _list_projects_to_promote(task_project_ids: set[str]) -> list[M.MirrorProject]:
    """task의 프로젝트들 중 진행단계가 '진행중' 아닌 것만 — 변경 대상."""
    if not task_project_ids:
        return []
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(M.MirrorProject)
                .where(M.MirrorProject.archived.is_(False))
                .where(M.MirrorProject.page_id.in_(task_project_ids))
                .where(M.MirrorProject.stage != "진행중")
            )
            .scalars()
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


async def auto_progress_tasks(notion: NotionService) -> dict[str, int]:
    """일일 자동 처리. 결과 카운트 dict 반환.

    노션 rate limit 0.4초이므로 task 100개면 ~40초. background로 호출 권장.
    """
    due_tasks = _list_due_tasks()
    logger.info("auto-progress 대상 task: %d 건", len(due_tasks))

    task_updated = 0
    task_failed = 0
    project_ids_to_promote: set[str] = set()

    for t in due_tasks:
        try:
            page = await notion.update_page(
                t.page_id, {"상태": {"status": {"name": "진행 중"}}}
            )
            get_sync().upsert_page("tasks", page)
            task_updated += 1
            for pid in t.project_ids or []:
                if pid:
                    project_ids_to_promote.add(pid)
        except Exception:  # noqa: BLE001
            logger.exception("task 자동 진행 실패 page_id=%s", t.page_id)
            task_failed += 1

    # 프로젝트 진행단계 promote — '완료' 체크박스/완료일도 함께 클리어해
    # stage=진행중 + completed=true 같은 부정합 회피.
    # 클리어되는 이전 완료 정보는 assign_log 에 '완료 해제' 이벤트로 기록.
    projects_due = _list_projects_to_promote(project_ids_to_promote)
    project_updated = 0
    project_failed = 0
    for p in projects_due:
        try:
            # 이전 완료 정보 capture — 클리어 후 추적용
            prev_completed = bool(p.completed)
            prev_end_date = (
                P.date_range(p.properties or {}, "완료일")[0] or ""
            )

            page = await notion.update_page(
                p.page_id,
                {
                    "진행단계": {"select": {"name": "진행중"}},
                    "완료": {"checkbox": False},
                    "완료일": {"date": None},
                },
            )
            get_sync().upsert_page("projects", page)
            project_updated += 1

            # 이전이 완료 상태였다면 이력 기록
            if prev_completed or prev_end_date:
                await log_assign_change(
                    notion,
                    project_id=p.page_id,
                    project_name=(
                        f"{p.name or ''} (이전 완료일: {prev_end_date or '미상'})"
                    ),
                    actor="(시스템 자동 promote)",
                    target="(자동)",
                    action="완료 해제",
                )
        except Exception:  # noqa: BLE001
            logger.exception("프로젝트 진행단계 promote 실패 page_id=%s", p.page_id)
            project_failed += 1

    result = {
        "tasks_due": len(due_tasks),
        "tasks_updated": task_updated,
        "tasks_failed": task_failed,
        "projects_promoted": project_updated,
        "projects_failed": project_failed,
    }
    logger.info("auto-progress 완료: %s", result)
    return result
