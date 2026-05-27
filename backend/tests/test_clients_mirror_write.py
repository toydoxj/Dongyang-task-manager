"""PR-GA 회귀 — clients update/delete mirror-first + outbox (PR-FZ 패턴).

update/delete는 노션 동기 호출 0건 (mirror direct + outbox enqueue).
create는 page_id 즉시 확정 위해 노션 직접 유지.
"""
from __future__ import annotations

import inspect

from app.models.notion_outbox import OP_DELETE, OP_UPDATE


def test_update_delete_no_notion_dependency() -> None:
    from app.routers.clients import delete_client, update_client

    assert "notion" not in inspect.signature(update_client).parameters
    assert "notion" not in inspect.signature(delete_client).parameters


def test_create_keeps_notion_dependency() -> None:
    from app.routers.clients import create_client

    assert "notion" in inspect.signature(create_client).parameters


def test_op_constants() -> None:
    assert OP_UPDATE == "update"
    assert OP_DELETE == "delete"
