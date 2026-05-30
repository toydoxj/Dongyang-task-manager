"""/api/admin/sync — admin 강제 트리거 + 마지막 sync 상태.

업무시간(KST 06~20시)에는 Render cron이 안 돌므로, 즉시 동기화가
필요할 때 admin이 본 페이지에서 트리거. 외부 cron secret 불필요.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.security import require_admin
from app.services.sync import ALL_KINDS, SyncKind, get_sync
from app.services.sync_run_log import (
    finish_sync_run,
    start_sync_run,
    status_for_result,
)

logger = logging.getLogger("admin.sync")
# Render/Uvicorn web service 로그에서 INFO 레벨 운영 이벤트가 확실히 보이게 한다.
ops_logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/admin/sync", tags=["admin_sync"])


class SyncStatusItem(BaseModel):
    kind: str
    last_incremental_synced_at: datetime | None = None
    last_full_synced_at: datetime | None = None
    last_error: str = ""
    last_run_count: int = 0


class SyncStatusResponse(BaseModel):
    items: list[SyncStatusItem]


@router.get("/status", response_model=SyncStatusResponse)
def get_sync_status(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SyncStatusResponse:
    """모든 kind의 마지막 sync 시각/카운트/에러 표시."""
    rows = db.execute(select(M.NotionSyncState)).scalars().all()
    by_kind = {r.db_kind: r for r in rows}
    items: list[SyncStatusItem] = []
    for kind in ALL_KINDS:
        row = by_kind.get(kind)
        if row is None:
            items.append(SyncStatusItem(kind=kind))
        else:
            items.append(
                SyncStatusItem(
                    kind=kind,
                    last_incremental_synced_at=row.last_incremental_synced_at,
                    last_full_synced_at=row.last_full_synced_at,
                    last_error=row.last_error or "",
                    last_run_count=row.last_run_count,
                )
            )
    return SyncStatusResponse(items=items)


class SyncRunRequest(BaseModel):
    kind: str | None = None  # None = 전체
    full: bool = False


class SyncRunResponse(BaseModel):
    status: str  # "started" | "already_running" | "error"
    kind: str | None = None
    full: bool = False
    run_id: str


class SyncRunLogItem(BaseModel):
    run_id: str
    source: str
    kind: str | None = None
    full: bool
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None
    result: str = ""
    error: str = ""


class SyncRunLogResponse(BaseModel):
    items: list[SyncRunLogItem]


@router.post("/run", response_model=SyncRunResponse)
async def run_sync(
    body: SyncRunRequest,
    background: BackgroundTasks,
    _admin: User = Depends(require_admin),
) -> SyncRunResponse:
    """admin 강제 트리거 — fire-and-forget. 결과는 status endpoint로 polling."""
    if body.kind and body.kind not in ALL_KINDS:
        raise HTTPException(
            status_code=400, detail=f"unknown kind: {body.kind}"
        )

    sync = get_sync()
    run_id = uuid4().hex[:8]
    requested_at = time.monotonic()
    start_sync_run(run_id=run_id, source="manual", kind=body.kind, full=body.full)
    ops_logger.info(
        "admin sync accepted run_id=%s kind=%s full=%s",
        run_id,
        body.kind or "all",
        body.full,
    )

    async def _run() -> None:
        ops_logger.info(
            "admin sync started run_id=%s kind=%s full=%s",
            run_id,
            body.kind or "all",
            body.full,
        )
        try:
            if body.kind:
                count = await sync.sync_kind(body.kind, full=body.full)  # type: ignore[arg-type]
                finish_sync_run(
                    run_id=run_id,
                    status="success",
                    result={"kind": body.kind, "count": count},
                )
                elapsed = time.monotonic() - requested_at
                ops_logger.info(
                    "admin sync done run_id=%s kind=%s full=%s count=%d elapsed=%.1fs",
                    run_id,
                    body.kind,
                    body.full,
                    count,
                    elapsed,
                )
                logger.info(
                    "admin sync %s full=%s done: %d",
                    body.kind,
                    body.full,
                    count,
                )
            else:
                result = await sync.sync_all(full=body.full)
                finish_sync_run(
                    run_id=run_id,
                    status=status_for_result(result),
                    result=result,
                )
                elapsed = time.monotonic() - requested_at
                ops_logger.info(
                    "admin sync_all done run_id=%s full=%s result=%s elapsed=%.1fs",
                    run_id,
                    body.full,
                    result,
                    elapsed,
                )
                logger.info(
                    "admin sync_all full=%s done: %s", body.full, result
                )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - requested_at
            finish_sync_run(
                run_id=run_id,
                status="failed",
                error=str(exc),
            )
            ops_logger.exception(
                "admin sync failed run_id=%s kind=%s full=%s elapsed=%.1fs",
                run_id,
                body.kind or "all",
                body.full,
                elapsed,
            )
            logger.exception(
                "admin sync 실패 kind=%s full=%s", body.kind, body.full
            )

    background.add_task(_run)
    return SyncRunResponse(
        status="started", kind=body.kind, full=body.full, run_id=run_id
    )


@router.get("/runs", response_model=SyncRunLogResponse)
def list_sync_runs(
    limit: int = Query(default=10, ge=1, le=50),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SyncRunLogResponse:
    """최근 sync 실행 이력."""
    rows = (
        db.execute(
            select(M.NotionSyncRunLog)
            .order_by(M.NotionSyncRunLog.started_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    now = datetime.now(tz=rows[0].started_at.tzinfo) if rows else None
    items: list[SyncRunLogItem] = []
    for row in rows:
        finished_at = row.finished_at
        end_at = finished_at or now
        elapsed = (
            (end_at - row.started_at).total_seconds()
            if end_at is not None
            else None
        )
        items.append(
            SyncRunLogItem(
                run_id=row.run_id,
                source=row.source,
                kind=row.kind or None,
                full=row.full,
                status=row.status,
                started_at=row.started_at,
                finished_at=finished_at,
                elapsed_seconds=elapsed,
                result=row.result or "",
                error=row.error or "",
            )
        )
    return SyncRunLogResponse(items=items)


# ── PR-FO Phase 1.3.1 Outbox monitoring ──


class OutboxStatusEntry(BaseModel):
    status: str  # pending | processing | retry | sent | dead
    count: int
    oldest_created_at: str | None = None


class OutboxStatusResponse(BaseModel):
    items: list[OutboxStatusEntry]


@router.get("/outbox", response_model=OutboxStatusResponse)
def outbox_status(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> OutboxStatusResponse:
    """notion_outbox 상태별 카운트 + 가장 오래된 row created_at.

    인프라 깔린 후 모니터링. pending count가 계속 늘면 drain worker가 안 돌거나
    노션 API 장애. dead count > 0이면 수동 점검 필요.
    """
    from app.services.notion_outbox import status_summary

    items = [OutboxStatusEntry(**row) for row in status_summary(db)]
    return OutboxStatusResponse(items=items)
