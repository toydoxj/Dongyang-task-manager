"""PR-FR Phase 1.3.4 회귀 테스트 — tasks update/archive mirror-first + outbox.

PR-FP와 동일 패턴 — tasks 도메인 cut-over. update/archive는 노션 호출 0건,
mirror direct + outbox enqueue.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.notion_outbox import (
    OP_DELETE,
    OP_UPDATE,
    is_active_status,
    STATUS_PENDING,
)


def test_op_delete_constant() -> None:
    """archive_task가 사용하는 OP_DELETE 상수 존재."""
    assert OP_DELETE == "delete"


def test_op_update_constant() -> None:
    """update_task가 사용하는 OP_UPDATE 상수 존재."""
    assert OP_UPDATE == "update"


def test_sync_upsert_in_session_exists() -> None:
    """sync.upsert_in_session — 호출자 transaction 안에서 mirror upsert."""
    from app.services.sync import NotionSyncService

    assert hasattr(NotionSyncService, "upsert_in_session")
    assert hasattr(NotionSyncService, "archive_in_session")


def test_enqueue_delete_requires_notion_page_id() -> None:
    """archive_task가 enqueue(op=delete)할 때 notion_page_id 필수."""
    from app.services.notion_outbox import enqueue

    db = MagicMock()
    with pytest.raises(ValueError, match="requires notion_page_id"):
        enqueue(
            db, aggregate_type="tasks", aggregate_id="t1",
            op=OP_DELETE, payload={},
        )


def test_enqueue_delete_with_page_id_inserts() -> None:
    """archive: enqueue(op=delete, notion_page_id=...) 정상 insert."""
    from app.services.notion_outbox import enqueue

    db = MagicMock()
    db.execute.return_value.first.return_value = None
    enqueue(
        db, aggregate_type="tasks", aggregate_id="t1",
        op=OP_DELETE, payload={}, notion_page_id="t1",
    )
    assert db.add.called


def test_active_status_includes_pending() -> None:
    """drain worker pickup 대상 — pending은 active."""
    assert is_active_status(STATUS_PENDING) is True
