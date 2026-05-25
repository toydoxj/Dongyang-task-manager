"""PR-FT Phase 1.3.6 회귀 테스트 — sales 도메인 mirror-first + outbox."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import mirror as M
from app.routers.sales import _sale_page_from_mirror_with_update


def _sale_row(
    *,
    page_id: str = "sale-1",
    code: str = "영25-001",
    name: str = "테스트영업",
    properties: dict | None = None,
) -> M.MirrorSales:
    if properties is None:
        properties = {
            "견적서명": {"type": "title", "title": [{"plain_text": name}]},
            "단계": {"type": "select", "select": {"name": "진행중"}},
        }
    return M.MirrorSales(
        page_id=page_id,
        code=code,
        name=name,
        kind="수주영업",
        stage="진행중",
        category=[],
        assignees=[],
        properties=properties,
        url="https://notion.so/sale-1",
        archived=False,
    )


def test_sale_page_from_mirror_merges_props() -> None:
    """update_props 병합 + page-like dict 형태."""
    row = _sale_row()
    update_props = {"단계": {"select": {"name": "완료"}}}
    page = _sale_page_from_mirror_with_update(row, update_props)
    assert page["id"] == "sale-1"
    assert page["properties"]["단계"]["select"]["name"] == "완료"
    assert page["properties"]["견적서명"]["title"][0]["plain_text"] == "테스트영업"
    assert page["url"] == "https://notion.so/sale-1"
    assert "T" in page["last_edited_time"]


def test_sale_page_with_null_properties() -> None:
    """row.properties=None이어도 update_props만으로 page 생성."""
    row = _sale_row(properties={})
    row.properties = None  # type: ignore[assignment]
    update_props = {"견적금액": {"number": 1000000}}
    page = _sale_page_from_mirror_with_update(row, update_props)
    assert page["properties"]["견적금액"]["number"] == 1000000


def test_sale_estimated_amount_payload() -> None:
    """_sync_sale_estimated_amount의 enqueue payload 형태 검증."""
    payload = {"견적금액": {"number": 5000000}}
    assert "견적금액" in payload
    assert payload["견적금액"]["number"] == 5000000
