"""계약 항목 create mirror-first 회귀 테스트."""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.models import mirror as M
from app.models.auth import User
from app.models.contract_item import (
    ContractItem,
    ContractItemCreateRequest,
    ContractItemUpdateRequest,
)
from app.models.notion_outbox import (
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_SENT,
    NotionOutbox,
)
from app.routers.contract_items import (
    create_contract_item,
    delete_contract_item,
    update_contract_item,
)
from app.scripts.outbox_drain import _finalize_create_mirror


class _Result:
    def __init__(self, *, first: Any = None, scalar: Any = None):
        self._first = first
        self._scalar = scalar

    def first(self) -> Any:
        return self._first

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def all(self) -> list[Any]:
        return []


class _FakeDb:
    def __init__(
        self,
        *,
        rows: dict[str, M.MirrorContractItem] | None = None,
        active_create: NotionOutbox | None = None,
        sent_real_id: str | None = None,
    ):
        self.rows = rows or {}
        self.active_create = active_create
        self.sent_real_id = sent_real_id
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.committed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    def execute(self, *_args: Any, **_kwargs: Any) -> _Result:
        if self.active_create is not None:
            return _Result(scalar=self.active_create)
        if self.sent_real_id is not None:
            real_id = self.sent_real_id
            self.sent_real_id = None
            return _Result(scalar=real_id)
        return _Result()

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def get(self, _model: Any, key: str) -> M.MirrorContractItem | None:
        return self.rows.get(key)


class _FakeSync:
    def upsert_in_session(self, db: _FakeDb, kind: str, page: dict) -> None:
        assert kind == "contract_items"
        item = ContractItem.from_notion_page(page)
        row = db.rows.get(item.id)
        if row is None:
            row = M.MirrorContractItem(page_id=item.id)
            db.rows[item.id] = row
        row.project_id = item.project_id
        row.client_id = item.client_id
        row.label = item.label
        row.amount = item.amount
        row.vat = item.vat
        row.sort_order = item.sort_order
        row.properties = page.get("properties", {})
        row.last_edited_time = datetime.now(UTC)
        row.synced_at = datetime.now(UTC)
        row.archived = bool(page.get("archived", False))

    def archive_in_session(self, db: _FakeDb, kind: str, page_id: str) -> None:
        assert kind == "contract_items"
        row = db.rows[page_id]
        row.archived = True
        row.synced_at = datetime.now(UTC)


def _editor() -> User:
    return User(
        id=1,
        username="lead",
        password="",
        name="팀장",
        role="team_lead",
        status="active",
    )


def _contract_item_row(
    page_id: str,
    *,
    archived: bool = False,
    amount: float = 1000,
) -> M.MirrorContractItem:
    props = {
        "라벨": {"title": [{"text": {"content": "본 계약"}}]},
        "프로젝트": {"relation": [{"id": "project-1"}]},
        "발주처": {"relation": [{"id": "client-1"}]},
        "금액": {"number": amount},
        "VAT": {"number": 100},
        "정렬": {"number": 1},
    }
    now = datetime(2026, 5, 28, tzinfo=UTC)
    return M.MirrorContractItem(
        page_id=page_id,
        project_id="project-1",
        client_id="client-1",
        label="본 계약",
        amount=amount,
        vat=100,
        sort_order=1,
        properties=props,
        last_edited_time=now,
        synced_at=now,
        archived=archived,
    )


def test_create_contract_item_has_no_notion_dependency() -> None:
    assert "notion" not in inspect.signature(create_contract_item).parameters


@pytest.mark.asyncio
async def test_create_contract_item_writes_local_mirror_and_create_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.contract_items.get_sync", lambda: _FakeSync())
    db = _FakeDb()

    item = await create_contract_item(
        ContractItemCreateRequest(
            project_id="project-1",
            client_id="client-1",
            label="추가용역",
            amount=1200000,
            vat=120000,
            sort_order=2,
        ),
        _user=_editor(),
        db=db,
    )

    assert item.id.startswith("local_contract_item_")
    assert item.project_id == "project-1"
    assert item.client_id == "client-1"
    assert item.label == "추가용역"
    assert db.rows[item.id].amount == 1200000

    outbox = next(o for o in db.added if isinstance(o, NotionOutbox))
    assert outbox.aggregate_type == "contract_items"
    assert outbox.aggregate_id == item.id
    assert outbox.op == OP_CREATE
    assert outbox.notion_page_id is None
    assert outbox.status == STATUS_PENDING
    assert outbox.payload["라벨"]["title"][0]["text"]["content"] == "추가용역"
    assert outbox.payload["프로젝트"]["relation"] == [{"id": "project-1"}]
    assert outbox.payload["발주처"]["relation"] == [{"id": "client-1"}]
    assert db.committed is True


@pytest.mark.asyncio
async def test_update_local_contract_item_patches_create_payload_without_update_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.contract_items.get_sync", lambda: _FakeSync())
    local_id = "local_contract_item_abc"
    create_outbox = NotionOutbox(
        aggregate_type="contract_items",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={"금액": {"number": 1000}},
        status=STATUS_PENDING,
    )
    db = _FakeDb(
        rows={local_id: _contract_item_row(local_id)},
        active_create=create_outbox,
    )

    updated = await update_contract_item(
        local_id,
        ContractItemUpdateRequest(label="변경설계", amount=7000),
        _user=_editor(),
        db=db,
    )

    assert updated.id == local_id
    assert updated.label == "변경설계"
    assert updated.amount == 7000
    assert db.rows[local_id].amount == 7000
    assert create_outbox.payload["라벨"]["title"][0]["text"]["content"] == "변경설계"
    assert create_outbox.payload["금액"]["number"] == 7000
    assert not any(
        isinstance(o, NotionOutbox) and o.op == OP_UPDATE for o in db.added
    )


@pytest.mark.asyncio
async def test_update_local_processing_contract_item_returns_409(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.contract_items.get_sync", lambda: _FakeSync())
    local_id = "local_contract_item_processing"
    create_outbox = NotionOutbox(
        aggregate_type="contract_items",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={},
        status=STATUS_PROCESSING,
    )
    db = _FakeDb(
        rows={local_id: _contract_item_row(local_id)},
        active_create=create_outbox,
    )

    with pytest.raises(HTTPException) as exc:
        await update_contract_item(
            local_id,
            ContractItemUpdateRequest(amount=3000),
            _user=_editor(),
            db=db,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_resolves_sent_local_contract_item_to_real_page_id(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.contract_items.get_sync", lambda: _FakeSync())
    local_id = "local_contract_item_abc"
    real_id = "notion-contract-item-1"
    db = _FakeDb(
        rows={
            local_id: _contract_item_row(local_id, archived=True),
            real_id: _contract_item_row(real_id),
        },
        sent_real_id=real_id,
    )

    updated = await update_contract_item(
        local_id,
        ContractItemUpdateRequest(amount=9000),
        _user=_editor(),
        db=db,
    )

    assert updated.id == real_id
    assert db.rows[real_id].amount == 9000
    outbox = next(o for o in db.added if isinstance(o, NotionOutbox))
    assert outbox.op == OP_UPDATE
    assert outbox.aggregate_id == real_id
    assert outbox.notion_page_id == real_id
    assert outbox.status == STATUS_PENDING


@pytest.mark.asyncio
async def test_delete_local_pending_contract_item_archives_without_delete_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.contract_items.get_sync", lambda: _FakeSync())
    local_id = "local_contract_item_delete"
    create_outbox = NotionOutbox(
        aggregate_type="contract_items",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={},
        status=STATUS_PENDING,
    )
    db = _FakeDb(
        rows={local_id: _contract_item_row(local_id)},
        active_create=create_outbox,
    )

    await delete_contract_item(local_id, _user=_editor(), db=db)

    assert db.rows[local_id].archived is True
    assert db.deleted == [create_outbox]
    assert not any(
        isinstance(o, NotionOutbox) and o.op == OP_DELETE for o in db.added
    )


def test_finalize_create_archives_local_and_upserts_real_contract_item(
    monkeypatch,
) -> None:
    local = _contract_item_row("local_contract_item_abc")
    db = _FakeDb(rows={local.page_id: local})
    calls: list[tuple[str, dict]] = []

    class _FinalizeSync:
        def upsert_in_session(self, _db: Any, kind: str, page: dict) -> None:
            calls.append((kind, page))

    monkeypatch.setattr("app.services.sync.get_sync", lambda: _FinalizeSync())
    row = SimpleNamespace(
        op=OP_CREATE,
        aggregate_type="contract_items",
        aggregate_id=local.page_id,
    )
    page = {
        "id": "notion-contract-item-2",
        "properties": {
            "라벨": {"title": [{"text": {"content": "실제"}}]},
            "프로젝트": {"relation": [{"id": "project-1"}]},
            "발주처": {"relation": [{"id": "client-1"}]},
        },
    }

    _finalize_create_mirror(db, row, page)

    assert local.archived is True
    assert calls == [("contract_items", page)]


def test_status_sent_constant_imported() -> None:
    assert STATUS_SENT == "sent"
