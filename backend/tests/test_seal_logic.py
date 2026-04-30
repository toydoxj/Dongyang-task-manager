"""seal_logic — 검토구분 정규화 / 제목 템플릿 / 구조검토서 문서번호 발급 검증."""
from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import seal_logic as SL


# ── normalize_type / normalize_status ──


def test_normalize_type_legacy_to_new() -> None:
    assert SL.normalize_type("도면") == "구조도면"
    assert SL.normalize_type("검토서") == "구조검토서"


def test_normalize_type_new_passthrough() -> None:
    for t in SL.SEAL_TYPES_NEW:
        assert SL.normalize_type(t) == t


def test_normalize_type_unknown_passthrough() -> None:
    assert SL.normalize_type("기타") == "기타"
    assert SL.normalize_type("알수없음") == "알수없음"


def test_normalize_status_legacy_to_new() -> None:
    assert SL.normalize_status("요청") == "1차검토 중"
    assert SL.normalize_status("팀장승인") == "2차검토 중"
    assert SL.normalize_status("관리자승인") == "승인"
    assert SL.normalize_status("완료") == "승인"


def test_normalize_status_new_passthrough() -> None:
    for s in ("1차검토 중", "2차검토 중", "승인", "반려"):
        assert SL.normalize_status(s) == s


# ── build_title — 6종 패턴 ──


def test_build_title_calc() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조계산서",
            fields={"revision": 2, "용도": "허가용"},
        )
        == "DY-26-100_구조계산서_rev2_허가용"
    )


def test_build_title_calc_zero_rev() -> None:
    """revision=0/None이면 rev0."""
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조계산서",
            fields={"revision": 0, "용도": "허가용"},
        )
        == "DY-26-100_구조계산서_rev0_허가용"
    )


def test_build_title_safety_cert() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조안전확인서",
            fields={"용도": "착공용"},
        )
        == "DY-26-100_구조안전확인서_착공용"
    )


def test_build_title_review() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조검토서",
            fields={"문서번호": "26-의견-005"},
        )
        == "DY-26-100_26-의견-005_구조검토서"
    )


def test_build_title_drawing() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조도면",
            fields={"용도": "실시설계"},
        )
        == "DY-26-100_구조도면_실시설계"
    )


def test_build_title_report() -> None:
    assert SL.build_title(code="DY-26-100", seal_type="보고서", fields={}) == (
        "DY-26-100_보고서"
    )


def test_build_title_etc() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="기타",
            fields={"문서종류": "공사관리계획"},
        )
        == "DY-26-100_공사관리계획"
    )


def test_build_title_etc_default() -> None:
    """문서종류 비어있으면 '기타'로."""
    assert SL.build_title(code="DY-26-100", seal_type="기타", fields={}) == (
        "DY-26-100_기타"
    )


# ── issue_review_doc_number ──


def _mock_notion_with_pages(pages: list[dict[str, Any]]):
    notion = MagicMock()
    notion.query_all = AsyncMock(return_value=pages)
    return notion


def _page(doc_no: str) -> dict[str, Any]:
    return {
        "properties": {
            "문서번호": {
                "rich_text": [{"plain_text": doc_no}],
            }
        }
    }


@pytest.mark.asyncio
async def test_issue_first_doc_number() -> None:
    notion = _mock_notion_with_pages([])
    yy = date.today().strftime("%y")
    doc_no = await SL.issue_review_doc_number(notion, "db-id")
    assert doc_no == f"{yy}-의견-001"


@pytest.mark.asyncio
async def test_issue_next_doc_number() -> None:
    yy = date.today().strftime("%y")
    pages = [
        _page(f"{yy}-의견-001"),
        _page(f"{yy}-의견-005"),
        _page(f"{yy}-의견-003"),
    ]
    notion = _mock_notion_with_pages(pages)
    doc_no = await SL.issue_review_doc_number(notion, "db-id")
    assert doc_no == f"{yy}-의견-006"


@pytest.mark.asyncio
async def test_issue_skips_other_year() -> None:
    """다른 연도(prefix가 다른) 행은 무시 — 노션 query filter가 starts_with로 처리하지만
    혹시 누수돼도 _parse_review_n이 None을 반환해 보호."""
    yy = date.today().strftime("%y")
    other_yy = "99"
    pages = [
        _page(f"{yy}-의견-001"),
        _page(f"{other_yy}-의견-999"),
    ]
    notion = _mock_notion_with_pages(pages)
    doc_no = await SL.issue_review_doc_number(notion, "db-id")
    assert doc_no == f"{yy}-의견-002"


# ── is_last_review_doc_number ──


@pytest.mark.asyncio
async def test_is_last_returns_true_for_max() -> None:
    yy = date.today().strftime("%y")
    pages = [_page(f"{yy}-의견-001"), _page(f"{yy}-의견-005")]
    notion = _mock_notion_with_pages(pages)
    assert await SL.is_last_review_doc_number(notion, "db-id", doc_no=f"{yy}-의견-005")


@pytest.mark.asyncio
async def test_is_last_returns_false_for_middle() -> None:
    yy = date.today().strftime("%y")
    pages = [
        _page(f"{yy}-의견-001"),
        _page(f"{yy}-의견-003"),
        _page(f"{yy}-의견-005"),
    ]
    notion = _mock_notion_with_pages(pages)
    assert not await SL.is_last_review_doc_number(
        notion, "db-id", doc_no=f"{yy}-의견-003"
    )


@pytest.mark.asyncio
async def test_is_last_empty_doc_no() -> None:
    notion = _mock_notion_with_pages([])
    assert not await SL.is_last_review_doc_number(notion, "db-id", doc_no="")
