"""outbox pending row가 있는 mirror row의 stale sync overwrite 방지."""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock


def _active_guard(monkeypatch, expected_type: str, expected_id: str) -> None:
    def fake_has_active(_db, aggregate_type: str, aggregate_id: str) -> bool:
        assert aggregate_type == expected_type
        assert aggregate_id == expected_id
        return True

    monkeypatch.setattr("app.services.notion_outbox.has_active", fake_has_active)


def test_client_sync_upsert_skips_when_outbox_active(monkeypatch) -> None:
    from app.services.sync import NotionSyncService

    _active_guard(monkeypatch, "clients", "client-1")
    db = MagicMock()
    sync = NotionSyncService.__new__(NotionSyncService)

    sync._upsert_one(db, "clients", {"id": "client-1", "properties": {}})

    db.execute.assert_not_called()


def test_cashflow_sync_upsert_skips_when_outbox_active(monkeypatch) -> None:
    from app.services.sync import NotionSyncService

    _active_guard(monkeypatch, "cashflow", "income-1")
    db = MagicMock()
    sync = NotionSyncService.__new__(NotionSyncService)

    sync._upsert_one(db, "cashflow", {"id": "income-1", "properties": {}})

    db.execute.assert_not_called()


def test_expense_sync_upsert_skips_when_outbox_active(monkeypatch) -> None:
    from app.services.sync import NotionSyncService

    _active_guard(monkeypatch, "expense", "expense-1")
    db = MagicMock()
    sync = NotionSyncService.__new__(NotionSyncService)

    sync._upsert_one(db, "expense", {"id": "expense-1", "properties": {}})

    db.execute.assert_not_called()


def test_contract_item_sync_upsert_skips_when_outbox_active(monkeypatch) -> None:
    from app.services.sync import NotionSyncService

    _active_guard(monkeypatch, "contract_items", "contract-item-1")
    db = MagicMock()
    sync = NotionSyncService.__new__(NotionSyncService)

    sync._upsert_one(
        db, "contract_items", {"id": "contract-item-1", "properties": {}}
    )

    db.execute.assert_not_called()


def test_sale_sync_upsert_skips_when_outbox_active(monkeypatch) -> None:
    from app.services.sync import NotionSyncService

    _active_guard(monkeypatch, "sales", "sale-1")
    db = MagicMock()
    sync = NotionSyncService.__new__(NotionSyncService)

    sync._upsert_one(db, "sales", {"id": "sale-1", "properties": {}})

    db.execute.assert_not_called()


def test_router_upsert_in_session_bypasses_outbox_guard(monkeypatch) -> None:
    """로컬 write endpoint는 active outbox가 있어도 mirror를 갱신해야 한다."""
    from app.services.sync import NotionSyncService

    def fail_has_active(*_args, **_kwargs) -> bool:
        raise AssertionError("router write에서 active outbox guard가 호출됨")

    monkeypatch.setattr("app.services.notion_outbox.has_active", fail_has_active)
    db = MagicMock()
    sync = NotionSyncService.__new__(NotionSyncService)
    sync._upsert_client = MagicMock()

    sync.upsert_in_session(db, "clients", {"id": "client-1", "properties": {}})

    sync._upsert_client.assert_called_once()


def test_upsert_page_exposes_guard_option() -> None:
    """단건 write-through 호출자가 active outbox guard 여부를 명시할 수 있다."""
    from app.services.sync import NotionSyncService

    param = inspect.signature(NotionSyncService.upsert_page).parameters[
        "skip_active_outbox"
    ]

    assert param.default is True
