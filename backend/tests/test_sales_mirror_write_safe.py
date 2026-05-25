"""PR-FU sales 도메인 재설계 회귀 테스트.

이전 PR-FT 회귀(name/code 빈 값 cascade) 방지:
1. sale_update_to_props: name/code 빈 string 무시
2. sale_from_mirror: 정규화 컬럼 우선 fallback
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import mirror as M
from app.models.sale import SaleUpdateRequest, sale_update_to_props
from app.routers.sales import _sale_page_from_mirror_with_update
from app.services.mirror_dto import sale_from_mirror


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
            "영업코드": {"type": "rich_text", "rich_text": [{"plain_text": code}]},
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
        url="",
        archived=False,
    )


def test_update_props_skips_empty_name() -> None:
    """name=""은 props에 포함되지 않음 — frontend prefill 빈 string 보호."""
    props = sale_update_to_props(SaleUpdateRequest(name="", stage="제출"))
    assert "견적서명" not in props
    assert "단계" in props


def test_update_props_skips_empty_code() -> None:
    """code=""은 props에 포함되지 않음."""
    props = sale_update_to_props(SaleUpdateRequest(code="", stage="제출"))
    assert "영업코드" not in props
    assert "단계" in props


def test_update_props_skips_whitespace_only_name() -> None:
    """공백만 있는 name도 무시 (strip 결과 빈 string)."""
    props = sale_update_to_props(SaleUpdateRequest(name="   "))
    assert "견적서명" not in props


def test_update_props_includes_normal_name_code() -> None:
    """정상 값은 props에 정상 포함."""
    props = sale_update_to_props(SaleUpdateRequest(name="경기도프로젝트", code="영25-001"))
    assert props["견적서명"]["title"][0]["text"]["content"] == "경기도프로젝트"
    assert props["영업코드"]["rich_text"][0]["text"]["content"] == "영25-001"


def test_sale_from_mirror_uses_normalized_columns_when_properties_missing() -> None:
    """row.properties에 견적서명/영업코드 누락이어도 정규화 컬럼이 fallback."""
    row = _sale_row(properties={})  # properties 빈 dict
    sale = sale_from_mirror(row)
    # 정규화 컬럼 사용
    assert sale.name == "테스트영업"
    assert sale.code == "영25-001"
    assert sale.stage == "진행중"
    assert sale.kind == "수주영업"


def test_sale_from_mirror_normalized_columns_override_properties() -> None:
    """정규화 컬럼이 properties보다 우선 — properties는 stale일 수 있음."""
    row = _sale_row(
        code="영25-001",  # mirror 정규화 컬럼
        name="최신영업명",
        properties={
            # properties에는 옛값
            "견적서명": {"type": "title", "title": [{"plain_text": "옛영업명"}]},
            "영업코드": {"type": "rich_text", "rich_text": [{"plain_text": "옛영25-000"}]},
        },
    )
    sale = sale_from_mirror(row)
    assert sale.code == "영25-001"  # 정규화 컬럼 우선
    assert sale.name == "최신영업명"


def test_page_from_mirror_with_update_merges_properly() -> None:
    """단계만 변경하는 update_props가 견적서명/영업코드 보존."""
    row = _sale_row()
    update_props = {"단계": {"select": {"name": "제출"}}}
    page = _sale_page_from_mirror_with_update(row, update_props)
    # 단계만 update
    assert page["properties"]["단계"]["select"]["name"] == "제출"
    # 견적서명/영업코드는 기존값 보존
    assert page["properties"]["견적서명"]["title"][0]["plain_text"] == "테스트영업"
    assert page["properties"]["영업코드"]["rich_text"][0]["plain_text"] == "영25-001"


def test_cascade_prevented_e2e() -> None:
    """cascade 시나리오 e2e — frontend 빈 prefill로 PATCH해도 mirror 손실 없음.

    1. frontend가 form.name="" / form.code="" / stage="제출" PATCH
    2. sale_update_to_props가 name/code 빈 string skip → props에 단계만
    3. update_props에 견적서명/영업코드 없음 → merge에서도 영향 없음
    """
    row = _sale_row()
    # frontend 빈 prefill 시뮬레이션
    body = SaleUpdateRequest(name="", code="", stage="제출")
    props = sale_update_to_props(body)

    # name/code 빈 값은 props에 없음
    assert "견적서명" not in props
    assert "영업코드" not in props
    assert props["단계"]["select"]["name"] == "제출"

    # mirror merge — 기존 견적서명/영업코드 보존
    page = _sale_page_from_mirror_with_update(row, props)
    assert page["properties"]["견적서명"]["title"][0]["plain_text"] == "테스트영업"
    assert page["properties"]["영업코드"]["rich_text"][0]["plain_text"] == "영25-001"
