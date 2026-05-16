"""주간 프로젝트 스냅샷 생성 (PR-W weekly_snapshot).

매주 일요일 23:59 KST에 호출되어 모든 진행 중 mirror_projects의 진행률·단계·
담당자를 박제. 다음 주 월요일을 `week_start`로 저장하여 다음 보고서가 곧장
참조 가능.

idempotent: 동일 (project_id, week_start) row가 있으면 update.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import SessionLocal
from app.models import mirror as M
from app.models.snapshot import ProjectSnapshot
from app.services.weekly_report.helpers import _avg_task_progress

logger = logging.getLogger("weekly_snapshot")

_KST = timezone(timedelta(hours=9))


def _next_monday(today: date) -> date:
    """오늘 기준 다음 월요일. 오늘이 월요일이면 7일 뒤."""
    days_ahead = 7 - today.weekday()
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def take_snapshot(target_week_start: date | None = None) -> int:
    """모든 진행 중 프로젝트의 스냅샷을 박제. 저장된 row 수 반환.

    target_week_start가 None이면 KST 기준 오늘의 다음 월요일로 자동 결정.
    """
    if target_week_start is None:
        today_kst = datetime.now(_KST).date()
        target_week_start = _next_monday(today_kst)

    saved = 0
    with SessionLocal() as db:
        rows = (
            db.query(M.MirrorProject)
            .filter(M.MirrorProject.archived.is_(False))
            .filter(M.MirrorProject.completed.is_(False))
            .all()
        )
        for r in rows:
            progress = _avg_task_progress(db, r.page_id)
            stmt = pg_insert(ProjectSnapshot).values(
                project_id=r.page_id,
                week_start=target_week_start,
                code=r.code or "",
                name=r.name or "",
                stage=r.stage or "",
                progress=progress,
                assignees=list(r.assignees or []),
                teams=list(r.teams or []),
                extra={},
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_project_snapshots_project_week",
                set_={
                    "code": stmt.excluded.code,
                    "name": stmt.excluded.name,
                    "stage": stmt.excluded.stage,
                    "progress": stmt.excluded.progress,
                    "assignees": stmt.excluded.assignees,
                    "teams": stmt.excluded.teams,
                    "snapshot_at": datetime.now(timezone.utc),
                },
            )
            db.execute(stmt)
            saved += 1
        db.commit()
    logger.info(
        "주간 snapshot 저장: %d개 프로젝트, week_start=%s",
        saved,
        target_week_start.isoformat(),
    )
    return saved


async def weekly_snapshot_job() -> None:
    """APScheduler용 async wrapper. 매주 일요일 23:59 KST 실행."""
    try:
        take_snapshot()
    except Exception:  # noqa: BLE001
        logger.exception("weekly_snapshot 실패")
