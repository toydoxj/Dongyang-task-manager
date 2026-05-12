"""/api/admin/sync — admin 강제 트리거 + 마지막 sync 상태.

업무시간(KST 06~20시)에는 Render cron이 안 돌므로, 즉시 동기화가
필요할 때 admin이 본 페이지에서 트리거. 외부 cron secret 불필요.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.security import require_admin
from app.services.sync import ALL_KINDS, SyncKind, get_sync

logger = logging.getLogger("admin.sync")

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

    async def _run() -> None:
        try:
            if body.kind:
                count = await sync.sync_kind(body.kind, full=body.full)  # type: ignore[arg-type]
                logger.info(
                    "admin sync %s full=%s done: %d",
                    body.kind,
                    body.full,
                    count,
                )
            else:
                result = await sync.sync_all(full=body.full)
                logger.info(
                    "admin sync_all full=%s done: %s", body.full, result
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "admin sync 실패 kind=%s full=%s", body.kind, body.full
            )

    background.add_task(_run)
    return SyncRunResponse(status="started", kind=body.kind, full=body.full)
