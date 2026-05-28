"""건의사항 create mirror-first 파일럿 회귀 테스트."""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.models import mirror as M
from app.models.auth import User
from app.models.notion_outbox import (
    OP_CREATE,
    OP_UPDATE,
    STATUS_PENDING,
    STATUS_SENT,
    NotionOutbox,
)
from app.routers.suggestions import (
    SuggestionCreate,
    SuggestionUpdate,
    create_suggestion,
    update_suggestion,
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


class _FakeDb:
    def __init__(
        self,
        *,
        rows: dict[str, Any] | None = None,
        active_create: NotionOutbox | None = None,
        sent_real_id: str | None = None,
    ):
        self.rows = rows or {}
        self.active_create = active_create
        self.sent_real_id = sent_real_id
        self.added: list[Any] = []
        self.committed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if isinstance(obj, M.MirrorSuggestion):
            self.rows[obj.page_id] = obj

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

    def refresh(self, _obj: Any) -> None:
        return None

    def get(self, _model: Any, key: str) -> Any:
        return self.rows.get(key)


def _user() -> User:
    return User(
        id=1,
        username="hong",
        password="",
        name="홍길동",
        role="member",
        status="active",
    )


def _suggestion_row(page_id: str, *, archived: bool = False) -> M.MirrorSuggestion:
    now = datetime(2026, 5, 28, tzinfo=UTC)
    return M.MirrorSuggestion(
        page_id=page_id,
        title="제안",
        content="본문",
        author="홍길동",
        categories=[],
        status="접수",
        resolution="",
        created_time=now,
        last_edited_time=now,
        archived=archived,
    )


def test_create_suggestion_has_no_notion_dependency() -> None:
    assert "notion" not in inspect.signature(create_suggestion).parameters


@pytest.mark.asyncio
async def test_create_suggestion_writes_local_mirror_and_create_outbox() -> None:
    db = _FakeDb()

    item = await create_suggestion(
        SuggestionCreate(title="제안", content="본문", categories=["개선"]),
        user=_user(),
        db=db,
    )

    assert item.id.startswith("local_suggestion_")
    assert item.title == "제안"
    mirror_row = next(o for o in db.added if isinstance(o, M.MirrorSuggestion))
    assert mirror_row.page_id == item.id
    assert mirror_row.author == "홍길동"
    assert mirror_row.categories == ["개선"]

    outbox = next(o for o in db.added if isinstance(o, NotionOutbox))
    assert outbox.aggregate_type == "suggestions"
    assert outbox.aggregate_id == item.id
    assert outbox.op == OP_CREATE
    assert outbox.notion_page_id is None
    assert outbox.status == STATUS_PENDING
    assert outbox.payload["내용"]["title"][0]["text"]["content"] == "제안"
    assert outbox.payload["방안"]["rich_text"][0]["text"]["content"] == "본문"
    assert db.committed is True


@pytest.mark.asyncio
async def test_update_local_suggestion_patches_create_payload_without_update_outbox() -> None:
    local_id = "local_suggestion_abc"
    row = _suggestion_row(local_id)
    create_outbox = NotionOutbox(
        aggregate_type="suggestions",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload={"내용": {"title": [{"text": {"content": "제안"}}]}},
        status=STATUS_PENDING,
    )
    db = _FakeDb(rows={local_id: row}, active_create=create_outbox)

    updated = await update_suggestion(
        local_id,
        SuggestionUpdate(title="수정", content="수정본문", categories=["정책"]),
        user=_user(),
        db=db,
    )

    assert updated.id == local_id
    assert updated.title == "수정"
    assert create_outbox.payload["내용"]["title"][0]["text"]["content"] == "수정"
    assert create_outbox.payload["방안"]["rich_text"][0]["text"]["content"] == "수정본문"
    assert create_outbox.payload["구분"]["multi_select"] == [{"name": "정책"}]
    assert not any(
        isinstance(o, NotionOutbox) and o.op == OP_UPDATE for o in db.added
    )


def test_finalize_create_archives_local_and_upserts_real_suggestion(monkeypatch) -> None:
    local = _suggestion_row("local_suggestion_abc")
    db = _FakeDb(rows={local.page_id: local})
    calls: list[tuple[str, dict]] = []

    class _FakeSync:
        def upsert_in_session(self, _db: Any, kind: str, page: dict) -> None:
            calls.append((kind, page))

    monkeypatch.setattr("app.services.sync.get_sync", lambda: _FakeSync())
    row = SimpleNamespace(
        op=OP_CREATE,
        aggregate_type="suggestions",
        aggregate_id=local.page_id,
    )
    page = {
        "id": "notion-page-1",
        "properties": {"내용": {"type": "title", "title": [{"plain_text": "실제"}]}},
    }

    _finalize_create_mirror(db, row, page)

    assert local.archived is True
    assert calls == [("suggestions", page)]


@pytest.mark.asyncio
async def test_update_resolves_sent_local_id_to_real_page_id() -> None:
    local_id = "local_suggestion_abc"
    real_id = "notion-page-2"
    db = _FakeDb(
        rows={
            local_id: _suggestion_row(local_id, archived=True),
            real_id: _suggestion_row(real_id),
        },
        sent_real_id=real_id,
    )

    updated = await update_suggestion(
        local_id,
        SuggestionUpdate(content="나중 수정"),
        user=_user(),
        db=db,
    )

    assert updated.id == real_id
    outbox = next(o for o in db.added if isinstance(o, NotionOutbox))
    assert outbox.op == OP_UPDATE
    assert outbox.aggregate_id == real_id
    assert outbox.notion_page_id == real_id
    assert outbox.status == STATUS_PENDING
    assert db.rows[real_id].content == "나중 수정"


def test_status_sent_constant_imported() -> None:
    assert STATUS_SENT == "sent"
