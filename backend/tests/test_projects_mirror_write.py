"""PR-FS Phase 1.3.5 회귀 테스트 — projects 도메인 mirror-first + outbox.

projects 5 write endpoint (update/stage/assign/unassign/create) — 노션 호출 0건,
mirror direct + outbox enqueue 패턴.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import mirror as M
from app.models.project import Project
from app.routers.projects import _project_page_from_mirror_with_update


def _project_row(
    *,
    page_id: str = "proj-1",
    code: str = "P001",
    name: str = "테스트프로젝트",
    properties: dict | None = None,
) -> M.MirrorProject:
    if properties is None:
        properties = {
            "프로젝트명": {"type": "title", "title": [{"plain_text": name}]},
            "프로젝트코드": {"type": "rich_text", "rich_text": [{"plain_text": code}]},
            "진행단계": {"type": "select", "select": {"name": "진행중"}},
            "담당자": {"type": "multi_select", "multi_select": [{"name": "홍길동"}]},
        }
    return M.MirrorProject(
        page_id=page_id,
        code=code,
        name=name,
        stage="진행중",
        assignees=["홍길동"],
        teams=[],
        client_relation_ids=[],
        properties=properties,
        url="https://notion.so/...",
        archived=False,
    )


def test_project_page_from_mirror_merges_props() -> None:
    """update_props 병합 + 노션 page-like dict 형태."""
    row = _project_row()
    update_props = {"진행단계": {"select": {"name": "대기"}}}
    page = _project_page_from_mirror_with_update(row, update_props)

    assert page["id"] == "proj-1"
    assert page["properties"]["진행단계"]["select"]["name"] == "대기"
    # 기존 properties 보존
    assert page["properties"]["담당자"]["multi_select"][0]["name"] == "홍길동"
    assert page["properties"]["프로젝트명"]["title"][0]["plain_text"] == "테스트프로젝트"
    # 부가 필드
    assert page["url"] == "https://notion.so/..."
    assert page["archived"] is False
    assert "T" in page["last_edited_time"]  # ISO format


def test_project_completed_is_derived_from_stage() -> None:
    """완료 여부는 노션 체크박스가 아니라 진행단계에서 계산한다."""
    page = {
        "id": "proj-stage",
        "properties": {
            "프로젝트명": {
                "type": "title",
                "title": [{"plain_text": "단계 완료 프로젝트"}],
            },
            "진행단계": {"type": "select", "select": {"name": "완료"}},
            "완료": {"type": "checkbox", "checkbox": False},
        },
    }
    assert Project.from_notion_page(page).completed is True

    page["properties"]["진행단계"] = {
        "type": "select",
        "select": {"name": "진행중"},
    }
    page["properties"]["완료"] = {"type": "checkbox", "checkbox": True}
    assert Project.from_notion_page(page).completed is False


def test_project_page_with_null_properties() -> None:
    """row.properties=None이어도 update_props만으로 page 생성."""
    row = _project_row(properties={})
    row.properties = None  # type: ignore[assignment]
    update_props = {"진행단계": {"select": {"name": "완료"}}}
    page = _project_page_from_mirror_with_update(row, update_props)
    assert page["properties"]["진행단계"]["select"]["name"] == "완료"


def test_project_assignee_add_pattern() -> None:
    """assign_me 패턴 — current + target append."""
    row = _project_row()
    current_assignees = row.properties["담당자"]["multi_select"]
    assert [a["name"] for a in current_assignees] == ["홍길동"]

    new_assignees = ["홍길동", "이순신"]
    update_props = {
        "담당자": {"multi_select": [{"name": n} for n in new_assignees]}
    }
    page = _project_page_from_mirror_with_update(row, update_props)
    assert [a["name"] for a in page["properties"]["담당자"]["multi_select"]] == [
        "홍길동",
        "이순신",
    ]


def test_retry_works_drive_no_notion_dependency() -> None:
    """PR-GB: retry_works_drive가 노션 직접 호출 제거 → mirror-direct."""
    import inspect

    from app.routers.projects import retry_works_drive

    assert "notion" not in inspect.signature(retry_works_drive).parameters


def test_works_drive_url_merge() -> None:
    """WORKS Drive URL update_props 병합 — 기존 properties 보존."""
    row = _project_row()
    update_props = {"WORKS Drive URL": {"url": "https://drive.example/folder"}}
    page = _project_page_from_mirror_with_update(row, update_props)
    assert (
        page["properties"]["WORKS Drive URL"]["url"]
        == "https://drive.example/folder"
    )
    assert page["properties"]["프로젝트명"]["title"][0]["plain_text"] == "테스트프로젝트"
