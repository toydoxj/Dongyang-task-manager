"""sales update/archive mirror-first + outbox 회귀 테스트."""
from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app.models import mirror as M
from app.models.notion_outbox import OP_DELETE, OP_UPDATE
from app.routers.sales import (
    _quote_task_props_for_sale,
    _require_quote_submission_date,
    _sale_page_from_mirror_with_update,
)


def _sale_row(
    *,
    page_id: str = "sale-1",
    code: str = "영26-001",
    name: str = "테스트 영업",
    properties: dict | None = None,
) -> M.MirrorSales:
    if properties is None:
        properties = {
            "견적서명": {"type": "title", "title": [{"plain_text": name}]},
            "영업코드": {"type": "rich_text", "rich_text": [{"plain_text": code}]},
            "유형": {"type": "select", "select": {"name": "수주영업"}},
            "단계": {"type": "select", "select": {"name": "진행"}},
        }
    return M.MirrorSales(
        page_id=page_id,
        code=code,
        name=name,
        kind="수주영업",
        stage="진행",
        category=[],
        assignees=[],
        quote_form_data={"forms": []},
        properties=properties,
        url="https://notion.so/sale-1",
        created_time=datetime(2026, 5, 27, tzinfo=timezone.utc),
        archived=False,
    )


def test_update_archive_no_notion_dependency() -> None:
    """일반 update/archive는 사용자 응답 path에서 노션을 기다리지 않는다."""
    from app.routers.sales import archive_sale, update_sale

    assert "notion" not in inspect.signature(update_sale).parameters
    assert "notion" not in inspect.signature(archive_sale).parameters


def test_quote_mutations_no_notion_dependency() -> None:
    """견적금액 sync는 Notion 직접 update 대신 outbox를 사용한다."""
    from app.routers.sales import (
        _sync_sale_estimated_amount,
        add_external_quote,
        delete_sale_quote,
        update_external_quote,
        update_sale_quote,
    )

    assert "notion" not in inspect.signature(_sync_sale_estimated_amount).parameters
    assert "notion" not in inspect.signature(update_sale_quote).parameters
    assert "notion" not in inspect.signature(delete_sale_quote).parameters
    assert "notion" not in inspect.signature(add_external_quote).parameters
    assert "notion" not in inspect.signature(update_external_quote).parameters


def test_add_quote_keeps_notion_task_create_dependency() -> None:
    """첫 견적 task 자동 생성은 아직 Notion create_page가 필요하다."""
    from app.routers.sales import add_sale_quote

    assert "notion" in inspect.signature(add_sale_quote).parameters


def test_link_project_no_notion_dependency() -> None:
    """기존 프로젝트 연결은 신규 생성이 없어 완전 mirror direct + outbox."""
    from app.routers.sales.link import link_to_existing_project

    assert "notion" not in inspect.signature(link_to_existing_project).parameters


def test_pdf_save_no_notion_dependency() -> None:
    """Drive 저장 후 sale 첨부 메타 갱신도 outbox로 처리한다."""
    from app.routers.sales.pdf import (
        save_quote_bundle_pdf_to_drive,
        save_quote_pdf_to_drive,
    )

    assert "notion" not in inspect.signature(save_quote_pdf_to_drive).parameters
    assert "notion" not in inspect.signature(save_quote_bundle_pdf_to_drive).parameters


def test_pdf_response_preserves_quote_form_data() -> None:
    """PDF 저장 응답은 mirror 전용 견적 JSONB를 잃지 않아야 한다."""
    from app.routers.sales.pdf import _sale_response_from_page_like

    row = _sale_row()
    row.quote_form_data = {"forms": [{"id": "q1", "input": {"x": 1}}]}
    page_like = _sale_page_from_mirror_with_update(
        row, {"제출일": {"date": {"start": "2026-05-27"}}}
    )

    sale = _sale_response_from_page_like(row, page_like)

    assert sale.submission_date == "2026-05-27"
    assert sale.quote_form_data == {"forms": [{"id": "q1", "input": {"x": 1}}]}


def test_convert_keeps_notion_create_dependency() -> None:
    """전환은 새 프로젝트 id가 필요해 create_page 의존은 유지한다."""
    from app.routers.sales.link import convert_to_project

    assert "notion" in inspect.signature(convert_to_project).parameters


def test_sale_page_from_mirror_merges_props() -> None:
    row = _sale_row()
    update_props = {"단계": {"select": {"name": "제출"}}}

    page = _sale_page_from_mirror_with_update(row, update_props)

    assert page["id"] == "sale-1"
    assert page["properties"]["단계"]["select"]["name"] == "제출"
    assert page["properties"]["영업코드"]["rich_text"][0]["plain_text"] == "영26-001"
    assert page["url"] == "https://notion.so/sale-1"
    assert page["archived"] is False
    assert page["created_time"] == "2026-05-27T00:00:00+00:00"
    assert "T" in page["last_edited_time"]


def test_quote_submission_date_required() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_quote_submission_date(None)

    assert exc.value.status_code == 400


def test_quote_task_props_use_submission_date_as_completion_date() -> None:
    row = _sale_row()
    row.submission_date = date(2026, 5, 10)
    row.assignees = ["정지훈"]

    props = _quote_task_props_for_sale(row)

    assert props["상태"] == {"status": {"name": "완료"}}
    assert props["기간"] == {
        "date": {"start": "2026-05-10", "end": "2026-05-10"}
    }
    assert props["실제 완료일"] == {"date": {"start": "2026-05-10"}}
    assert props["담당자"] == {"multi_select": [{"name": "정지훈"}]}


def test_sale_project_link_props() -> None:
    from app.routers.sales.link import _sale_project_link_props

    props = _sale_project_link_props("project-1")

    assert props["단계"]["select"]["name"] == "완료"
    assert props["전환된 프로젝트"]["relation"] == [{"id": "project-1"}]


def test_op_constants() -> None:
    assert OP_UPDATE == "update"
    assert OP_DELETE == "delete"
