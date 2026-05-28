"""outbox local relation id 보정 회귀 테스트."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.notion_outbox import OP_CREATE
from app.scripts.outbox_drain import (
    _finalize_create_mirror,
    _resolve_local_relation_payloads,
)


class _Result:
    def __init__(
        self,
        *,
        rows: list[object] | None = None,
        scalar: str | None = None,
    ):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self._rows

    def scalar_one_or_none(self) -> str | None:
        return self._scalar


class _FakeDb:
    def __init__(
        self,
        *,
        rows: dict[str, object] | None = None,
        execute_results: list[_Result] | None = None,
    ):
        self.rows = rows or {}
        self.execute_results = execute_results or []

    def get(self, _model: object, key: str) -> object | None:
        return self.rows.get(key)

    def execute(self, *_args: object, **_kwargs: object) -> _Result:
        if self.execute_results:
            return self.execute_results.pop(0)
        return _Result()


def _relation_prop(prop_name: str, page_id: str) -> dict:
    return {prop_name: {"relation": [{"id": page_id}]}}


def test_finalize_contract_item_rewrites_cashflow_and_active_outbox(
    monkeypatch,
) -> None:
    local_id = "local_contract_item_abc"
    real_id = "notion-contract-item-1"
    local_row = SimpleNamespace(page_id=local_id, archived=False, synced_at=None)
    cashflow_row = SimpleNamespace(
        properties=_relation_prop("계약항목", local_id),
        synced_at=None,
    )
    active_outbox = SimpleNamespace(
        payload=_relation_prop("계약항목", local_id),
    )
    calls: list[tuple[str, dict]] = []

    class _Sync:
        def upsert_in_session(self, _db: object, kind: str, page: dict) -> None:
            calls.append((kind, page))

    monkeypatch.setattr("app.services.sync.get_sync", lambda: _Sync())
    db = _FakeDb(
        rows={local_id: local_row},
        execute_results=[
            _Result(rows=[cashflow_row]),
            _Result(rows=[active_outbox]),
        ],
    )
    row = SimpleNamespace(
        op=OP_CREATE,
        aggregate_type="contract_items",
        aggregate_id=local_id,
    )
    page = {"id": real_id, "properties": {}}

    _finalize_create_mirror(db, row, page)

    assert local_row.archived is True
    assert cashflow_row.properties["계약항목"]["relation"] == [{"id": real_id}]
    assert active_outbox.payload["계약항목"]["relation"] == [{"id": real_id}]
    assert calls == [("contract_items", page)]


def test_finalize_client_rewrites_contract_item_and_active_outbox(monkeypatch) -> None:
    local_id = "local_client_abc"
    real_id = "notion-client-1"
    local_row = SimpleNamespace(page_id=local_id, archived=False, synced_at=None)
    contract_item_row = SimpleNamespace(
        client_id=local_id,
        properties=_relation_prop("발주처", local_id),
        synced_at=None,
    )
    active_outbox = SimpleNamespace(
        payload=_relation_prop("발주처", local_id),
    )
    calls: list[tuple[str, dict]] = []

    class _Sync:
        def upsert_in_session(self, _db: object, kind: str, page: dict) -> None:
            calls.append((kind, page))

    monkeypatch.setattr("app.services.sync.get_sync", lambda: _Sync())
    db = _FakeDb(
        rows={local_id: local_row},
        execute_results=[
            _Result(rows=[contract_item_row]),
            _Result(rows=[active_outbox]),
        ],
    )
    row = SimpleNamespace(
        op=OP_CREATE,
        aggregate_type="clients",
        aggregate_id=local_id,
    )
    page = {"id": real_id, "properties": {}}

    _finalize_create_mirror(db, row, page)

    assert local_row.archived is True
    assert contract_item_row.client_id == real_id
    assert contract_item_row.properties["발주처"]["relation"] == [{"id": real_id}]
    assert active_outbox.payload["발주처"]["relation"] == [{"id": real_id}]
    assert calls == [("clients", page)]


def test_resolve_local_relation_payloads_rewrites_sent_mapping() -> None:
    local_id = "local_contract_item_abc"
    real_id = "notion-contract-item-1"
    db = _FakeDb(execute_results=[_Result(scalar=real_id)])
    row = SimpleNamespace(
        op=OP_CREATE,
        payload=_relation_prop("계약항목", local_id),
    )

    _resolve_local_relation_payloads(db, row)

    assert row.payload["계약항목"]["relation"] == [{"id": real_id}]


def test_resolve_local_relation_payloads_repairs_existing_mirror_refs() -> None:
    local_id = "local_contract_item_abc"
    real_id = "notion-contract-item-1"
    cashflow_row = SimpleNamespace(
        properties=_relation_prop("계약항목", local_id),
        synced_at=None,
    )
    active_outbox = SimpleNamespace(
        payload=_relation_prop("계약항목", local_id),
    )
    db = _FakeDb(
        execute_results=[
            _Result(scalar=real_id),
            _Result(rows=[cashflow_row]),
            _Result(rows=[active_outbox]),
        ],
    )
    row = SimpleNamespace(
        op=OP_CREATE,
        payload=_relation_prop("계약항목", local_id),
    )

    _resolve_local_relation_payloads(db, row)

    assert row.payload["계약항목"]["relation"] == [{"id": real_id}]
    assert cashflow_row.properties["계약항목"]["relation"] == [{"id": real_id}]
    assert active_outbox.payload["계약항목"]["relation"] == [{"id": real_id}]


def test_resolve_local_relation_payloads_waits_for_unresolved_mapping() -> None:
    local_id = "local_contract_item_abc"
    db = _FakeDb(execute_results=[_Result()])
    row = SimpleNamespace(
        op=OP_CREATE,
        payload=_relation_prop("계약항목", local_id),
    )

    with pytest.raises(ValueError, match="relation local id not resolved"):
        _resolve_local_relation_payloads(db, row)
