"""프로젝트 옵션 메타 endpoint — multi_select chips 표시용.

PR-DC (Phase 4-J 13단계): `GET /options` 분리.

parent router prefix(`/api/projects`)는 projects/__init__.py가 그대로 유지.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.models.auth import User
from app.security import get_current_user
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

router = APIRouter()


class ProjectOptions(BaseModel):
    """프로젝트 DB의 multi_select 옵션 (편집 모달의 chips 표시용)."""

    work_types: list[str] = Field(default_factory=list)


@router.get("/options", response_model=ProjectOptions)
async def get_project_options(
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> ProjectOptions:
    """노션 프로젝트 DB의 multi_select 옵션 — work_types 등.

    NotionService의 30초 ds 캐시에 의존하므로 별도 캐시 불필요.
    """
    db_id = get_settings().notion_db_projects
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NOTION_DB_PROJECTS 미설정",
        )
    ds = await notion.get_data_source(db_id)
    props = ds.get("properties", {})

    def _opts(name: str) -> list[str]:
        prop = props.get(name) or {}
        if prop.get("type") != "multi_select":
            return []
        opts = (prop.get("multi_select") or {}).get("options") or []
        return [o.get("name", "") for o in opts if o.get("name")]

    return ProjectOptions(work_types=_opts("업무내용"))
