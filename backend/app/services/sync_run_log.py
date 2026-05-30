"""sync 실행 이력 기록 helper."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Literal

from app.db import SessionLocal
from app.models import mirror as M

SyncRunStatus = Literal["running", "success", "partial_failed", "failed"]
logger = logging.getLogger("sync.run_log")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json_text(value: object | None) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str)


def start_sync_run(
    *,
    run_id: str,
    source: str,
    kind: str | None,
    full: bool,
) -> None:
    """sync 실행 시작 이력을 남긴다."""
    try:
        with SessionLocal() as db:
            row = M.NotionSyncRunLog(
                run_id=run_id,
                source=source,
                kind=kind or "",
                full=full,
                status="running",
                started_at=_utcnow(),
            )
            db.merge(row)
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("sync run log 시작 기록 실패 run_id=%s", run_id)


def finish_sync_run(
    *,
    run_id: str,
    status: SyncRunStatus,
    result: object | None = None,
    error: str = "",
) -> None:
    """sync 실행 종료 상태를 기록한다."""
    try:
        with SessionLocal() as db:
            row = db.get(M.NotionSyncRunLog, run_id)
            if row is None:
                row = M.NotionSyncRunLog(
                    run_id=run_id,
                    source="unknown",
                    kind="",
                    full=False,
                    started_at=_utcnow(),
                )
                db.add(row)
            row.status = status
            row.result = _json_text(result)
            row.error = error[:4000]
            row.finished_at = _utcnow()
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("sync run log 종료 기록 실패 run_id=%s", run_id)


def status_for_result(result: dict[str, int]) -> SyncRunStatus:
    """sync_all 결과 dict에서 부분 실패 여부를 판단한다."""
    if any(count < 0 for count in result.values()):
        return "partial_failed"
    return "success"
