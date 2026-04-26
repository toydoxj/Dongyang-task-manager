"""/api/projects — 노션 메인 프로젝트 DB 조회 라우터."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.exceptions import NotFoundError
from app.models.auth import User
from app.models.project import Project, ProjectListResponse
from app.security import get_current_user
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

router = APIRouter(prefix="/projects", tags=["projects"])


def _build_filter(
    *,
    assignee: str | None,
    stage: str | None,
    team: str | None,
    completed: bool | None,
) -> dict[str, Any] | None:
    """노션 filter 표현식 합성. 없으면 None."""
    clauses: list[dict[str, Any]] = []
    if assignee:
        clauses.append(
            {"property": "담당자", "multi_select": {"contains": assignee}}
        )
    if stage:
        clauses.append({"property": "진행단계", "select": {"equals": stage}})
    if team:
        clauses.append({"property": "담당팀", "multi_select": {"contains": team}})
    if completed is not None:
        clauses.append({"property": "완료", "checkbox": {"equals": completed}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"and": clauses}


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    assignee: str | None = Query(default=None, description="담당자명"),
    stage: str | None = Query(default=None, description="진행단계"),
    team: str | None = Query(default=None, description="담당팀"),
    completed: bool | None = Query(default=None, description="완료 여부"),
    mine: bool = Query(default=False, description="True면 본인 담당만 (assignee 무시)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> ProjectListResponse:
    db_id = get_settings().notion_db_projects
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_PROJECTS 미설정",
        )

    if mine:
        # 본인 이름이 노션 담당자 옵션에 등록되어 있다고 가정 (User.name 사용)
        if not user.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 이름이 등록되어 있지 않아 mine 필터를 사용할 수 없습니다",
            )
        assignee = user.name

    filt = _build_filter(
        assignee=assignee, stage=stage, team=team, completed=completed
    )
    sorts = [{"property": "Sub_CODE", "direction": "ascending"}]
    pages = await notion.query_all(db_id, filter=filt, sorts=sorts)
    items = [Project.from_notion_page(p) for p in pages]
    return ProjectListResponse(items=items, count=len(items))


@router.get("/{page_id}", response_model=Project)
async def get_project(
    page_id: str,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return Project.from_notion_page(page)
