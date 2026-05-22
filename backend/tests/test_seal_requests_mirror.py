"""PR-FL Phase 1.1 회귀 테스트 — /seal-requests GET → mirror 전환.

INCIDENT.md 2026-05-22 만성 hang 근본 해결: list_seal_requests가 노션 호출 없이
mirror_seal_requests SELECT로 응답.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db import SessionLocal
from app.models import mirror as M
from app.models.auth import User
from app.routers.seal_requests.list_endpoint import (
    _mirror_row_to_notion_page,
    list_seal_requests,
)


def _make_mirror_row(
    *,
    page_id: str = "p1",
    status: str = "1차검토 중",
    requester: str = "테스터",
    project_ids: list[str] | None = None,
    title: str = "구조검토서 요청",
    properties: dict | None = None,
) -> M.MirrorSealRequest:
    """sync.py가 채우는 형태의 mirror row 생성."""
    if properties is None:
        # _from_notion_page가 읽는 노션 raw 형식 — 최소 필드만
        properties = {
            "제목": {
                "type": "title",
                "title": [{"plain_text": title}],
            },
            "상태": {"type": "select", "select": {"name": status}},
            "날인유형": {
                "type": "select",
                "select": {"name": "구조검토서"},
            },
            "요청자": {
                "type": "rich_text",
                "rich_text": [{"plain_text": requester}],
            },
            "프로젝트": {
                "type": "relation",
                "relation": [{"id": pid} for pid in (project_ids or [])],
            },
        }
    row = M.MirrorSealRequest(
        page_id=page_id,
        title=title,
        seal_type="구조검토서",
        status=status,
        requester=requester,
        project_ids=project_ids or [],
        properties=properties,
        created_time=datetime(2026, 5, 22, tzinfo=timezone.utc),
        last_edited_time=datetime(2026, 5, 22, tzinfo=timezone.utc),
        archived=False,
    )
    return row


def test_mirror_row_to_notion_page_shape() -> None:
    """mirror row → page-like dict 변환 — _from_notion_page 기대 schema와 일치."""
    row = _make_mirror_row(page_id="abc-123")
    page = _mirror_row_to_notion_page(row)
    assert page["id"] == "abc-123"
    assert "properties" in page
    assert page["properties"]["요청자"]["rich_text"][0]["plain_text"] == "테스터"
    # ISO 문자열 형식 (Pydantic이 받아들이는 형태)
    assert "T" in page["created_time"]


def test_mirror_row_to_notion_page_null_properties() -> None:
    """옛 row가 properties=NULL이면 falsy 분기로 빈 dict 처리."""
    row = _make_mirror_row(properties={})
    row.properties = None  # type: ignore[assignment]
    page = _mirror_row_to_notion_page(row)
    assert page["properties"] == {}


@pytest.mark.asyncio
async def test_list_seal_requests_mirror_only_no_notion_call() -> None:
    """admin이 list 호출 → mirror SELECT만 — notion.query_all 호출 0회.

    SQLite 환경에선 mirror_* 테이블이 ARRAY/JSONB로 컴파일되지 않아 SKIP.
    Postgres 운영 흐름에서만 의미 있는 시나리오라 단위 테스트는 _mirror_row_to_notion_page
    + import 검증으로 갈음.
    """
    from app.db import _is_sqlite

    if _is_sqlite:
        pytest.skip("mirror tables는 Postgres 전용 — SQLite 환경 skip")

    # Postgres 환경에서만 실행 — db_url에 PostgreSQL 설정된 경우
    with SessionLocal() as db:
        user = User(
            id=1, name="admin", role="admin", status="active", email="a@x"
        )
        # mock notion (실제로 호출되지 않음을 검증)
        class _NoCallNotion:
            async def query_all(self, *args, **kwargs):
                raise AssertionError("notion.query_all 호출됨 — mirror-only 위반")

        res = await list_seal_requests(
            project_id=None, user=user, notion=_NoCallNotion(), db=db,  # type: ignore[arg-type]
        )
        assert res.items is not None  # 빈 리스트라도 OK (production data 의존 X)
        assert res.count == len(res.items)


@pytest.mark.asyncio
async def test_list_seal_requests_member_without_project_id_forbidden() -> None:
    """member role + project_id 없음 → 403 (기존 동작 유지)."""
    from fastapi import HTTPException

    user = User(id=1, name="m", role="member", status="active", email="m@x")
    with pytest.raises(HTTPException) as exc:
        await list_seal_requests(
            project_id=None, user=user, notion=None, db=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 403
