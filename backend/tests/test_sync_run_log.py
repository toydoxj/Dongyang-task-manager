from __future__ import annotations

from uuid import uuid4

from app.db import SessionLocal
from app.models import mirror as M
from app.services.sync_run_log import (
    finish_sync_run,
    start_sync_run,
    status_for_result,
)


def test_sync_run_log_records_success() -> None:
    run_id = uuid4().hex[:8]

    start_sync_run(run_id=run_id, source="manual", kind=None, full=True)
    finish_sync_run(run_id=run_id, status="success", result={"projects": 2})

    with SessionLocal() as db:
        row = db.get(M.NotionSyncRunLog, run_id)

    assert row is not None
    assert row.source == "manual"
    assert row.kind == ""
    assert row.full is True
    assert row.status == "success"
    assert row.result == '{"projects": 2}'
    assert row.finished_at is not None


def test_status_for_result_detects_partial_failure() -> None:
    assert status_for_result({"projects": 1, "tasks": 0}) == "success"
    assert status_for_result({"projects": 1, "tasks": -1}) == "partial_failed"
