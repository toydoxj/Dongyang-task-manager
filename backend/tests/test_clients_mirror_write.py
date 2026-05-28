"""PR-GA/GK 회귀 — clients create/update/delete mirror-first + outbox.

create/update/delete는 노션 동기 호출 0건 (mirror direct + outbox enqueue).
"""
from __future__ import annotations

import inspect

from app.models.notion_outbox import OP_DELETE, OP_UPDATE


def test_update_delete_no_notion_dependency() -> None:
    from app.routers.clients import create_client, delete_client, update_client

    assert "notion" not in inspect.signature(create_client).parameters
    assert "notion" not in inspect.signature(update_client).parameters
    assert "notion" not in inspect.signature(delete_client).parameters


def test_op_constants() -> None:
    assert OP_UPDATE == "update"
    assert OP_DELETE == "delete"
