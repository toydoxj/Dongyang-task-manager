"""프로젝트 계약기간 Notion payload 정규화 회귀 테스트."""
from __future__ import annotations

from app.models.project import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    notion_date_range_prop,
    project_create_to_props,
    project_update_to_props,
)


def test_notion_date_range_uses_end_as_single_date_when_start_missing() -> None:
    """start 없이 end만 있으면 Notion 단일 날짜로 보낸다."""
    assert notion_date_range_prop(None, "2026-05-27") == {
        "date": {"start": "2026-05-27", "end": None}
    }


def test_notion_date_range_sorts_reversed_range() -> None:
    """start > end 입력은 Notion이 거부하지 않도록 순서를 보정한다."""
    assert notion_date_range_prop("2026-05-30", "2026-05-01") == {
        "date": {"start": "2026-05-01", "end": "2026-05-30"}
    }


def test_project_update_contract_end_only_has_valid_start() -> None:
    """PATCH에서 계약종료일만 들어와도 date.start=null을 만들지 않는다."""
    props = project_update_to_props(
        ProjectUpdateRequest(contract_end="2026-05-27")
    )

    assert props["계약기간"] == {
        "date": {"start": "2026-05-27", "end": None}
    }
    assert props["계약"] == {"checkbox": True}


def test_project_create_contract_end_only_has_valid_start() -> None:
    """CREATE에서 계약종료일만 있어도 Notion date payload는 유효하다."""
    props = project_create_to_props(
        ProjectCreateRequest(name="테스트 프로젝트", contract_end="2026-05-27")
    )

    assert props["계약기간"] == {
        "date": {"start": "2026-05-27", "end": None}
    }
