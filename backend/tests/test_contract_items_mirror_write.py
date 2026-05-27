"""PR-FZ 회귀 테스트 — contract_items update/delete mirror-first + outbox.

tasks(PR-FR)와 동일 패턴 표본 전환. update/delete는 노션 동기 호출 0건,
mirror direct + outbox enqueue. create는 page_id 확정 위해 노션 직접 유지.
"""
from __future__ import annotations

import inspect

from app.models.contract_item import (
    ContractItemUpdateRequest,
    contract_item_update_props,
)
from app.models.notion_outbox import OP_DELETE, OP_UPDATE


def test_update_delete_no_notion_dependency() -> None:
    """전환 회귀 방지 — update/delete 핸들러에 notion 의존성이 재유입되지 않음."""
    from app.routers.contract_items import (
        delete_contract_item,
        update_contract_item,
    )

    assert "notion" not in inspect.signature(update_contract_item).parameters
    assert "notion" not in inspect.signature(delete_contract_item).parameters


def test_create_keeps_notion_dependency() -> None:
    """create는 노션 page_id 즉시 확정 위해 노션 직접 유지 (tasks 일관)."""
    from app.routers.contract_items import create_contract_item

    assert "notion" in inspect.signature(create_contract_item).parameters


def test_update_props_empty_when_no_fields() -> None:
    assert contract_item_update_props(ContractItemUpdateRequest()) == {}


def test_update_props_builds_only_changed_fields() -> None:
    props = contract_item_update_props(
        ContractItemUpdateRequest(label="추가용역", amount=1000)
    )
    assert props["라벨"]["title"][0]["text"]["content"] == "추가용역"
    assert props["금액"]["number"] == 1000
    assert "발주처" not in props  # 미지정 필드는 제외


def test_op_constants() -> None:
    assert OP_UPDATE == "update"
    assert OP_DELETE == "delete"
