"""APScheduler — 5분 incremental sync + 1일 full reconcile."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services.sync import ALL_KINDS, get_sync
from app.services.weekly_snapshot import weekly_snapshot_job
from app.settings import get_settings

logger = logging.getLogger("notion.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _incremental_job() -> None:
    sync = get_sync()
    for kind in ALL_KINDS:
        try:
            count = await sync.sync_kind(kind, full=False)
            if count:
                logger.info("incremental %s: %d 페이지 sync", kind, count)
        except Exception:  # noqa: BLE001
            logger.exception("incremental %s 실패", kind)


async def _full_reconcile_job() -> None:
    sync = get_sync()
    logger.info("full reconcile 시작")
    result = await sync.sync_all(full=True)
    logger.info("full reconcile 완료: %s", result)


def start_scheduler() -> None:
    """FastAPI lifespan에서 호출."""
    global _scheduler
    settings = get_settings()
    if not settings.sync_enabled:
        logger.info("SYNC_ENABLED=false → 스케줄러 비활성")
        return
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(
        _incremental_job,
        trigger=IntervalTrigger(minutes=settings.sync_interval_minutes),
        id="notion-incremental",
        max_instances=1,
        coalesce=True,
        # 시작 직후 1회 실행 (앱 부팅 후 곧바로 데이터 확보)
        next_run_time=None,
    )
    _scheduler.add_job(
        _full_reconcile_job,
        trigger=CronTrigger(hour=3, minute=0),
        id="notion-full-reconcile",
        max_instances=1,
        coalesce=True,
    )
    # 주간 스냅샷 — 매주 일요일 23:59 KST. 다음 월요일을 week_start로 박제.
    _scheduler.add_job(
        weekly_snapshot_job,
        trigger=CronTrigger(day_of_week="sun", hour=23, minute=59),
        id="weekly-snapshot",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "스케줄러 시작: incremental=%d분, full reconcile=daily 03:00, weekly snapshot=sun 23:59",
        settings.sync_interval_minutes,
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    finally:
        _scheduler = None
