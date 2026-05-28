"""수금 create mirror-first 회귀 테스트."""
from __future__ import annotations

import inspect
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.models import mirror as M
from app.models.auth import User
from app.models.cashflow import CashflowEntry
from app.models.notion_outbox import (
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_SENT,
    NotionOutbox,
)
from app.routers.cashflow import (
    IncomeCreateRequest,
    IncomeUpdateRequest,
    create_income,
    delete_income,
    update_income,
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
        rows: dict[str, M.MirrorCashflow] | None = None,
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

    def get(self, _model: Any, key: str) -> M.MirrorCashflow | None:
        return self.rows.get(key)


class _FakeSync:
    def upsert_in_session(self, db: _FakeDb, kind: str, page: dict) -> None:
        assert kind == "cashflow"
        entry = CashflowEntry.from_income_page(page)
        row = db.rows.get(entry.id)
        parsed_date = date.fromisoformat(entry.date) if entry.date else None
        if row is None:
            row = M.MirrorCashflow(page_id=entry.id, kind="income")
            db.rows[entry.id] = row
        row.kind = "income"
        row.project_ids = list(entry.project_ids)
        row.date = parsed_date
        row.amount = float(entry.amount or 0)
        row.category = entry.category or ""
        row.note = entry.note or ""
        row.properties = page.get("properties", {})
        row.last_edited_time = datetime.now(UTC)
        row.synced_at = datetime.now(UTC)
        row.archived = bool(page.get("archived", False))

    def archive_in_session(self, db: _FakeDb, kind: str, page_id: str) -> None:
        assert kind == "cashflow"
        row = db.rows[page_id]
        row.archived = True
        row.synced_at = datetime.now(UTC)


def _admin() -> User:
    return User(
        id=1,
        username="admin",
        password="",
        name="관리자",
        role="admin",
        status="active",
    )


def _income_row(
    page_id: str,
    *,
    archived: bool = False,
    amount: float = 1000,
) -> M.MirrorCashflow:
    props = {
        "수금일": {"date": {"start": "2026-05-28", "end": None}},
        "수금액(원)": {"number": amount},
        "회차": {"number": 1},
        "비고": {"rich_text": [{"text": {"content": "메모"}}]},
    }
    now = datetime(2026, 5, 28, tzinfo=UTC)
    return M.MirrorCashflow(
        page_id=page_id,
        kind="income",
        project_ids=[],
        date=date(2026, 5, 28),
        amount=amount,
        category="1회차",
        note="메모",
        properties=props,
        last_edited_time=now,
        synced_at=now,
        archived=archived,
    )


def test_create_income_has_no_notion_dependency() -> None:
    assert "notion" not in inspect.signature(create_income).parameters


@pytest.mark.asyncio
async def test_create_income_writes_local_mirror_and_create_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.cashflow.get_sync", lambda: _FakeSync())
    db = _FakeDb()

    item = await create_income(
        IncomeCreateRequest(
            date="2026-05-28",
            amount=1200000,
            round_no=2,
            project_ids=["project-1"],
            contract_item_id="contract-item-1",
            note="2차 수금",
        ),
        _user=_admin(),
        db=db,
    )

    assert item.id.startswith("local_cashflow_income_")
    assert item.type == "income"
    assert item.date == "2026-05-28"
    assert item.amount == 1200000
    assert db.rows[item.id].amount == 1200000
    assert db.rows[item.id].project_ids == ["project-1"]

    outbox = next(o for o in db.added if isinstance(o, NotionOutbox))
    assert outbox.aggregate_type == "cashflow"
    assert outbox.aggregate_id == item.id
    assert outbox.op == OP_CREATE
    assert outbox.notion_page_id is None
    assert outbox.status == STATUS_PENDING
    assert outbox.payload["수금일"]["date"]["start"] == "2026-05-28"
    assert outbox.payload["수금액(원)"]["number"] == 1200000
    assert outbox.payload["계약항목"]["relation"] == [{"id": "contract-item-1"}]
    assert db.committed is True


@pytest.mark.asyncio
async def test_update_local_income_patches_create_payload_without_update_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.cashflow.get_sync", lambda: _FakeSync())
    local_id = "local_cashflow_income_abc"
    create_outbox = NotionOutbox(
        aggregate_type="cashflow",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={
            "수금일": {"date": {"start": "2026-05-28", "end": None}},
            "수금액(원)": {"number": 1000},
        },
        status=STATUS_PENDING,
    )
    db = _FakeDb(
        rows={local_id: _income_row(local_id)},
        active_create=create_outbox,
    )

    updated = await update_income(
        local_id,
        IncomeUpdateRequest(amount=7000, note="수정 메모"),
        _user=_admin(),
        db=db,
    )

    assert updated.id == local_id
    assert updated.amount == 7000
    assert db.rows[local_id].amount == 7000
    assert db.rows[local_id].note == "수정 메모"
    assert create_outbox.payload["수금액(원)"]["number"] == 7000
    assert (
        create_outbox.payload["비고"]["rich_text"][0]["text"]["content"]
        == "수정 메모"
    )
    assert not any(
        isinstance(o, NotionOutbox) and o.op == OP_UPDATE for o in db.added
    )


@pytest.mark.asyncio
async def test_update_local_processing_income_returns_409(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.cashflow.get_sync", lambda: _FakeSync())
    local_id = "local_cashflow_income_processing"
    create_outbox = NotionOutbox(
        aggregate_type="cashflow",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={},
        status=STATUS_PROCESSING,
    )
    db = _FakeDb(
        rows={local_id: _income_row(local_id)},
        active_create=create_outbox,
    )

    with pytest.raises(HTTPException) as exc:
        await update_income(
            local_id,
            IncomeUpdateRequest(amount=3000),
            _user=_admin(),
            db=db,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_resolves_sent_local_income_to_real_page_id(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.cashflow.get_sync", lambda: _FakeSync())
    local_id = "local_cashflow_income_abc"
    real_id = "notion-income-1"
    db = _FakeDb(
        rows={
            local_id: _income_row(local_id, archived=True),
            real_id: _income_row(real_id),
        },
        sent_real_id=real_id,
    )

    updated = await update_income(
        local_id,
        IncomeUpdateRequest(amount=9000),
        _user=_admin(),
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
async def test_delete_local_pending_income_archives_without_delete_outbox(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.cashflow.get_sync", lambda: _FakeSync())
    local_id = "local_cashflow_income_delete"
    create_outbox = NotionOutbox(
        aggregate_type="cashflow",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={},
        status=STATUS_PENDING,
    )
    db = _FakeDb(
        rows={local_id: _income_row(local_id)},
        active_create=create_outbox,
    )

    await delete_income(local_id, _user=_admin(), db=db)

    assert db.rows[local_id].archived is True
    assert db.deleted == [create_outbox]
    assert not any(
        isinstance(o, NotionOutbox) and o.op == OP_DELETE for o in db.added
    )


def test_finalize_create_archives_local_and_upserts_real_cashflow(monkeypatch) -> None:
    local = _income_row("local_cashflow_income_abc")
    db = _FakeDb(rows={local.page_id: local})
    calls: list[tuple[str, dict]] = []

    class _FinalizeSync:
        def upsert_in_session(self, _db: Any, kind: str, page: dict) -> None:
            calls.append((kind, page))

    monkeypatch.setattr("app.services.sync.get_sync", lambda: _FinalizeSync())
    row = SimpleNamespace(
        op=OP_CREATE,
        aggregate_type="cashflow",
        aggregate_id=local.page_id,
    )
    page = {
        "id": "notion-income-2",
        "properties": {
            "수금일": {"date": {"start": "2026-05-28", "end": None}},
            "수금액(원)": {"number": 3000},
        },
    }

    _finalize_create_mirror(db, row, page)

    assert local.archived is True
    assert calls == [("cashflow", page)]


def test_status_sent_constant_imported() -> None:
    assert STATUS_SENT == "sent"
