"""발주처 create mirror-first 회귀 테스트."""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.models import mirror as M
from app.models.auth import User
from app.models.notion_outbox import (
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_SENT,
    NotionOutbox,
)
from app.routers.clients import (
    ClientCreateRequest,
    ClientUpdateRequest,
    create_client,
    delete_client,
    update_client,
)
from app.scripts.outbox_drain import _finalize_create_mirror
from app.services import notion_props as P


class _Result:
    def __init__(
        self,
        *,
        first: Any = None,
        scalar: Any = None,
    ):
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
        rows: dict[str, M.MirrorClient] | None = None,
        execute_results: list[_Result] | None = None,
    ):
        self.rows = rows or {}
        self.execute_results = execute_results or []
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.committed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    def execute(self, *_args: Any, **_kwargs: Any) -> _Result:
        if self.execute_results:
            return self.execute_results.pop(0)
        return _Result()

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def get(self, _model: Any, key: str) -> M.MirrorClient | None:
        return self.rows.get(key)


class _FakeSync:
    def upsert_in_session(self, db: _FakeDb, kind: str, page: dict) -> None:
        assert kind == "clients"
        props = page.get("properties", {})
        row = db.rows.get(page["id"])
        if row is None:
            row = M.MirrorClient(page_id=page["id"])
            db.rows[page["id"]] = row
        row.name = P.title(props, "이름")
        row.category = P.select_name(props, "구분")
        row.properties = props
        row.last_edited_time = datetime.now(UTC)
        row.synced_at = datetime.now(UTC)
        row.archived = bool(page.get("archived", False))

    def archive_in_session(self, db: _FakeDb, kind: str, page_id: str) -> None:
        assert kind == "clients"
        row = db.rows[page_id]
        row.archived = True
        row.synced_at = datetime.now(UTC)


def _user(*, role: str = "admin") -> User:
    return User(
        id=1,
        username="admin",
        password="",
        name="관리자",
        role=role,
        status="active",
    )


def _client_row(
    page_id: str,
    *,
    archived: bool = False,
    name: str = "동양건축",
) -> M.MirrorClient:
    props = {
        "이름": {"title": [{"text": {"content": name}}]},
        "구분": {"select": {"name": "건축사무소"}},
    }
    now = datetime(2026, 5, 28, tzinfo=UTC)
    return M.MirrorClient(
        page_id=page_id,
        name=name,
        category="건축사무소",
        properties=props,
        last_edited_time=now,
        synced_at=now,
        archived=archived,
    )


def test_create_client_has_no_notion_dependency() -> None:
    assert "notion" not in inspect.signature(create_client).parameters


@pytest.mark.asyncio
async def test_create_client_writes_local_mirror_and_create_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.clients.get_sync", lambda: _FakeSync())
    # create 중복 체크 + enqueue dedupe
    db = _FakeDb(execute_results=[_Result(), _Result()])

    item = await create_client(
        ClientCreateRequest(name="동양건축", category="건축사무소"),
        _user=_user(),
        db=db,
    )

    assert item.id.startswith("local_client_")
    assert item.name == "동양건축"
    assert item.category == "건축사무소"
    assert db.rows[item.id].name == "동양건축"

    outbox = next(o for o in db.added if isinstance(o, NotionOutbox))
    assert outbox.aggregate_type == "clients"
    assert outbox.aggregate_id == item.id
    assert outbox.op == OP_CREATE
    assert outbox.notion_page_id is None
    assert outbox.status == STATUS_PENDING
    assert outbox.payload["이름"]["title"][0]["text"]["content"] == "동양건축"
    assert outbox.payload["구분"]["select"]["name"] == "건축사무소"
    assert db.committed is True


@pytest.mark.asyncio
async def test_create_client_returns_existing_without_outbox() -> None:
    existing = _client_row("client-1", name="동양건축")
    db = _FakeDb(rows={existing.page_id: existing}, execute_results=[_Result(scalar=existing)])

    item = await create_client(
        ClientCreateRequest(name=" 동양건축 "),
        _user=_user(),
        db=db,
    )

    assert item.id == "client-1"
    assert item.name == "동양건축"
    assert not any(isinstance(o, NotionOutbox) for o in db.added)


@pytest.mark.asyncio
async def test_update_local_client_patches_create_payload_without_update_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.clients.get_sync", lambda: _FakeSync())
    local_id = "local_client_abc"
    create_outbox = NotionOutbox(
        aggregate_type="clients",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={"이름": {"title": [{"text": {"content": "동양건축"}}]}},
        status=STATUS_PENDING,
    )
    db = _FakeDb(
        rows={local_id: _client_row(local_id)},
        execute_results=[_Result(scalar=create_outbox)],
    )

    updated = await update_client(
        local_id,
        ClientUpdateRequest(category="시공사"),
        _user=_user(),
        db=db,
    )

    assert updated.id == local_id
    assert updated.category == "시공사"
    assert db.rows[local_id].category == "시공사"
    assert create_outbox.payload["구분"]["select"]["name"] == "시공사"
    assert not any(
        isinstance(o, NotionOutbox) and o.op == OP_UPDATE for o in db.added
    )


@pytest.mark.asyncio
async def test_update_local_processing_client_returns_409(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.clients.get_sync", lambda: _FakeSync())
    local_id = "local_client_processing"
    create_outbox = NotionOutbox(
        aggregate_type="clients",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={},
        status=STATUS_PROCESSING,
    )
    db = _FakeDb(
        rows={local_id: _client_row(local_id)},
        execute_results=[_Result(scalar=create_outbox)],
    )

    with pytest.raises(HTTPException) as exc:
        await update_client(
            local_id,
            ClientUpdateRequest(category="시공사"),
            _user=_user(),
            db=db,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_resolves_sent_local_client_to_real_page_id(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.clients.get_sync", lambda: _FakeSync())
    local_id = "local_client_abc"
    real_id = "notion-client-1"
    db = _FakeDb(
        rows={
            local_id: _client_row(local_id, archived=True),
            real_id: _client_row(real_id),
        },
        # resolve sent id + enqueue dedupe
        execute_results=[_Result(scalar=real_id), _Result()],
    )

    updated = await update_client(
        local_id,
        ClientUpdateRequest(category="시공사"),
        _user=_user(),
        db=db,
    )

    assert updated.id == real_id
    assert db.rows[real_id].category == "시공사"
    outbox = next(o for o in db.added if isinstance(o, NotionOutbox))
    assert outbox.op == OP_UPDATE
    assert outbox.aggregate_id == real_id
    assert outbox.notion_page_id == real_id
    assert outbox.status == STATUS_PENDING


@pytest.mark.asyncio
async def test_delete_local_pending_client_archives_without_delete_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.clients.get_sync", lambda: _FakeSync())
    local_id = "local_client_delete"
    create_outbox = NotionOutbox(
        aggregate_type="clients",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={},
        status=STATUS_PENDING,
    )
    db = _FakeDb(
        rows={local_id: _client_row(local_id)},
        # used_in_project + active create
        execute_results=[_Result(), _Result(scalar=create_outbox)],
    )

    await delete_client(local_id, _admin=_user(), db=db)

    assert db.rows[local_id].archived is True
    assert db.deleted == [create_outbox]
    assert not any(
        isinstance(o, NotionOutbox) and o.op == OP_DELETE for o in db.added
    )


def test_finalize_create_archives_local_and_upserts_real_client(monkeypatch) -> None:
    local = _client_row("local_client_abc")
    db = _FakeDb(rows={local.page_id: local})
    calls: list[tuple[str, dict]] = []

    class _FinalizeSync:
        def upsert_in_session(self, _db: Any, kind: str, page: dict) -> None:
            calls.append((kind, page))

    monkeypatch.setattr("app.services.sync.get_sync", lambda: _FinalizeSync())
    row = SimpleNamespace(
        op=OP_CREATE,
        aggregate_type="clients",
        aggregate_id=local.page_id,
    )
    page = {
        "id": "notion-client-2",
        "properties": {
            "이름": {"title": [{"text": {"content": "실제"}}]},
        },
    }

    _finalize_create_mirror(db, row, page)

    assert local.archived is True
    assert calls == [("clients", page)]


def test_status_sent_constant_imported() -> None:
    assert STATUS_SENT == "sent"
